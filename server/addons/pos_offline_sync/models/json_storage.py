# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class JsonStorageSync(models.Model):
    """
    Extensión del modelo json.storage para sincronización offline.
    """
    _inherit = 'json.storage'

    # Campos de Sincronización
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,
        help='ID del registro en el servidor cloud'
    )
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('error', 'Error'),
    ], string='Estado de Sincronización', default='local', copy=False, index=True)

    sync_queue_id = fields.Many2one(
        'pos.sync.queue',
        string='Registro en Cola',
        readonly=True,
        copy=False
    )
    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True,
        copy=False
    )

    @api.model
    def create(self, vals):
        """Override para agregar automáticamente a la cola de sincronización."""
        record = super().create(vals)

        # Verificar si debemos omitir la sincronización
        if self.env.context.get('skip_sync_queue', False):
            return record

        # Agregar a la cola de sincronización
        try:
            record._add_to_sync_queue('create')
        except Exception as e:
            _logger.warning(f'Error agregando json.storage a cola de sync: {e}')

        return record

    def write(self, vals):
        """Override para actualizar cola de sincronización si el registro cambia."""
        result = super().write(vals)

        # Verificar si debemos omitir la sincronización
        if self.env.context.get('skip_sync_queue', False):
            return result

        # Solo re-sincronizar si cambian campos importantes
        sync_trigger_fields = {'json_data', 'is_access_key', 'sent'}
        if sync_trigger_fields & set(vals.keys()):
            for record in self:
                if record.sync_state == 'synced':
                    try:
                        record._add_to_sync_queue('write')
                    except Exception as e:
                        _logger.warning(f'Error actualizando sync queue para json.storage: {e}')

        return result

    def _add_to_sync_queue(self, operation='create'):
        """
        Agrega el registro a la cola de sincronización.

        Args:
            operation: Tipo de operación ('create', 'write', 'unlink')
        """
        self.ensure_one()
        SyncQueue = self.env['pos.sync.queue']

        # Obtener el warehouse desde el pos_order o config
        warehouse = None
        if self.pos_order and self.pos_order.session_id:
            warehouse = self.pos_order.session_id.config_id.picking_type_id.warehouse_id

        if not warehouse:
            # Intentar obtener desde el contexto o configuración
            pos_config = self.env['pos.config'].search([
                ('point_of_sale_id', '=', self.id_point_of_sale)
            ], limit=1)
            if pos_config:
                warehouse = pos_config.picking_type_id.warehouse_id

        if not warehouse:
            _logger.warning(f'No se pudo determinar warehouse para json.storage {self.id}')
            return False

        # Serializar datos para la cola
        data = self._serialize_for_sync()

        # Crear registro en cola
        queue_vals = {
            'model_name': 'json.storage',
            'record_id': self.id,
            'record_ref': f'JSON-{self.id}',
            'operation': operation,
            'data_json': json.dumps(data),
            'warehouse_id': warehouse.id,
            'priority': '1',  # Prioridad normal
        }

        if self.pos_order and self.pos_order.session_id:
            queue_vals['pos_config_id'] = self.pos_order.session_id.config_id.id
            queue_vals['session_id'] = self.pos_order.session_id.id

        queue_record = SyncQueue.sudo().create(queue_vals)

        # Actualizar estado del registro
        self.with_context(skip_sync_queue=True).write({
            'sync_state': 'pending',
            'sync_queue_id': queue_record.id,
        })

        _logger.info(f'json.storage {self.id} agregado a cola de sincronización')
        return True

    def _serialize_for_sync(self):
        """
        Serializa el registro para sincronización.

        Returns:
            dict: Datos serializados del registro
        """
        self.ensure_one()

        return {
            'id': self.id,
            'json_data': self.json_data,
            'employee': self.employee,
            'id_point_of_sale': self.id_point_of_sale,
            'client_invoice': self.client_invoice,
            'id_database_old_invoice_client': self.id_database_old_invoice_client,
            'is_access_key': self.is_access_key,
            'sent': self.sent,
            'db_key': self.db_key,
            'pos_order_id': self.pos_order_id.id if self.pos_order_id else False,
            'pos_order': self.pos_order.id if self.pos_order else False,
            'create_date': self.create_date.isoformat() if self.create_date else None,
        }


class JsonNoteCreditSync(models.Model):
    """
    Extensión del modelo json.note.credit para sincronización offline.
    """
    _inherit = 'json.note.credit'

    # Campos de Sincronización
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,
        help='ID del registro en el servidor cloud'
    )
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('error', 'Error'),
    ], string='Estado de Sincronización', default='local', copy=False, index=True)

    sync_queue_id = fields.Many2one(
        'pos.sync.queue',
        string='Registro en Cola',
        readonly=True,
        copy=False
    )
    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True,
        copy=False
    )

    @api.model
    def create(self, vals):
        """Override para agregar automáticamente a la cola de sincronización."""
        record = super().create(vals)

        # Verificar si debemos omitir la sincronización
        if self.env.context.get('skip_sync_queue', False):
            return record

        # Agregar a la cola de sincronización
        try:
            record._add_to_sync_queue('create')
        except Exception as e:
            _logger.warning(f'Error agregando json.note.credit a cola de sync: {e}')

        return record

    def _add_to_sync_queue(self, operation='create'):
        """
        Agrega el registro a la cola de sincronización.
        """
        self.ensure_one()
        SyncQueue = self.env['pos.sync.queue']

        # Obtener el warehouse desde el pos_order_id (pos.config)
        warehouse = None
        if self.pos_order_id:
            pos_config = self.env['pos.config'].browse(self.pos_order_id.id)
            if pos_config:
                warehouse = pos_config.picking_type_id.warehouse_id

        if not warehouse:
            _logger.warning(f'No se pudo determinar warehouse para json.note.credit {self.id}')
            return False

        # Serializar datos para la cola
        data = {
            'id': self.id,
            'json_data': self.json_data,
            'id_point_of_sale': self.id_point_of_sale,
            'date_invoices': self.date_invoices,
            'is_access_key': self.is_access_key,
            'sent': self.sent,
            'db_key': self.db_key,
            'pos_order_id': self.pos_order_id.id if self.pos_order_id else False,
            'create_date': self.create_date.isoformat() if self.create_date else None,
        }

        # Crear registro en cola
        queue_vals = {
            'model_name': 'json.note.credit',
            'record_id': self.id,
            'record_ref': f'NC-{self.id}',
            'operation': operation,
            'data_json': json.dumps(data),
            'warehouse_id': warehouse.id,
            'pos_config_id': self.pos_order_id.id if self.pos_order_id else False,
            'priority': '1',
        }

        queue_record = SyncQueue.sudo().create(queue_vals)

        # Actualizar estado del registro
        self.with_context(skip_sync_queue=True).write({
            'sync_state': 'pending',
            'sync_queue_id': queue_record.id,
        })

        _logger.info(f'json.note.credit {self.id} agregado a cola de sincronización')
        return True
