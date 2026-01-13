# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timedelta
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import ValidationError
from contextlib import contextmanager

_logger = logging.getLogger(__name__)


class PosSyncQueue(models.Model):
    """
    Cola de sincronización para registros pendientes.

    Almacena los registros generados en el POS offline que necesitan
    ser sincronizados con la nube cuando la conexión esté disponible.
    """
    _name = 'pos.sync.queue'
    _description = 'Cola de Sincronización POS'
    _order = 'priority desc, create_date asc'

    name = fields.Char(
        string='Referencia',
        required=True,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('pos.sync.queue')
    )

    # Identificación del Registro
    model_name = fields.Char(
        string='Modelo',
        required=True,
        index=True,
        help='Nombre técnico del modelo Odoo'
    )
    record_id = fields.Integer(
        string='ID del Registro',
        required=True,
        index=True,
        help='ID del registro local'
    )
    record_ref = fields.Char(
        string='Referencia del Registro',
        help='Referencia legible del registro (ej: POS/001)'
    )

    # Datos de Sincronización
    operation = fields.Selection([
        ('create', 'Crear'),
        ('write', 'Actualizar'),
        ('unlink', 'Eliminar'),
    ], string='Operación', required=True, default='create')

    data_json = fields.Text(
        string='Datos JSON',
        required=True,
        help='Datos serializados del registro para sincronizar'
    )

    # Contexto
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        required=True,
        index=True,
        ondelete='cascade'
    )
    pos_config_id = fields.Many2one(
        'pos.config',
        string='Punto de Venta',
        index=True
    )
    session_id = fields.Many2one(
        'pos.session',
        string='Sesión POS'
    )
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.user
    )

    # Estado y Control
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('synced', 'Sincronizado'),
        ('error', 'Error'),
        ('skipped', 'Omitido'),
    ], string='Estado', default='pending', index=True, required=True)

    priority = fields.Selection([
        ('0', 'Baja'),
        ('1', 'Normal'),
        ('2', 'Alta'),
        ('3', 'Urgente'),
    ], string='Prioridad', default='1', index=True)

    # Seguimiento de Intentos
    attempt_count = fields.Integer(
        string='Intentos',
        default=0,
        help='Número de intentos de sincronización'
    )
    max_attempts = fields.Integer(
        string='Máximo de Intentos',
        default=3
    )
    last_attempt_date = fields.Datetime(
        string='Último Intento'
    )
    next_retry_date = fields.Datetime(
        string='Próximo Reintento',
        index=True,
        help='Calculado automáticamente al marcar como error'
    )

    # Resultado de Sincronización
    sync_date = fields.Datetime(
        string='Fecha de Sincronización',
        readonly=True
    )
    cloud_record_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        help='ID del registro creado en el servidor cloud'
    )
    error_message = fields.Text(
        string='Mensaje de Error',
        readonly=True
    )
    response_json = fields.Text(
        string='Respuesta JSON',
        readonly=True,
        help='Respuesta del servidor cloud'
    )

    # Dependencias
    depends_on_ids = fields.Many2many(
        'pos.sync.queue',
        'pos_sync_queue_dependency_rel',
        'queue_id',
        'depends_on_id',
        string='Depende de',
        help='Registros que deben sincronizarse antes'
    )
    dependent_ids = fields.Many2many(
        'pos.sync.queue',
        'pos_sync_queue_dependency_rel',
        'depends_on_id',
        'queue_id',
        string='Dependientes',
        help='Registros que dependen de este'
    )

    @api.model
    def create(self, vals):
        """Genera secuencia automática si no se proporciona nombre."""
        if not vals.get('name'):
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'pos.sync.queue'
            ) or 'SYNC/NEW'
        return super().create(vals)

    def get_data(self):
        """Deserializa y retorna los datos JSON."""
        self.ensure_one()
        try:
            return json.loads(self.data_json) if self.data_json else {}
        except json.JSONDecodeError:
            _logger.error(f'Error decodificando JSON para queue {self.name}')
            return {}

    def set_data(self, data):
        """Serializa y guarda datos en formato JSON."""
        self.ensure_one()
        self.data_json = json.dumps(data, default=str)

    def mark_as_synced(self, cloud_record_id=None, response=None):
        """Marca el registro como sincronizado exitosamente."""
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

        # Registrar en log
        self.env['pos.sync.log'].create({
            'queue_id': self.id,
            'sync_config_id': self._get_sync_config_id(),
            'action': 'sync_success',
            'model_name': self.model_name,
            'record_id': self.record_id,
            'message': f'Sincronizado exitosamente. Cloud ID: {cloud_record_id}',
        })

    def mark_as_error(self, error_message, skip_log=False):
        """
        Marca el registro con error de sincronización.

        Args:
            error_message: Mensaje de error
            skip_log: Si True, no crea registro de log (para operaciones batch)
        """
        self.ensure_one()
        now = fields.Datetime.now()
        new_attempt_count = self.attempt_count + 1

        # Calcular próximo reintento con backoff exponencial
        delay_minutes = min(2 ** new_attempt_count, 60)  # Max 1 hora
        next_retry = now + timedelta(minutes=delay_minutes)

        self.write({
            'state': 'error',
            'attempt_count': new_attempt_count,
            'last_attempt_date': now,
            'next_retry_date': next_retry,
            'error_message': error_message,
        })

        # Registrar en log (opcional para operaciones batch)
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
        """Marca el registro como en procesamiento."""
        self.write({
            'state': 'processing',
            'last_attempt_date': fields.Datetime.now(),
        })

    def reset_to_pending(self):
        """Resetea el registro a estado pendiente para reintentar."""
        self.write({
            'state': 'pending',
            'attempt_count': 0,
            'error_message': False,
            'last_attempt_date': False,
        })

    def _get_sync_config_id(self):
        """Obtiene el ID de configuración de sincronización."""
        config = self.env['pos.sync.config'].get_config_for_warehouse(
            self.warehouse_id.id
        )
        return config.id if config else False

    @api.model
    def add_to_queue(self, model_name, record_id, operation, data,
                     warehouse_id, pos_config_id=None, session_id=None,
                     priority='1', depends_on_ids=None, record_ref=None):
        """
        Agrega un registro a la cola de sincronización.
        OPTIMIZADO: Usa SQL para verificar existencia y evita lecturas innecesarias.

        Args:
            model_name: Nombre técnico del modelo
            record_id: ID del registro local
            operation: 'create', 'write', o 'unlink'
            data: Diccionario con los datos a sincronizar
            warehouse_id: ID del almacén
            pos_config_id: ID del punto de venta (opcional)
            session_id: ID de la sesión POS (opcional)
            priority: Nivel de prioridad ('0'-'3')
            depends_on_ids: Lista de IDs de queue de los que depende
            record_ref: Referencia legible (opcional, evita lectura adicional)

        Returns:
            pos.sync.queue: Registro creado o actualizado
        """
        data_json = json.dumps(data, default=str)

        # Usar SQL para verificar existencia (más eficiente que search)
        self.env.cr.execute("""
            SELECT id FROM pos_sync_queue
            WHERE model_name = %s
              AND record_id = %s
              AND state IN ('pending', 'processing')
              AND warehouse_id = %s
            LIMIT 1
        """, (model_name, record_id, warehouse_id))

        result = self.env.cr.fetchone()

        if result:
            # Actualizar registro existente con SQL directo
            existing_id = result[0]
            self.env.cr.execute("""
                UPDATE pos_sync_queue
                SET data_json = %s, operation = %s, priority = %s
                WHERE id = %s
            """, (data_json, operation, priority, existing_id))
            self.invalidate_model(['data_json', 'operation', 'priority'])
            return self.browse(existing_id)

        # Si no se proporcionó record_ref, obtenerlo
        if not record_ref:
            record_ref = self._get_record_reference_fast(model_name, record_id, data)

        # Obtener max_attempts (usar cache si está disponible)
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

        _logger.debug(f'Agregado a cola de sync: {model_name}:{record_id} - {operation}')

        return queue_record

    def _get_record_reference_fast(self, model_name, record_id, data=None):
        """
        Obtiene referencia legible sin cargar el registro completo.
        OPTIMIZADO: Primero intenta extraer de data, luego de la BD.
        """
        # Intentar obtener de los datos serializados
        if data:
            if data.get('name'):
                return data['name']
            if data.get('pos_reference'):
                return data['pos_reference']
            if data.get('display_name'):
                return data['display_name']

        # Fallback: consultar solo el campo name
        try:
            self.env.cr.execute(f"""
                SELECT COALESCE(name, '{model_name}#' || id::text)
                FROM {model_name.replace('.', '_')}
                WHERE id = %s
            """, (record_id,))
            result = self.env.cr.fetchone()
            if result:
                return result[0]
        except Exception:
            pass

        return f'{model_name}#{record_id}'

    def _get_record_reference(self, model_name, record_id):
        """Obtiene una referencia legible del registro."""
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
        """Obtiene registros pendientes de un modelo específico."""
        return self.search([
            ('model_name', '=', model_name),
            ('warehouse_id', '=', warehouse_id),
            ('state', '=', 'pending'),
        ], limit=limit, order='priority desc, create_date asc')

    @api.model
    def get_ready_for_sync(self, warehouse_id, limit=100):
        """
        Obtiene registros listos para sincronizar con bloqueo de concurrencia.

        Usa SELECT FOR UPDATE SKIP LOCKED para evitar que múltiples
        procesos/cron jobs procesen los mismos registros simultáneamente.

        Args:
            warehouse_id: ID del almacén
            limit: Número máximo de registros a obtener

        Returns:
            pos.sync.queue: Recordset con registros listos
        """
        now = fields.Datetime.now()

        # Usar SQL directo con FOR UPDATE SKIP LOCKED para evitar concurrencia
        # Esto permite que múltiples workers procesen diferentes registros
        # NOTA: json.storage y json.note.credit se excluyen porque se sincronizan
        # como parte de pos.order para evitar errores de foreign key
        query = """
            SELECT id FROM pos_sync_queue
            WHERE warehouse_id = %s
              AND state IN ('pending', 'error')
              AND attempt_count < max_attempts
              AND (next_retry_date IS NULL OR next_retry_date <= %s)
              AND model_name NOT IN ('json.storage', 'json.note.credit')
            ORDER BY priority DESC, create_date ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        """

        self.env.cr.execute(query, (warehouse_id, now, limit * 2))
        candidate_ids = [row[0] for row in self.env.cr.fetchall()]

        if not candidate_ids:
            return self.env['pos.sync.queue']

        # Cargar los registros encontrados
        candidates = self.browse(candidate_ids)

        # Filtrar por dependencias resueltas (en memoria para eficiencia)
        ready_ids = []
        for record in candidates:
            # Verificar dependencias usando SQL para evitar cargar relaciones
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
        """
        Versión optimizada para procesamiento batch.
        Marca los registros como 'processing' atómicamente.

        Args:
            warehouse_id: ID del almacén
            limit: Número máximo de registros

        Returns:
            pos.sync.queue: Recordset marcados como processing
        """
        now = fields.Datetime.now()

        # Seleccionar y marcar como processing en una sola operación atómica
        # NOTA: json.storage y json.note.credit se excluyen porque se sincronizan
        # como parte de pos.order para evitar errores de foreign key
        query = """
            UPDATE pos_sync_queue
            SET state = 'processing', last_attempt_date = %s
            WHERE id IN (
                SELECT id FROM pos_sync_queue
                WHERE warehouse_id = %s
                  AND state IN ('pending', 'error')
                  AND attempt_count < max_attempts
                  AND (next_retry_date IS NULL OR next_retry_date <= %s)
                  AND model_name NOT IN ('json.storage', 'json.note.credit')
                ORDER BY priority DESC, create_date ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
        """

        self.env.cr.execute(query, (now, warehouse_id, now, limit))
        processing_ids = [row[0] for row in self.env.cr.fetchall()]

        if not processing_ids:
            return self.env['pos.sync.queue']

        # Invalidar cache para los registros actualizados
        self.invalidate_model(['state', 'last_attempt_date'])

        return self.browse(processing_ids)

    @api.model
    def cleanup_old_synced(self, days=30):
        """
        Limpia registros sincronizados antiguos usando SQL directo.
        OPTIMIZACIÓN: Usar DELETE directo es mucho más eficiente que unlink()
        para grandes volúmenes de datos.
        """
        cutoff_date = fields.Datetime.now() - timedelta(days=days)

        # Primero eliminar dependencias huérfanas
        self.env.cr.execute("""
            DELETE FROM pos_sync_queue_dependency_rel
            WHERE queue_id IN (
                SELECT id FROM pos_sync_queue
                WHERE state = 'synced' AND sync_date < %s
            )
            OR depends_on_id IN (
                SELECT id FROM pos_sync_queue
                WHERE state = 'synced' AND sync_date < %s
            )
        """, (cutoff_date, cutoff_date))

        # Luego eliminar registros antiguos
        self.env.cr.execute("""
            DELETE FROM pos_sync_queue
            WHERE state = 'synced' AND sync_date < %s
            RETURNING id
        """, (cutoff_date,))

        deleted_ids = self.env.cr.fetchall()
        count = len(deleted_ids)

        # Invalidar cache
        self.invalidate_model()

        _logger.info(f'Limpiados {count} registros de cola antiguos')
        return count

    @api.model
    def cleanup_json_storage_queue(self):
        """
        Marca como sincronizados SOLO los registros json.storage cuya orden
        asociada YA fue sincronizada exitosamente.

        OPTIMIZADO: Usa SQL para evitar N+1 queries.

        Returns:
            int: Número de registros actualizados
        """
        now = fields.Datetime.now()

        # OPTIMIZACIÓN: Usar SQL directo para encontrar json.storage/json.note.credit
        # cuyas órdenes ya están sincronizadas, evitando el problema N+1
        self.env.cr.execute("""
            UPDATE pos_sync_queue q1
            SET state = 'synced', sync_date = %s
            WHERE q1.model_name IN ('json.storage', 'json.note.credit')
              AND q1.state IN ('pending', 'error', 'processing')
              AND (
                  -- Caso 1: El registro original ya no existe (limpiar)
                  NOT EXISTS (
                      SELECT 1 FROM json_storage js
                      WHERE js.id = q1.record_id AND q1.model_name = 'json.storage'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM json_note_credit jnc
                      WHERE jnc.id = q1.record_id AND q1.model_name = 'json.note.credit'
                  )
                  -- Caso 2: La orden asociada ya fue sincronizada
                  OR EXISTS (
                      SELECT 1 FROM pos_sync_queue q2
                      JOIN json_storage js ON js.id = q1.record_id
                      WHERE q2.model_name = 'pos.order'
                        AND q2.record_id = js.pos_order
                        AND q2.state = 'synced'
                        AND q1.model_name = 'json.storage'
                  )
                  OR EXISTS (
                      SELECT 1 FROM pos_sync_queue q2
                      JOIN json_note_credit jnc ON jnc.id = q1.record_id
                      WHERE q2.model_name = 'pos.order'
                        AND q2.record_id = jnc.pos_order_id
                        AND q2.state = 'synced'
                        AND q1.model_name = 'json.note.credit'
                  )
              )
            RETURNING id
        """, (now,))

        updated_ids = self.env.cr.fetchall()
        count = len(updated_ids)

        if count > 0:
            self.invalidate_model()
            _logger.info(
                f'Marcados {count} registros json.storage/json.note.credit como sincronizados '
                f'(sus órdenes asociadas ya fueron sincronizadas)'
            )

        return count

    @api.model
    def cleanup_stuck_processing(self, hours=2):
        """
        Limpia registros atascados en estado 'processing'.
        Los devuelve a 'pending' para ser reintentados.

        Args:
            hours: Horas después de las cuales considerar un registro atascado
        """
        cutoff_date = fields.Datetime.now() - timedelta(hours=hours)

        self.env.cr.execute("""
            UPDATE pos_sync_queue
            SET state = 'pending'
            WHERE state = 'processing'
              AND last_attempt_date < %s
            RETURNING id
        """, (cutoff_date,))

        reset_ids = self.env.cr.fetchall()
        count = len(reset_ids)

        if count > 0:
            self.invalidate_model(['state'])
            _logger.warning(f'Reseteados {count} registros atascados en processing')

        return count

    def action_retry(self):
        """Acción para reintentar sincronización."""
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
        """Omite el registro de la sincronización."""
        self.write({'state': 'skipped'})
