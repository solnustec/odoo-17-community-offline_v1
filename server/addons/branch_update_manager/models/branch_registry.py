# -*- coding: utf-8 -*-

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BranchRegistry(models.Model):
    """
    Registro de sucursales para gestión de actualizaciones.
    Cada sucursal debe registrarse para recibir actualizaciones.
    """
    _name = 'branch.registry'
    _description = 'Branch Registry'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Branch Name',
        required=True,
        tracking=True,
        help='Nombre identificador de la sucursal'
    )
    code = fields.Char(
        string='Branch Code',
        required=True,
        tracking=True,
        help='Código único de la sucursal (ej: SUC001)'
    )
    description = fields.Text(string='Description')

    # Identificación
    branch_uuid = fields.Char(
        string='Branch UUID',
        readonly=True,
        copy=False,
        help='Identificador único generado automáticamente'
    )
    api_key = fields.Char(
        string='API Key',
        readonly=True,
        copy=False,
        groups='branch_update_manager.group_branch_update_admin',
        help='Clave API para autenticación'
    )
    api_key_hash = fields.Char(
        string='API Key Hash',
        readonly=True,
        copy=False
    )

    # Estado
    state = fields.Selection([
        ('pending', 'Pending Activation'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
    ], string='State', default='pending', tracking=True, required=True)

    # Información de conexión
    last_connection = fields.Datetime(
        string='Last Connection',
        readonly=True,
        help='Última vez que la sucursal se conectó'
    )
    last_ip_address = fields.Char(
        string='Last IP Address',
        readonly=True
    )
    connection_count = fields.Integer(
        string='Connection Count',
        readonly=True,
        default=0
    )
    is_online = fields.Boolean(
        string='Online',
        compute='_compute_is_online',
        store=True
    )
    online_status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('unknown', 'Unknown'),
    ], string='Online Status', compute='_compute_online_status')

    # Información del sistema
    odoo_version = fields.Char(string='Odoo Version', readonly=True)
    python_version = fields.Char(string='Python Version', readonly=True)
    os_info = fields.Char(string='OS Info', readonly=True)
    hostname = fields.Char(string='Hostname', readonly=True)
    installed_modules = fields.Text(
        string='Installed Modules',
        readonly=True,
        help='JSON con módulos instalados y versiones'
    )
    database_name = fields.Char(string='Database Name', readonly=True)
    database_size = fields.Char(string='Database Size', readonly=True)

    # Ubicación
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        help='Almacén asociado a esta sucursal'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    address = fields.Text(string='Address')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    country_id = fields.Many2one('res.country', string='Country')
    timezone = fields.Selection(
        '_tz_get',
        string='Timezone',
        default='America/Guayaquil'
    )

    # Contacto
    contact_name = fields.Char(string='Contact Name')
    contact_phone = fields.Char(string='Contact Phone')
    contact_email = fields.Char(string='Contact Email')

    # Actualizaciones
    current_package_id = fields.Many2one(
        'branch.update.package',
        string='Current Package',
        readonly=True,
        help='Último paquete instalado exitosamente'
    )
    current_version = fields.Char(
        string='Current Version',
        readonly=True,
        help='Versión actual instalada'
    )
    pending_update_ids = fields.Many2many(
        'branch.update.package',
        'branch_pending_updates_rel',
        'branch_id',
        'package_id',
        string='Pending Updates',
        compute='_compute_pending_updates',
        help='Actualizaciones pendientes de instalar'
    )
    pending_update_count = fields.Integer(
        string='Pending Updates Count',
        compute='_compute_pending_updates'
    )
    last_update_date = fields.Datetime(
        string='Last Update Date',
        readonly=True
    )
    last_update_status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    ], string='Last Update Status', readonly=True)

    # Configuración
    auto_update = fields.Boolean(
        string='Auto Update',
        default=True,
        help='Aplicar actualizaciones automáticamente'
    )
    update_window_start = fields.Float(
        string='Update Window Start',
        default=2.0,
        help='Hora de inicio para actualizaciones (0-24)'
    )
    update_window_end = fields.Float(
        string='Update Window End',
        default=6.0,
        help='Hora de fin para actualizaciones (0-24)'
    )
    priority = fields.Selection([
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
    ], string='Priority', default='normal')

    # Logs
    log_ids = fields.One2many(
        'branch.update.log',
        'branch_id',
        string='Update Logs'
    )
    log_count = fields.Integer(
        string='Log Count',
        compute='_compute_log_count'
    )

    # Tags para agrupación
    tag_ids = fields.Many2many(
        'branch.registry.tag',
        string='Tags',
        help='Etiquetas para agrupar sucursales'
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Branch code must be unique!'),
        ('uuid_unique', 'UNIQUE(branch_uuid)', 'Branch UUID must be unique!'),
    ]

    @api.model
    def _tz_get(self):
        import pytz
        return [(tz, tz) for tz in sorted(pytz.all_timezones)]

    @api.model
    def create(self, vals):
        # Generar UUID y API Key
        if not vals.get('branch_uuid'):
            vals['branch_uuid'] = secrets.token_hex(16)

        if not vals.get('api_key'):
            api_key = secrets.token_urlsafe(32)
            vals['api_key'] = api_key
            vals['api_key_hash'] = hashlib.sha256(api_key.encode()).hexdigest()

        return super().create(vals)

    @api.depends('last_connection')
    def _compute_is_online(self):
        threshold = datetime.now() - timedelta(minutes=10)
        for record in self:
            record.is_online = (
                record.last_connection and
                record.last_connection > threshold
            )

    @api.depends('last_connection')
    def _compute_online_status(self):
        now = datetime.now()
        for record in self:
            if not record.last_connection:
                record.online_status = 'unknown'
            elif record.last_connection > now - timedelta(minutes=10):
                record.online_status = 'online'
            else:
                record.online_status = 'offline'

    @api.depends('log_ids')
    def _compute_log_count(self):
        for record in self:
            record.log_count = len(record.log_ids)

    def _compute_pending_updates(self):
        """Calcula las actualizaciones pendientes para cada sucursal."""
        for record in self:
            if record.state != 'active':
                record.pending_update_ids = False
                record.pending_update_count = 0
                continue

            # Buscar paquetes publicados no instalados
            installed_packages = self.env['branch.update.log'].search([
                ('branch_id', '=', record.id),
                ('state', '=', 'success'),
            ]).mapped('package_id')

            domain = [
                ('state', '=', 'published'),
                ('id', 'not in', installed_packages.ids),
                '|',
                ('all_branches', '=', True),
                ('target_branch_ids', 'in', record.id),
            ]

            pending = self.env['branch.update.package'].search(domain)
            record.pending_update_ids = pending
            record.pending_update_count = len(pending)

    def action_activate(self):
        """Activa la sucursal."""
        for record in self:
            if record.state == 'pending':
                record.state = 'active'

    def action_suspend(self):
        """Suspende la sucursal."""
        for record in self:
            record.state = 'suspended'

    def action_deactivate(self):
        """Desactiva la sucursal."""
        for record in self:
            record.state = 'inactive'

    def action_regenerate_api_key(self):
        """Regenera la API Key."""
        self.ensure_one()
        api_key = secrets.token_urlsafe(32)
        self.write({
            'api_key': api_key,
            'api_key_hash': hashlib.sha256(api_key.encode()).hexdigest(),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('API Key Regenerated'),
                'message': _('New API Key: %s\nPlease update the branch configuration.') % api_key,
                'type': 'warning',
                'sticky': True,
            }
        }

    def action_view_logs(self):
        """Abre la vista de logs de la sucursal."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Update Logs - %s') % self.name,
            'res_model': 'branch.update.log',
            'view_mode': 'tree,form',
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }

    def action_force_update_check(self):
        """Fuerza una verificación de actualizaciones."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Update Check'),
                'message': _('The branch will check for updates on next connection.'),
                'type': 'info',
                'sticky': False,
            }
        }

    def verify_api_key(self, api_key):
        """Verifica si la API key es válida."""
        self.ensure_one()
        if not api_key or not self.api_key_hash:
            return False
        return hmac.compare_digest(
            self.api_key_hash,
            hashlib.sha256(api_key.encode()).hexdigest()
        )

    def update_connection_info(self, ip_address=None, system_info=None):
        """Actualiza información de conexión."""
        self.ensure_one()
        vals = {
            'last_connection': fields.Datetime.now(),
            'connection_count': self.connection_count + 1,
        }
        if ip_address:
            vals['last_ip_address'] = ip_address

        if system_info:
            if system_info.get('odoo_version'):
                vals['odoo_version'] = system_info['odoo_version']
            if system_info.get('python_version'):
                vals['python_version'] = system_info['python_version']
            if system_info.get('os_info'):
                vals['os_info'] = system_info['os_info']
            if system_info.get('hostname'):
                vals['hostname'] = system_info['hostname']
            if system_info.get('database_name'):
                vals['database_name'] = system_info['database_name']
            if system_info.get('database_size'):
                vals['database_size'] = system_info['database_size']
            if system_info.get('installed_modules'):
                import json
                vals['installed_modules'] = json.dumps(system_info['installed_modules'])

        self.sudo().write(vals)

    def get_pending_packages(self):
        """Retorna la lista de paquetes pendientes para esta sucursal."""
        self.ensure_one()
        self._compute_pending_updates()
        return [{
            'reference': pkg.reference,
            'name': pkg.name,
            'version': pkg.version,
            'priority': pkg.priority,
            'checksum_sha256': pkg.checksum_sha256,
            'package_size': pkg.package_size,
            'publish_date': pkg.publish_date.isoformat() if pkg.publish_date else None,
        } for pkg in self.pending_update_ids.sorted(key=lambda p: p.publish_date)]

    @api.model
    def cron_check_offline_branches(self):
        """
        Cron job: Verifica sucursales que no se han conectado en 24 horas.
        Solo registra en el log, no envía correos.
        """
        threshold = datetime.now() - timedelta(hours=24)
        branches = self.search([
            ('state', '=', 'active'),
            ('last_connection', '<', threshold),
        ])

        if branches:
            branch_names = ', '.join(branches.mapped('name'))
            _logger.warning(
                f'Sucursales offline detectadas ({len(branches)}): {branch_names}'
            )

        return True


class BranchRegistryTag(models.Model):
    """Etiquetas para agrupar sucursales."""
    _name = 'branch.registry.tag'
    _description = 'Branch Tag'

    name = fields.Char(string='Tag Name', required=True)
    color = fields.Integer(string='Color')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Tag name must be unique!'),
    ]
