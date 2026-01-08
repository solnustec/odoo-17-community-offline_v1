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
        _logger.info(f'json.storage create called with keys: {list(vals.keys())}')
        record = super().create(vals)

        # Verificar si debemos omitir la sincronización
        if self.env.context.get('skip_sync_queue', False):
            _logger.info(f'json.storage {record.id}: skip_sync_queue=True, omitiendo cola')
            return record

        # Verificar si estamos en modo de instalación
        if self.env.context.get('install_mode', False):
            _logger.info(f'json.storage {record.id}: install_mode=True, omitiendo cola')
            return record

        # Agregar a la cola de sincronización
        try:
            result = record._add_to_sync_queue('create')
            _logger.info(f'json.storage {record.id}: _add_to_sync_queue resultado: {result}')
        except Exception as e:
            _logger.warning(f'Error agregando json.storage {record.id} a cola de sync: {e}', exc_info=True)

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
                        _logger.warning(f'Error actualizando sync queue para json.storage {record.id}: {e}')

        return result

    def _add_to_sync_queue(self, operation='create'):
        """
        Agrega el registro a la cola de sincronización.

        Args:
            operation: Tipo de operación ('create', 'write', 'unlink')
        """
        self.ensure_one()

        _logger.info(f'json.storage {self.id}: Iniciando _add_to_sync_queue({operation})')
        _logger.info(f'  - pos_order: {self.pos_order} (id={self.pos_order.id if self.pos_order else None})')
        _logger.info(f'  - pos_order_id: {self.pos_order_id} (id={self.pos_order_id.id if self.pos_order_id else None})')
        _logger.info(f'  - id_point_of_sale: {self.id_point_of_sale}')

        SyncQueue = self.env['pos.sync.queue']

        # Obtener el warehouse desde múltiples fuentes
        warehouse = None
        pos_config = None
        session = None

        # Opción 1: Desde pos_order (pos.order) → session → config → warehouse
        if self.pos_order and self.pos_order.session_id:
            session = self.pos_order.session_id
            pos_config = session.config_id
            if pos_config and pos_config.picking_type_id:
                warehouse = pos_config.picking_type_id.warehouse_id
                _logger.info(f'  - Warehouse desde pos_order: {warehouse.name if warehouse else None}')

        # Opción 2: Desde pos_order_id (pos.config) → warehouse
        if not warehouse and self.pos_order_id:
            pos_config = self.pos_order_id  # pos_order_id es Many2one a pos.config
            if pos_config.picking_type_id:
                warehouse = pos_config.picking_type_id.warehouse_id
                _logger.info(f'  - Warehouse desde pos_order_id (pos.config): {warehouse.name if warehouse else None}')

        # Opción 3: Buscar pos.config por external_id (id_point_of_sale es un string)
        if not warehouse and self.id_point_of_sale:
            # id_point_of_sale parece ser un external_id string
            # Intentar convertir a int y buscar por point_of_sale_id
            try:
                external_id = int(self.id_point_of_sale)
                pos_config = self.env['pos.config'].search([
                    ('point_of_sale_id', '=', external_id)
                ], limit=1)
                if pos_config and pos_config.picking_type_id:
                    warehouse = pos_config.picking_type_id.warehouse_id
                    _logger.info(f'  - Warehouse desde point_of_sale_id ({external_id}): {warehouse.name if warehouse else None}')
            except (ValueError, TypeError):
                _logger.info(f'  - id_point_of_sale "{self.id_point_of_sale}" no es un número válido')

        # Opción 4: Usar el primer warehouse activo con sync configurado
        if not warehouse:
            sync_config = self.env['pos.sync.config'].search([
                ('is_active', '=', True)
            ], limit=1)
            if sync_config:
                warehouse = sync_config.warehouse_id
                _logger.info(f'  - Warehouse desde sync_config activo: {warehouse.name if warehouse else None}')

        if not warehouse:
            _logger.warning(f'json.storage {self.id}: No se pudo determinar warehouse')
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

        if pos_config:
            queue_vals['pos_config_id'] = pos_config.id
        if session:
            queue_vals['session_id'] = session.id

        _logger.info(f'json.storage {self.id}: Creando registro en cola con warehouse={warehouse.name}')
        queue_record = SyncQueue.sudo().create(queue_vals)

        # Actualizar estado del registro
        self.with_context(skip_sync_queue=True).write({
            'sync_state': 'pending',
            'sync_queue_id': queue_record.id,
        })

        _logger.info(f'json.storage {self.id} agregado a cola de sincronización (queue_id={queue_record.id})')
        return True

    def _serialize_for_sync(self):
        """
        Serializa el registro para sincronización.

        Returns:
            dict: Datos serializados del registro
        """
        self.ensure_one()

        data = {
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
        # Agregar referencia de orden para búsqueda (no es un campo del modelo)
        if self.pos_order:
            data['_pos_order_ref'] = self.pos_order.name
        return data


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
        _logger.info(f'json.note.credit create called')
        record = super().create(vals)

        # Verificar si debemos omitir la sincronización
        if self.env.context.get('skip_sync_queue', False):
            return record

        # Verificar si estamos en modo de instalación
        if self.env.context.get('install_mode', False):
            return record

        # Agregar a la cola de sincronización
        try:
            record._add_to_sync_queue('create')
        except Exception as e:
            _logger.warning(f'Error agregando json.note.credit {record.id} a cola de sync: {e}', exc_info=True)

        return record

    def _add_to_sync_queue(self, operation='create'):
        """
        Agrega el registro a la cola de sincronización.
        """
        self.ensure_one()
        SyncQueue = self.env['pos.sync.queue']

        _logger.info(f'json.note.credit {self.id}: Iniciando _add_to_sync_queue({operation})')

        # Obtener el warehouse desde el pos_order_id (pos.config)
        warehouse = None
        pos_config = None

        if self.pos_order_id:
            pos_config = self.pos_order_id  # Es Many2one a pos.config
            if pos_config.picking_type_id:
                warehouse = pos_config.picking_type_id.warehouse_id

        # Fallback: usar sync_config activo
        if not warehouse:
            sync_config = self.env['pos.sync.config'].search([
                ('is_active', '=', True)
            ], limit=1)
            if sync_config:
                warehouse = sync_config.warehouse_id

        if not warehouse:
            _logger.warning(f'json.note.credit {self.id}: No se pudo determinar warehouse')
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
            'priority': '1',
        }

        if pos_config:
            queue_vals['pos_config_id'] = pos_config.id

        queue_record = SyncQueue.sudo().create(queue_vals)

        # Actualizar estado del registro
        self.with_context(skip_sync_queue=True).write({
            'sync_state': 'pending',
            'sync_queue_id': queue_record.id,
        })

        _logger.info(f'json.note.credit {self.id} agregado a cola de sincronización')
        return True
