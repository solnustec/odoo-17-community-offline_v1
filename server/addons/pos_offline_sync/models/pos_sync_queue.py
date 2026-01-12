# -*- coding: utf-8 -*-
import json
from datetime import timedelta
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PosSyncQueue(models.Model):
    _name = 'pos.sync.queue'
    _description = 'Cola de Sincronización POS'
    _order = 'priority desc, create_date asc'

    name = fields.Char(string='Referencia', required=True, readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('pos.sync.queue'))
    model_name = fields.Char(string='Modelo', required=True)
    record_id = fields.Integer(string='ID del Registro', required=True)
    record_ref = fields.Char(string='Referencia del Registro')
    operation = fields.Selection([
        ('create', 'Crear'),
        ('write', 'Actualizar'),
        ('unlink', 'Eliminar'),
    ], string='Operación', required=True, default='create')
    data_json = fields.Text(string='Datos JSON', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', required=True, ondelete='cascade')
    pos_config_id = fields.Many2one('pos.config', string='Punto de Venta')
    session_id = fields.Many2one('pos.session', string='Sesión POS')
    user_id = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user)
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('synced', 'Sincronizado'),
        ('error', 'Error'),
        ('skipped', 'Omitido'),
    ], string='Estado', default='pending', required=True)
    priority = fields.Selection([
        ('0', 'Baja'),
        ('1', 'Normal'),
        ('2', 'Alta'),
        ('3', 'Urgente'),
    ], string='Prioridad', default='1')
    attempt_count = fields.Integer(string='Intentos', default=0)
    max_attempts = fields.Integer(string='Máximo de Intentos', default=3)
    last_attempt_date = fields.Datetime(string='Último Intento')
    next_retry_date = fields.Datetime(string='Próximo Reintento')
    sync_date = fields.Datetime(string='Fecha de Sincronización', readonly=True)
    cloud_record_id = fields.Integer(string='ID en Cloud', readonly=True)
    error_message = fields.Text(string='Mensaje de Error', readonly=True)
    response_json = fields.Text(string='Respuesta JSON', readonly=True)
    depends_on_ids = fields.Many2many('pos.sync.queue', 'pos_sync_queue_dependency_rel',
        'queue_id', 'depends_on_id', string='Depende de')
    dependent_ids = fields.Many2many('pos.sync.queue', 'pos_sync_queue_dependency_rel',
        'depends_on_id', 'queue_id', string='Dependientes')

    @api.model
    def create(self, vals):
        if not vals.get('name'):
            vals['name'] = self.env['ir.sequence'].next_by_code('pos.sync.queue') or 'SYNC/NEW'
        return super().create(vals)

    def get_data(self):
        self.ensure_one()
        try:
            return json.loads(self.data_json) if self.data_json else {}
        except json.JSONDecodeError:
            return {}

    def set_data(self, data):
        self.ensure_one()
        self.data_json = json.dumps(data, default=str)

    def mark_as_synced(self, cloud_record_id=None, response=None):
        self.ensure_one()
        vals = {
            'state': 'synced',
            'sync_date': fields.Datetime.now(),
            'error_message': False,
        }
        if cloud_record_id:
            vals['cloud_record_id'] = cloud_record_id
        if response:
            vals['response_json'] = json.dumps(response, default=str)
        self.write(vals)
        self.env['pos.sync.log'].create({
            'queue_id': self.id,
            'sync_config_id': self._get_sync_config_id(),
            'action': 'sync_success',
            'model_name': self.model_name,
            'record_id': self.record_id,
            'message': f'Sincronizado exitosamente. Cloud ID: {cloud_record_id}',
        })

    def mark_as_error(self, error_message, skip_log=False):
        self.ensure_one()
        now = fields.Datetime.now()
        new_attempt_count = self.attempt_count + 1
        delay_minutes = min(2 ** new_attempt_count, 60)
        next_retry = now + timedelta(minutes=delay_minutes)
        self.write({
            'state': 'error',
            'attempt_count': new_attempt_count,
            'last_attempt_date': now,
            'next_retry_date': next_retry,
            'error_message': error_message,
        })
        if not skip_log:
            self.env['pos.sync.log'].create({
                'queue_id': self.id,
                'sync_config_id': self._get_sync_config_id(),
                'action': 'sync_error',
                'model_name': self.model_name,
                'record_id': self.record_id,
                'message': error_message,
                'level': 'error',
            })

    def mark_as_processing(self):
        self.write({
            'state': 'processing',
            'last_attempt_date': fields.Datetime.now(),
        })

    def reset_to_pending(self):
        self.write({
            'state': 'pending',
            'attempt_count': 0,
            'error_message': False,
            'last_attempt_date': False,
        })

    def _get_sync_config_id(self):
        config = self.env['pos.sync.config'].get_config_for_warehouse(self.warehouse_id.id)
        return config.id if config else False

    @api.model
    def add_to_queue(self, model_name, record_id, operation, data, warehouse_id,
                     pos_config_id=None, session_id=None, priority='1',
                     depends_on_ids=None, record_ref=None):
        data_json = json.dumps(data, default=str)
        self.env.cr.execute("""
            SELECT id FROM pos_sync_queue
            WHERE model_name = %s AND record_id = %s
              AND state IN ('pending', 'processing') AND warehouse_id = %s
            LIMIT 1
        """, (model_name, record_id, warehouse_id))
        result = self.env.cr.fetchone()
        if result:
            existing_id = result[0]
            self.env.cr.execute("""
                UPDATE pos_sync_queue
                SET data_json = %s, operation = %s, priority = %s
                WHERE id = %s
            """, (data_json, operation, priority, existing_id))
            self.invalidate_model(['data_json', 'operation', 'priority'])
            return self.browse(existing_id)
        if not record_ref:
            record_ref = self._get_record_reference_fast(model_name, record_id, data)
        max_attempts = 3
        config = self.env['pos.sync.config'].get_config_for_warehouse(warehouse_id)
        if config:
            max_attempts = config.retry_attempts
        vals = {
            'model_name': model_name,
            'record_id': record_id,
            'record_ref': record_ref,
            'operation': operation,
            'data_json': data_json,
            'warehouse_id': warehouse_id,
            'pos_config_id': pos_config_id,
            'session_id': session_id,
            'priority': priority,
            'max_attempts': max_attempts,
        }
        queue_record = self.create(vals)
        if depends_on_ids:
            queue_record.depends_on_ids = [(6, 0, depends_on_ids)]
        return queue_record

    def _get_record_reference_fast(self, model_name, record_id, data=None):
        if data:
            if data.get('name'):
                return data['name']
            if data.get('pos_reference'):
                return data['pos_reference']
            if data.get('display_name'):
                return data['display_name']
        try:
            self.env.cr.execute(f"""
                SELECT COALESCE(name, '{model_name}#' || id::text)
                FROM {model_name.replace('.', '_')} WHERE id = %s
            """, (record_id,))
            result = self.env.cr.fetchone()
            if result:
                return result[0]
        except Exception:
            pass
        return f'{model_name}#{record_id}'

    def _get_record_reference(self, model_name, record_id):
        try:
            record = self.env[model_name].browse(record_id)
            if hasattr(record, 'name') and record.name:
                return record.name
            if hasattr(record, 'display_name'):
                return record.display_name
            return f'{model_name}#{record_id}'
        except Exception:
            return f'{model_name}#{record_id}'

    @api.model
    def get_pending_by_model(self, model_name, warehouse_id, limit=100):
        return self.search([
            ('model_name', '=', model_name),
            ('warehouse_id', '=', warehouse_id),
            ('state', '=', 'pending'),
        ], limit=limit, order='priority desc, create_date asc')

    @api.model
    def get_ready_for_sync(self, warehouse_id, limit=100):
        now = fields.Datetime.now()
        query = """
            SELECT id FROM pos_sync_queue
            WHERE warehouse_id = %s AND state IN ('pending', 'error')
              AND attempt_count < max_attempts
              AND (next_retry_date IS NULL OR next_retry_date <= %s)
              AND model_name NOT IN ('json.storage', 'json.note.credit')
            ORDER BY priority DESC, create_date ASC
            LIMIT %s FOR UPDATE SKIP LOCKED
        """
        self.env.cr.execute(query, (warehouse_id, now, limit * 2))
        candidate_ids = [row[0] for row in self.env.cr.fetchall()]
        if not candidate_ids:
            return self.env['pos.sync.queue']
        candidates = self.browse(candidate_ids)
        ready_ids = []
        for record in candidates:
            if record.depends_on_ids:
                self.env.cr.execute("""
                    SELECT COUNT(*) FROM pos_sync_queue_dependency_rel rel
                    JOIN pos_sync_queue q ON rel.depends_on_id = q.id
                    WHERE rel.queue_id = %s AND q.state != 'synced'
                """, (record.id,))
                unresolved_count = self.env.cr.fetchone()[0]
                if unresolved_count > 0:
                    continue
            ready_ids.append(record.id)
            if len(ready_ids) >= limit:
                break
        return self.browse(ready_ids)

    @api.model
    def get_ready_for_sync_batch(self, warehouse_id, limit=100):
        now = fields.Datetime.now()
        query = """
            UPDATE pos_sync_queue
            SET state = 'processing', last_attempt_date = %s
            WHERE id IN (
                SELECT id FROM pos_sync_queue
                WHERE warehouse_id = %s AND state IN ('pending', 'error')
                  AND attempt_count < max_attempts
                  AND (next_retry_date IS NULL OR next_retry_date <= %s)
                  AND model_name NOT IN ('json.storage', 'json.note.credit')
                ORDER BY priority DESC, create_date ASC
                LIMIT %s FOR UPDATE SKIP LOCKED
            ) RETURNING id
        """
        self.env.cr.execute(query, (now, warehouse_id, now, limit))
        processing_ids = [row[0] for row in self.env.cr.fetchall()]
        if not processing_ids:
            return self.env['pos.sync.queue']
        self.invalidate_model(['state', 'last_attempt_date'])
        return self.browse(processing_ids)

    @api.model
    def cleanup_old_synced(self, days=30):
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        self.env.cr.execute("""
            DELETE FROM pos_sync_queue_dependency_rel
            WHERE queue_id IN (SELECT id FROM pos_sync_queue WHERE state = 'synced' AND sync_date < %s)
               OR depends_on_id IN (SELECT id FROM pos_sync_queue WHERE state = 'synced' AND sync_date < %s)
        """, (cutoff_date, cutoff_date))
        self.env.cr.execute("""
            DELETE FROM pos_sync_queue WHERE state = 'synced' AND sync_date < %s RETURNING id
        """, (cutoff_date,))
        deleted_ids = self.env.cr.fetchall()
        count = len(deleted_ids)
        self.invalidate_model()
        return count

    @api.model
    def cleanup_json_storage_queue(self):
        now = fields.Datetime.now()
        pending_records = self.search([
            ('model_name', 'in', ['json.storage', 'json.note.credit']),
            ('state', 'in', ['pending', 'error', 'processing'])
        ])
        if not pending_records:
            return 0
        ids_to_sync = []
        for queue_record in pending_records:
            try:
                if queue_record.model_name == 'json.storage':
                    storage_record = self.env['json.storage'].sudo().browse(queue_record.record_id)
                else:
                    storage_record = self.env['json.note.credit'].sudo().browse(queue_record.record_id)
                if not storage_record.exists():
                    ids_to_sync.append(queue_record.id)
                    continue
                pos_order = storage_record.pos_order if hasattr(storage_record, 'pos_order') else None
                if not pos_order:
                    ids_to_sync.append(queue_record.id)
                    continue
                order_queue = self.search([
                    ('model_name', '=', 'pos.order'),
                    ('record_id', '=', pos_order.id),
                    ('state', '=', 'synced')
                ], limit=1)
                if order_queue:
                    ids_to_sync.append(queue_record.id)
            except Exception:
                pass
        if ids_to_sync:
            self.env.cr.execute("""
                UPDATE pos_sync_queue SET state = 'synced', sync_date = %s
                WHERE id IN %s RETURNING id
            """, (now, tuple(ids_to_sync)))
            count = len(self.env.cr.fetchall())
            self.invalidate_model()
            return count
        return 0

    @api.model
    def cleanup_stuck_processing(self, hours=2):
        cutoff_date = fields.Datetime.now() - timedelta(hours=hours)
        self.env.cr.execute("""
            UPDATE pos_sync_queue SET state = 'pending'
            WHERE state = 'processing' AND last_attempt_date < %s RETURNING id
        """, (cutoff_date,))
        reset_ids = self.env.cr.fetchall()
        count = len(reset_ids)
        if count > 0:
            self.invalidate_model(['state'])
        return count

    def action_retry(self):
        self.filtered(lambda r: r.state == 'error').reset_to_pending()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Reintento Programado',
                'message': 'Los registros serán reintentados en la próxima sincronización.',
                'type': 'info',
                'sticky': False,
            }
        }

    def action_skip(self):
        self.write({'state': 'skipped'})
