# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PosSyncConfig(models.Model):
    """
    Configuración de sincronización para POS Offline.

    Este modelo gestiona la configuración de cada sucursal offline,
    definiendo qué datos sincronizar y con qué frecuencia.
    """
    _name = 'pos.sync.config'
    _description = 'Configuración de Sincronización POS Offline'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre identificativo de la configuración'
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)

    # Configuración de Sucursal
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén/Sucursal',
        required=True,
        help='Almacén que será gestionado por este POS offline'
    )
    pos_config_ids = fields.Many2many(
        'pos.config',
        'pos_sync_config_pos_config_rel',
        'sync_config_id',
        'pos_config_id',
        string='Puntos de Venta',
        help='Puntos de venta asociados a esta configuración'
    )

    # Configuración de Conexión
    cloud_url = fields.Char(
        string='URL del Servidor Cloud',
        help='URL del servidor Odoo en la nube para sincronización'
    )
    api_key = fields.Char(
        string='API Key',
        help='Clave de autenticación para la sincronización'
    )
    sync_interval = fields.Integer(
        string='Intervalo de Sincronización (minutos)',
        default=5,
        help='Frecuencia de sincronización automática en minutos'
    )

    # Modo de Operación
    operation_mode = fields.Selection([
        ('offline', 'Solo Offline'),
        ('hybrid', 'Híbrido (Online cuando disponible)'),
        ('sync_on_demand', 'Sincronización Manual'),
    ], string='Modo de Operación', default='hybrid',
        help='Define cómo opera el POS respecto a la conectividad')

    # Entidades a Sincronizar
    sync_orders = fields.Boolean(
        string='Sincronizar Órdenes',
        default=True,
        help='Sincronizar pos.order con la nube'
    )
    sync_partners = fields.Boolean(
        string='Sincronizar Clientes',
        default=True,
        help='Sincronizar res.partner con la nube'
    )
    sync_products = fields.Boolean(
        string='Sincronizar Productos',
        default=True,
        help='Recibir actualizaciones de productos desde la nube'
    )
    sync_stock = fields.Boolean(
        string='Sincronizar Stock',
        default=True,
        help='Sincronizar stock.quant con la nube'
    )
    sync_loyalty = fields.Boolean(
        string='Sincronizar Programas de Lealtad',
        default=True,
        help='Sincronizar loyalty.program y relacionados'
    )
    sync_employees = fields.Boolean(
        string='Sincronizar Empleados',
        default=True,
        help='Sincronizar hr.employee con la nube'
    )
    sync_payment_methods = fields.Boolean(
        string='Sincronizar Métodos de Pago',
        default=True,
        help='Sincronizar pos.payment.method con la nube'
    )
    sync_pricelists = fields.Boolean(
        string='Sincronizar Listas de Precios',
        default=True,
        help='Recibir actualizaciones de listas de precios desde la nube'
    )
    sync_fiscal_positions = fields.Boolean(
        string='Sincronizar Posiciones Fiscales',
        default=True,
        help='Sincronizar posiciones fiscales y descuentos institucionales'
    )
    sync_refunds = fields.Boolean(
        string='Sincronizar Reembolsos',
        default=True,
        help='Sincronizar notas de crédito/reembolsos con la nube'
    )
    sync_sessions = fields.Boolean(
        string='Sincronizar Sesiones POS',
        default=True,
        help='Sincronizar apertura y cierre de sesiones POS con la nube'
    )
    sync_stock_transfers = fields.Boolean(
        string='Sincronizar Transferencias',
        default=True,
        help='Sincronizar transferencias de stock internas con la nube'
    )
    sync_institutions = fields.Boolean(
        string='Sincronizar Instituciones de Crédito',
        default=True,
        help='Sincronizar instituciones de crédito/descuento y saldos de clientes (institution, institution.client)'
    )

    # Restricciones Contables
    skip_accounting = fields.Boolean(
        string='Omitir Registros Contables',
        default=True,
        help='No generar asientos contables en modo offline'
    )
    skip_invoice_generation = fields.Boolean(
        string='Omitir Generación de Facturas',
        default=False,
        help='No generar facturas automáticamente en modo offline. IMPORTANTE: Dejar desactivado para generar clave de acceso y autorización en Ecuador/LATAM.'
    )

    # Estado de Sincronización
    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True
    )
    sync_status = fields.Selection([
        ('idle', 'Inactivo'),
        ('syncing', 'Sincronizando'),
        ('error', 'Error'),
        ('success', 'Exitoso'),
    ], string='Estado de Sincronización', default='idle', readonly=True)
    last_error_message = fields.Text(
        string='Último Error',
        readonly=True
    )

    # Estadísticas
    pending_sync_count = fields.Integer(
        string='Registros Pendientes',
        compute='_compute_pending_sync_count',
        store=False
    )
    total_synced_orders = fields.Integer(
        string='Órdenes Sincronizadas',
        readonly=True,
        default=0
    )

    # Configuración Avanzada
    batch_size = fields.Integer(
        string='Tamaño de Lote',
        default=100,
        help='Número de registros a procesar por lote de sincronización'
    )
    retry_attempts = fields.Integer(
        string='Intentos de Reintento',
        default=3,
        help='Número de intentos antes de marcar como fallido'
    )
    sync_timeout = fields.Integer(
        string='Timeout (segundos)',
        default=30,
        help='Tiempo máximo de espera para operaciones de sincronización'
    )

    _sql_constraints = [
        ('warehouse_unique', 'UNIQUE(warehouse_id)',
         'Solo puede existir una configuración por almacén.'),
        ('name_unique', 'UNIQUE(name)',
         'El nombre de la configuración debe ser único.'),
    ]

    @api.depends('warehouse_id')
    def _compute_pending_sync_count(self):
        """Calcula el número de registros pendientes de sincronización."""
        SyncQueue = self.env['pos.sync.queue']
        for record in self:
            if record.warehouse_id:
                record.pending_sync_count = SyncQueue.search_count([
                    ('warehouse_id', '=', record.warehouse_id.id),
                    ('state', 'in', ['pending', 'error']),
                ])
            else:
                record.pending_sync_count = 0

    @api.constrains('sync_interval')
    def _check_sync_interval(self):
        """Valida que el intervalo de sincronización sea razonable."""
        for record in self:
            if record.sync_interval < 1:
                raise ValidationError(
                    'El intervalo de sincronización debe ser al menos 1 minuto.'
                )
            if record.sync_interval > 1440:  # 24 horas
                raise ValidationError(
                    'El intervalo de sincronización no puede ser mayor a 24 horas.'
                )

    @api.constrains('batch_size')
    def _check_batch_size(self):
        """Valida el tamaño de lote."""
        for record in self:
            if record.batch_size < 1 or record.batch_size > 10000:
                raise ValidationError(
                    'El tamaño de lote debe estar entre 1 y 10,000.'
                )

    def action_test_connection(self):
        """Prueba la conexión con el servidor cloud."""
        self.ensure_one()
        import requests

        if not self.cloud_url:
            raise ValidationError('Debe configurar la URL del servidor cloud.')

        try:
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

            response = requests.get(
                f'{self.cloud_url}/pos_offline_sync/ping',
                headers=headers,
                timeout=self.sync_timeout
            )
            response.raise_for_status()

            self.write({
                'sync_status': 'success',
                'last_error_message': False,
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Conexión Exitosa',
                    'message': 'Se ha establecido conexión con el servidor cloud.',
                    'type': 'success',
                    'sticky': False,
                }
            }

        except requests.exceptions.RequestException as e:
            self.write({
                'sync_status': 'error',
                'last_error_message': str(e),
            })
            raise ValidationError(f'Error de conexión: {str(e)}')

    def action_force_sync(self):
        """Fuerza una sincronización inmediata."""
        self.ensure_one()
        manager = self.env['pos.sync.manager'].sudo()
        return manager.execute_sync(self)

    def action_view_pending_records(self):
        """Abre la vista de registros pendientes de sincronización."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Registros Pendientes',
            'res_model': 'pos.sync.queue',
            'view_mode': 'tree,form',
            'domain': [
                ('warehouse_id', '=', self.warehouse_id.id),
                ('state', 'in', ['pending', 'error']),
            ],
            'context': {'default_warehouse_id': self.warehouse_id.id},
        }

    def action_view_sync_logs(self):
        """Abre la vista de logs de sincronización."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Logs de Sincronización',
            'res_model': 'pos.sync.log',
            'view_mode': 'tree,form',
            'domain': [('sync_config_id', '=', self.id)],
            'context': {'default_sync_config_id': self.id},
        }

    def action_run_migration(self):
        """
        Ejecuta la migración inicial de datos maestros.

        Descarga productos, clientes, listas de precios, etc. desde PRINCIPAL.
        Solo para modo OFFLINE.
        """
        self.ensure_one()

        if self.operation_mode != 'offline':
            raise ValidationError(
                'La migración solo está disponible en modo OFFLINE. '
                'Este punto debe recibir datos desde el PRINCIPAL.'
            )

        if not self.cloud_url:
            raise ValidationError(
                'Configure la URL del servidor PRINCIPAL antes de ejecutar la migración.'
            )

        # Ejecutar migración
        SyncManager = self.env['pos.sync.manager'].sudo()
        result = SyncManager.run_initial_migration(self)

        # Mostrar resultado
        if result.get('success'):
            message = f"Migración completada:\n\n"
            for model, data in result.get('models_processed', {}).items():
                message += f"• {model}: {data.get('imported', 0)} creados, {data.get('updated', 0)} actualizados\n"
            message += f"\nTotal: {result.get('total_records', 0)} registros"

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Migración Exitosa',
                    'message': message,
                    'type': 'success',
                    'sticky': True,
                }
            }
        else:
            errors = result.get('errors', ['Error desconocido'])
            raise ValidationError(
                'Error en migración:\n' + '\n'.join(errors[:5])
            )

    def get_sync_entities(self):
        """Retorna la lista de entidades configuradas para sincronizar."""
        self.ensure_one()
        entities = []
        if self.sync_orders:
            entities.append('pos.order')
        if self.sync_partners:
            entities.append('res.partner')
        if self.sync_products:
            entities.append('product.product')
        if self.sync_stock:
            entities.append('stock.quant')
        if self.sync_loyalty:
            entities.extend([
                'loyalty.program',
                'loyalty.rule',
                'loyalty.reward',
            ])
        if self.sync_employees:
            entities.append('hr.employee')
        if self.sync_payment_methods:
            entities.append('pos.payment.method')
        if self.sync_pricelists:
            entities.append('product.pricelist')
        if self.sync_fiscal_positions:
            entities.append('account.fiscal.position')
        if self.sync_sessions:
            entities.append('pos.session')
        if self.sync_stock_transfers:
            entities.append('stock.picking')
        if self.sync_institutions:
            entities.extend([
                'institution',
                'institution.client',
            ])
        return entities

    @api.model
    def get_config_for_warehouse(self, warehouse_id):
        """Obtiene la configuración de sincronización para un almacén."""
        return self.search([
            ('warehouse_id', '=', warehouse_id),
            ('active', '=', True),
        ], limit=1)

    @api.model
    def get_active_configs(self):
        """Retorna todas las configuraciones activas."""
        return self.search([('active', '=', True)])
