# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ===== Configuración del Servidor Central =====
    branch_update_mode = fields.Selection([
        ('server', 'Central Server (Cloud)'),
        ('branch', 'Branch (Sucursal)'),
    ], string='Operation Mode', default='server',
       config_parameter='branch_update.mode',
       help='Modo de operación: servidor central o sucursal')

    # ===== Configuración del Servidor Central =====
    branch_update_master_api_key = fields.Char(
        string='Master API Key',
        config_parameter='branch_update.master_api_key',
        help='Clave maestra para administración'
    )
    branch_update_package_path = fields.Char(
        string='Package Storage Path',
        config_parameter='branch_update.package_path',
        default='/var/lib/odoo/update_packages',
        help='Ruta donde se almacenan los paquetes de actualización'
    )
    branch_update_max_package_size = fields.Integer(
        string='Max Package Size (MB)',
        config_parameter='branch_update.max_package_size',
        default=500,
        help='Tamaño máximo de paquete en MB'
    )
    branch_update_retention_days = fields.Integer(
        string='Log Retention (days)',
        config_parameter='branch_update.retention_days',
        default=90,
        help='Días para retener logs de actualización'
    )

    # ===== Configuración de Sucursal =====
    branch_update_cloud_url = fields.Char(
        string='Cloud Server URL',
        config_parameter='branch_update.cloud_url',
        help='URL del servidor central (ej: https://erp.empresa.com)'
    )
    branch_update_branch_uuid = fields.Char(
        string='Branch UUID',
        config_parameter='branch_update.branch_uuid',
        readonly=True,
        help='Identificador único de esta sucursal'
    )
    branch_update_api_key = fields.Char(
        string='API Key',
        config_parameter='branch_update.api_key',
        help='Clave API para autenticación con el servidor'
    )
    branch_update_branch_name = fields.Char(
        string='Branch Name',
        config_parameter='branch_update.branch_name',
        help='Nombre de esta sucursal'
    )

    # ===== Configuración de Actualizaciones =====
    branch_update_check_interval = fields.Integer(
        string='Check Interval (minutes)',
        config_parameter='branch_update.check_interval',
        default=5,
        help='Intervalo en minutos para verificar actualizaciones'
    )
    branch_update_auto_apply = fields.Boolean(
        string='Auto Apply Updates',
        config_parameter='branch_update.auto_apply',
        default=True,
        help='Aplicar actualizaciones automáticamente'
    )
    branch_update_backup_before = fields.Boolean(
        string='Backup Before Update',
        config_parameter='branch_update.backup_before_update',
        default=True,
        help='Crear backup antes de aplicar actualizaciones'
    )
    branch_update_window_start = fields.Float(
        string='Update Window Start (hour)',
        config_parameter='branch_update.window_start',
        default=2.0,
        help='Hora de inicio para aplicar actualizaciones (0-24)'
    )
    branch_update_window_end = fields.Float(
        string='Update Window End (hour)',
        config_parameter='branch_update.window_end',
        default=6.0,
        help='Hora de fin para aplicar actualizaciones (0-24)'
    )

    # ===== Configuración de Red =====
    branch_update_timeout = fields.Integer(
        string='Connection Timeout (seconds)',
        config_parameter='branch_update.timeout',
        default=30,
        help='Tiempo de espera para conexiones'
    )
    branch_update_retry_count = fields.Integer(
        string='Retry Count',
        config_parameter='branch_update.retry_count',
        default=3,
        help='Número de reintentos en caso de fallo'
    )
    branch_update_retry_delay = fields.Integer(
        string='Retry Delay (seconds)',
        config_parameter='branch_update.retry_delay',
        default=60,
        help='Tiempo de espera entre reintentos'
    )

    # ===== Estadísticas =====
    branch_update_total_branches = fields.Integer(
        string='Total Branches',
        compute='_compute_statistics'
    )
    branch_update_active_branches = fields.Integer(
        string='Active Branches',
        compute='_compute_statistics'
    )
    branch_update_online_branches = fields.Integer(
        string='Online Branches',
        compute='_compute_statistics'
    )
    branch_update_pending_updates = fields.Integer(
        string='Pending Updates',
        compute='_compute_statistics'
    )

    @api.depends('branch_update_mode')
    def _compute_statistics(self):
        for record in self:
            BranchRegistry = self.env['branch.registry']
            UpdatePackage = self.env['branch.update.package']

            record.branch_update_total_branches = BranchRegistry.search_count([])
            record.branch_update_active_branches = BranchRegistry.search_count([
                ('state', '=', 'active')
            ])
            record.branch_update_online_branches = BranchRegistry.search_count([
                ('is_online', '=', True)
            ])
            # pending_count is a computed non-stored field, can't use in domain
            # Count published packages instead
            record.branch_update_pending_updates = UpdatePackage.search_count([
                ('state', '=', 'published')
            ])

    def action_register_branch(self):
        """Abre el wizard para registrar esta sucursal."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Register Branch'),
            'res_model': 'branch.register.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_check_updates(self):
        """Fuerza una verificación de actualizaciones."""
        self.env['branch.update.agent'].check_for_updates()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Update Check'),
                'message': _('Update check completed.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_branches(self):
        """Abre la vista de sucursales."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Branches'),
            'res_model': 'branch.registry',
            'view_mode': 'tree,form',
        }

    def action_view_packages(self):
        """Abre la vista de paquetes."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Update Packages'),
            'res_model': 'branch.update.package',
            'view_mode': 'tree,form',
        }

    def action_regenerate_master_key(self):
        """Regenera la clave maestra."""
        import secrets
        new_key = secrets.token_urlsafe(32)
        self.env['ir.config_parameter'].sudo().set_param(
            'branch_update.master_api_key', new_key
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Key Regenerated'),
                'message': _('New master key: %s') % new_key,
                'type': 'warning',
                'sticky': True,
            }
        }
