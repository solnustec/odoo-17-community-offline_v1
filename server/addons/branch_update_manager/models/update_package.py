# -*- coding: utf-8 -*-

import base64
import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class UpdatePackage(models.Model):
    """
    Modelo principal para paquetes de actualización.
    Gestiona la creación, empaquetado y distribución de actualizaciones.
    """
    _name = 'branch.update.package'
    _description = 'Update Package'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Package Name',
        required=True,
        tracking=True,
        help='Nombre descriptivo del paquete de actualización'
    )
    reference = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        help='Referencia única del paquete'
    )
    version = fields.Char(
        string='Version',
        required=True,
        tracking=True,
        help='Versión del paquete (ej: 1.0.0, 17.0.1.2.3)'
    )
    description = fields.Text(
        string='Description',
        help='Descripción detallada de los cambios incluidos'
    )
    release_notes = fields.Html(
        string='Release Notes',
        help='Notas de la versión para los administradores'
    )

    # Estado del paquete
    state = fields.Selection([
        ('draft', 'Draft'),
        ('packaging', 'Packaging'),
        ('ready', 'Ready'),
        ('published', 'Published'),
        ('deprecated', 'Deprecated'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='draft', tracking=True, required=True)

    # Tipo de actualización
    update_type = fields.Selection([
        ('full', 'Full Package'),
        ('incremental', 'Incremental (Delta)'),
        ('hotfix', 'Hotfix'),
        ('config', 'Configuration Only'),
    ], string='Update Type', default='full', required=True, tracking=True)

    priority = fields.Selection([
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Priority', default='normal', required=True, tracking=True)

    # Módulos incluidos
    module_ids = fields.Many2many(
        'ir.module.module',
        'update_package_module_rel',
        'package_id',
        'module_id',
        string='Modules to Update',
        domain=[('state', '=', 'installed')],
        help='Módulos a incluir en la actualización'
    )
    module_version_ids = fields.One2many(
        'branch.module.version',
        'package_id',
        string='Module Versions',
        help='Versiones específicas de cada módulo'
    )

    # Archivos adicionales
    additional_files = fields.Binary(
        string='Additional Files',
        help='Archivos adicionales a incluir (ZIP)'
    )
    additional_files_name = fields.Char(string='Additional Files Name')

    # Paquete generado
    package_file = fields.Binary(
        string='Package File',
        readonly=True,
        attachment=True,
        help='Archivo ZIP del paquete generado'
    )
    package_file_name = fields.Char(
        string='Package File Name',
        readonly=True
    )
    package_size = fields.Integer(
        string='Package Size (bytes)',
        readonly=True
    )
    package_size_display = fields.Char(
        string='Package Size',
        compute='_compute_package_size_display'
    )
    checksum_sha256 = fields.Char(
        string='SHA256 Checksum',
        readonly=True,
        help='Hash SHA256 para verificar integridad'
    )
    checksum_md5 = fields.Char(
        string='MD5 Checksum',
        readonly=True
    )

    # Fechas
    package_date = fields.Datetime(
        string='Package Date',
        readonly=True,
        help='Fecha de generación del paquete'
    )
    publish_date = fields.Datetime(
        string='Publish Date',
        readonly=True,
        tracking=True
    )
    expiry_date = fields.Date(
        string='Expiry Date',
        help='Fecha de expiración (opcional)'
    )

    # Distribución
    target_branch_ids = fields.Many2many(
        'branch.registry',
        'update_package_branch_rel',
        'package_id',
        'branch_id',
        string='Target Branches',
        help='Sucursales destino (vacío = todas)'
    )
    all_branches = fields.Boolean(
        string='All Branches',
        default=True,
        help='Enviar a todas las sucursales activas'
    )

    # Estadísticas
    download_count = fields.Integer(
        string='Downloads',
        readonly=True,
        default=0
    )
    install_count = fields.Integer(
        string='Successful Installs',
        readonly=True,
        default=0
    )
    failure_count = fields.Integer(
        string='Failed Installs',
        readonly=True,
        default=0
    )
    pending_count = fields.Integer(
        string='Pending Installs',
        compute='_compute_pending_count'
    )

    # Logs
    log_ids = fields.One2many(
        'branch.update.log',
        'package_id',
        string='Update Logs'
    )

    # Configuración de aplicación
    pre_update_script = fields.Text(
        string='Pre-Update Script',
        help='Script Python a ejecutar antes de la actualización'
    )
    post_update_script = fields.Text(
        string='Post-Update Script',
        help='Script Python a ejecutar después de la actualización'
    )
    requires_restart = fields.Boolean(
        string='Requires Restart',
        default=True,
        help='Requiere reiniciar el servicio Odoo'
    )
    backup_required = fields.Boolean(
        string='Backup Required',
        default=True,
        help='Crear backup antes de aplicar'
    )

    # Dependencias
    depends_on_package_id = fields.Many2one(
        'branch.update.package',
        string='Depends On',
        domain=[('state', '=', 'published')],
        help='Paquete que debe estar instalado antes'
    )
    min_odoo_version = fields.Char(
        string='Min Odoo Version',
        default='17.0',
        help='Versión mínima de Odoo requerida'
    )

    @api.model
    def create(self, vals):
        if vals.get('reference', _('New')) == _('New'):
            vals['reference'] = self.env['ir.sequence'].next_by_code(
                'branch.update.package'
            ) or _('New')
        return super().create(vals)

    @api.depends('package_size')
    def _compute_package_size_display(self):
        for record in self:
            if record.package_size:
                size = record.package_size
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if size < 1024:
                        record.package_size_display = f"{size:.2f} {unit}"
                        break
                    size /= 1024
            else:
                record.package_size_display = '0 B'

    @api.depends('target_branch_ids', 'all_branches', 'log_ids')
    def _compute_pending_count(self):
        for record in self:
            if record.state != 'published':
                record.pending_count = 0
                continue

            if record.all_branches:
                total_branches = self.env['branch.registry'].search_count([
                    ('state', '=', 'active')
                ])
            else:
                total_branches = len(record.target_branch_ids.filtered(
                    lambda b: b.state == 'active'
                ))

            installed = self.env['branch.update.log'].search_count([
                ('package_id', '=', record.id),
                ('state', '=', 'success')
            ])
            record.pending_count = max(0, total_branches - installed)

    def action_generate_package(self):
        """Genera el paquete ZIP con los módulos seleccionados."""
        self.ensure_one()

        if not self.module_ids:
            raise UserError(_('Debe seleccionar al menos un módulo.'))

        self.state = 'packaging'

        try:
            # Crear directorio temporal
            temp_dir = tempfile.mkdtemp(prefix='odoo_update_')
            package_dir = os.path.join(temp_dir, 'package')
            os.makedirs(package_dir)

            manifest = {
                'reference': self.reference,
                'name': self.name,
                'version': self.version,
                'update_type': self.update_type,
                'priority': self.priority,
                'package_date': fields.Datetime.now().isoformat(),
                'requires_restart': self.requires_restart,
                'backup_required': self.backup_required,
                'min_odoo_version': self.min_odoo_version,
                'modules': [],
                'pre_update_script': self.pre_update_script or '',
                'post_update_script': self.post_update_script or '',
            }

            # Copiar módulos al paquete
            addons_paths = self._get_addons_paths()

            for module in self.module_ids:
                module_path = self._find_module_path(module.name, addons_paths)
                if module_path:
                    dest_path = os.path.join(package_dir, 'addons', module.name)
                    shutil.copytree(module_path, dest_path)

                    # Calcular checksum del módulo
                    module_checksum = self._calculate_directory_checksum(dest_path)

                    manifest['modules'].append({
                        'name': module.name,
                        'version': module.installed_version or '0.0.0',
                        'checksum': module_checksum,
                    })

                    # Crear registro de versión
                    self.env['branch.module.version'].create({
                        'package_id': self.id,
                        'module_name': module.name,
                        'version': module.installed_version or '0.0.0',
                        'checksum': module_checksum,
                    })
                else:
                    _logger.warning(f"Module {module.name} not found in addons paths")

            # Añadir archivos adicionales si existen
            if self.additional_files:
                additional_dir = os.path.join(package_dir, 'additional')
                os.makedirs(additional_dir)
                additional_zip_path = os.path.join(temp_dir, 'additional.zip')

                with open(additional_zip_path, 'wb') as f:
                    f.write(base64.b64decode(self.additional_files))

                with zipfile.ZipFile(additional_zip_path, 'r') as zf:
                    zf.extractall(additional_dir)

            # Guardar manifest
            manifest_path = os.path.join(package_dir, 'manifest.json')
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

            # Crear archivo ZIP
            zip_filename = f"{self.reference}_{self.version}.zip"
            zip_path = os.path.join(temp_dir, zip_filename)

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(package_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, package_dir)
                        zf.write(file_path, arcname)

            # Calcular checksums
            with open(zip_path, 'rb') as f:
                content = f.read()
                sha256_hash = hashlib.sha256(content).hexdigest()
                md5_hash = hashlib.md5(content).hexdigest()

            # Guardar paquete
            self.write({
                'package_file': base64.b64encode(content),
                'package_file_name': zip_filename,
                'package_size': len(content),
                'checksum_sha256': sha256_hash,
                'checksum_md5': md5_hash,
                'package_date': fields.Datetime.now(),
                'state': 'ready',
            })

            # Limpiar
            shutil.rmtree(temp_dir)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Package Generated'),
                    'message': _('Package %s generated successfully. Size: %s') % (
                        zip_filename, self.package_size_display
                    ),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            self.state = 'draft'
            _logger.exception("Error generating package")
            raise UserError(_('Error generating package: %s') % str(e))

    def action_publish(self):
        """Publica el paquete para distribución."""
        self.ensure_one()

        if self.state != 'ready':
            raise UserError(_('Only ready packages can be published.'))

        if not self.package_file:
            raise UserError(_('Package file is missing. Please regenerate.'))

        self.write({
            'state': 'published',
            'publish_date': fields.Datetime.now(),
        })

        # Notificar a las sucursales (opcional)
        self._notify_branches()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Package Published'),
                'message': _('Package %s is now available for distribution.') % self.reference,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_deprecate(self):
        """Marca el paquete como obsoleto."""
        self.ensure_one()
        self.state = 'deprecated'

    def action_cancel(self):
        """Cancela el paquete."""
        self.ensure_one()
        if self.install_count > 0:
            raise UserError(_(
                'Cannot cancel a package that has been installed. '
                'Mark it as deprecated instead.'
            ))
        self.state = 'cancelled'

    def action_reset_to_draft(self):
        """Resetea el paquete a borrador."""
        self.ensure_one()
        if self.state in ('published', 'deprecated') and self.install_count > 0:
            raise UserError(_('Cannot reset a package that has been installed.'))
        self.write({
            'state': 'draft',
            'package_file': False,
            'package_file_name': False,
            'package_size': 0,
            'checksum_sha256': False,
            'checksum_md5': False,
            'package_date': False,
        })
        self.module_version_ids.unlink()

    def _get_addons_paths(self):
        """Obtiene las rutas de addons configuradas."""
        config = self.env['ir.config_parameter'].sudo()
        addons_path = config.get_param('addons_path', '')

        if addons_path:
            paths = [p.strip() for p in addons_path.split(',')]
        else:
            # Rutas por defecto
            import odoo
            paths = odoo.addons.__path__

        return paths

    def _find_module_path(self, module_name, addons_paths):
        """Encuentra la ruta de un módulo."""
        for path in addons_paths:
            module_path = os.path.join(path, module_name)
            if os.path.isdir(module_path):
                manifest_path = os.path.join(module_path, '__manifest__.py')
                if os.path.exists(manifest_path):
                    return module_path
        return None

    def _calculate_directory_checksum(self, directory):
        """Calcula el checksum de un directorio."""
        sha256_hash = hashlib.sha256()

        for root, dirs, files in sorted(os.walk(directory)):
            dirs.sort()
            for filename in sorted(files):
                filepath = os.path.join(root, filename)
                # Ignorar archivos compilados y caché
                if filename.endswith(('.pyc', '.pyo')) or '__pycache__' in filepath:
                    continue
                try:
                    with open(filepath, 'rb') as f:
                        sha256_hash.update(f.read())
                except Exception:
                    pass

        return sha256_hash.hexdigest()

    def _notify_branches(self):
        """Notifica a las sucursales sobre el nuevo paquete."""
        # Esta función puede enviar notificaciones push si se configura
        _logger.info(f"Package {self.reference} published and ready for distribution")

    def get_package_info(self):
        """Retorna información del paquete para la API."""
        self.ensure_one()
        return {
            'reference': self.reference,
            'name': self.name,
            'version': self.version,
            'update_type': self.update_type,
            'priority': self.priority,
            'checksum_sha256': self.checksum_sha256,
            'checksum_md5': self.checksum_md5,
            'package_size': self.package_size,
            'publish_date': self.publish_date.isoformat() if self.publish_date else None,
            'requires_restart': self.requires_restart,
            'backup_required': self.backup_required,
            'min_odoo_version': self.min_odoo_version,
            'modules': [{
                'name': mv.module_name,
                'version': mv.version,
                'checksum': mv.checksum,
            } for mv in self.module_version_ids],
        }

    def increment_download_count(self):
        """Incrementa el contador de descargas."""
        self.sudo().write({'download_count': self.download_count + 1})

    def increment_install_count(self, success=True):
        """Incrementa el contador de instalaciones."""
        if success:
            self.sudo().write({'install_count': self.install_count + 1})
        else:
            self.sudo().write({'failure_count': self.failure_count + 1})

    @api.model
    def cron_deprecate_expired_packages(self):
        """
        Cron job: Depreca paquetes cuya fecha de expiración ha pasado.
        """
        from datetime import date
        expired = self.search([
            ('state', '=', 'published'),
            ('expiry_date', '<', date.today()),
        ])
        if expired:
            expired.write({'state': 'deprecated'})
            _logger.info(
                f'Paquetes deprecados automáticamente: {", ".join(expired.mapped("reference"))}'
            )
        return True


class ModuleVersion(models.Model):
    """Versiones de módulos incluidos en un paquete."""
    _name = 'branch.module.version'
    _description = 'Module Version in Package'

    package_id = fields.Many2one(
        'branch.update.package',
        string='Package',
        required=True,
        ondelete='cascade'
    )
    module_name = fields.Char(string='Module Name', required=True)
    version = fields.Char(string='Version', required=True)
    checksum = fields.Char(string='Checksum')
