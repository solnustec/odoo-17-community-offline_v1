# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    """
    Extensión del modelo pos.session para sincronización offline.
    """
    _inherit = 'pos.session'

    # Campos de Sincronización Cloud
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,
        help='ID del registro en el servidor cloud'
    )
    id_database_old = fields.Char(
        string='ID Base de Datos Origen',
        copy=False,
        index=True,
        help='ID del registro en la base de datos de origen (para migraciones)'
    )
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False)

    # Campos de Configuración de Sincronización
    # NOTA: Sin store=True para evitar recálculo masivo al instalar
    sync_config_id = fields.Many2one(
        'pos.sync.config',
        string='Configuración de Sincronización',
        compute='_compute_sync_config',
    )
    is_offline_mode = fields.Boolean(
        string='Modo Offline',
        compute='_compute_is_offline_mode',
    )
    pending_sync_count = fields.Integer(
        string='Pendientes de Sync',
        compute='_compute_pending_sync_count'
    )
    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True
    )

    def mark_as_synced(self, cloud_id=None):
        """Marca la sesión como sincronizada."""
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id
        self.write(vals)

    @api.depends('config_id', 'config_id.picking_type_id.warehouse_id')
    def _compute_sync_config(self):
        """Obtiene la configuración de sincronización para esta sesión."""
        for session in self:
            warehouse = session.config_id.picking_type_id.warehouse_id
            if warehouse:
                config = self.env['pos.sync.config'].get_config_for_warehouse(
                    warehouse.id
                )
                session.sync_config_id = config.id if config else False
            else:
                session.sync_config_id = False

    @api.depends('config_id', 'config_id.picking_type_id.warehouse_id')
    def _compute_is_offline_mode(self):
        """Determina si la sesión está en modo offline."""
        for session in self:
            warehouse = session.config_id.picking_type_id.warehouse_id
            if warehouse:
                config = self.env['pos.sync.config'].get_config_for_warehouse(warehouse.id)
                session.is_offline_mode = config.operation_mode == 'offline' if config else False
            else:
                session.is_offline_mode = False

    def _compute_pending_sync_count(self):
        """Calcula órdenes pendientes de sincronización en esta sesión."""
        for session in self:
            session.pending_sync_count = self.env['pos.order'].search_count([
                ('session_id', '=', session.id),
                ('sync_state', '=', 'pending'),
            ])

    def load_pos_data(self):
        """
        Override para cargar datos de sincronización en la UI del POS.
        """
        result = super().load_pos_data()

        # Agregar información de sincronización
        warehouse = self.config_id.picking_type_id.warehouse_id
        if warehouse:
            sync_config = self.env['pos.sync.config'].get_config_for_warehouse(
                warehouse.id
            )

            if sync_config:
                result['pos_offline_sync'] = {
                    'config_id': sync_config.id,
                    'config_name': sync_config.name,
                    'operation_mode': sync_config.operation_mode,
                    'is_offline': sync_config.operation_mode == 'offline',
                    'sync_interval': sync_config.sync_interval,
                    'skip_accounting': sync_config.skip_accounting,
                    'skip_invoice_generation': sync_config.skip_invoice_generation,
                    'warehouse_id': warehouse.id,
                    'warehouse_name': warehouse.name,
                    'last_sync_date': sync_config.last_sync_date.isoformat() if sync_config.last_sync_date else None,
                    'pending_count': sync_config.pending_sync_count,
                }

        return result

    def action_pos_session_close(self, balancing_account=False,
                                 amount_to_balance=0, bank_payment_method_diffs=None):
        """
        Override para sincronizar órdenes pendientes antes de cerrar sesión.
        """
        # Verificar si hay órdenes pendientes de sincronización
        if self.sync_config_id and self.sync_config_id.operation_mode != 'offline':
            pending_orders = self.env['pos.order'].search([
                ('session_id', '=', self.id),
                ('sync_state', '=', 'pending'),
            ])

            if pending_orders:
                _logger.info(
                    f'Intentando sincronizar {len(pending_orders)} órdenes '
                    f'antes de cerrar sesión {self.name}'
                )

                # Intentar sincronización
                try:
                    manager = self.env['pos.sync.manager'].sudo()
                    result = manager.execute_sync(self.sync_config_id)

                    if result.get('errors'):
                        _logger.warning(
                            f'Errores en sincronización pre-cierre: {result["errors"]}'
                        )

                except Exception as e:
                    _logger.error(f'Error en sincronización pre-cierre: {str(e)}')
                    # Continuamos con el cierre aunque falle la sincronización

        # Llamar al método padre
        return super().action_pos_session_close(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs
        )

    def action_sync_session_orders(self):
        """
        Sincroniza todas las órdenes de la sesión.
        """
        self.ensure_one()

        if not self.sync_config_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin Configuración',
                    'message': 'No hay configuración de sincronización para este POS.',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        manager = self.env['pos.sync.manager'].sudo()
        result = manager.execute_sync(self.sync_config_id)

        self.last_sync_date = fields.Datetime.now()

        if result.get('errors'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sincronización con Errores',
                    'message': f'Sincronizados: {result["uploaded"]}. Errores: {len(result["errors"])}',
                    'type': 'warning',
                    'sticky': True,
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sincronización Completada',
                'message': f'Se sincronizaron {result["uploaded"]} registros exitosamente.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_pending_sync(self):
        """
        Abre vista de órdenes pendientes de sincronización.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Órdenes Pendientes de Sincronización',
            'res_model': 'pos.order',
            'view_mode': 'tree,form',
            'domain': [
                ('session_id', '=', self.id),
                ('sync_state', '=', 'pending'),
            ],
        }

    @api.model
    def _get_pos_ui_pos_sync_config(self, params):
        """
        Obtiene configuración de sincronización para la UI.
        """
        config_id = params.get('config_id')
        if not config_id:
            return {}

        pos_config = self.env['pos.config'].browse(config_id)
        warehouse = pos_config.picking_type_id.warehouse_id

        if not warehouse:
            return {}

        sync_config = self.env['pos.sync.config'].get_config_for_warehouse(
            warehouse.id
        )

        if not sync_config:
            return {}

        return {
            'id': sync_config.id,
            'name': sync_config.name,
            'operation_mode': sync_config.operation_mode,
            'sync_interval': sync_config.sync_interval,
            'skip_accounting': sync_config.skip_accounting,
            'skip_invoice_generation': sync_config.skip_invoice_generation,
            'warehouse_id': warehouse.id,
            'warehouse_name': warehouse.name,
        }
