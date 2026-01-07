# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class UpdateLog(models.Model):
    """
    Log de actualizaciones aplicadas en las sucursales.
    Registra cada intento de actualización con su resultado.
    """
    _name = 'branch.update.log'
    _description = 'Update Log'
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference',
        compute='_compute_name',
        store=True
    )

    # Relaciones
    branch_id = fields.Many2one(
        'branch.registry',
        string='Branch',
        required=True,
        ondelete='cascade',
        index=True
    )
    package_id = fields.Many2one(
        'branch.update.package',
        string='Package',
        required=True,
        ondelete='cascade',
        index=True
    )

    # Estado
    state = fields.Selection([
        ('pending', 'Pending'),
        ('downloading', 'Downloading'),
        ('downloaded', 'Downloaded'),
        ('verifying', 'Verifying'),
        ('applying', 'Applying'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('rolled_back', 'Rolled Back'),
    ], string='State', default='pending', required=True, index=True)

    # Información del proceso
    action = fields.Selection([
        ('download', 'Download'),
        ('install', 'Install'),
        ('rollback', 'Rollback'),
        ('verify', 'Verify'),
    ], string='Action', default='install')

    # Fechas
    start_time = fields.Datetime(string='Start Time')
    end_time = fields.Datetime(string='End Time')
    duration = fields.Float(
        string='Duration (seconds)',
        compute='_compute_duration',
        store=True
    )

    # Detalles
    download_progress = fields.Float(string='Download Progress (%)')
    bytes_downloaded = fields.Integer(string='Bytes Downloaded')
    checksum_verified = fields.Boolean(string='Checksum Verified', default=False)

    # Resultado
    success = fields.Boolean(string='Success', default=False)
    error_message = fields.Text(string='Error Message')
    error_traceback = fields.Text(string='Error Traceback')

    # Información adicional
    ip_address = fields.Char(string='IP Address')
    user_agent = fields.Char(string='User Agent')
    applied_modules = fields.Text(
        string='Applied Modules',
        help='JSON list of modules that were updated'
    )
    rollback_available = fields.Boolean(
        string='Rollback Available',
        default=False
    )
    rollback_package_path = fields.Char(
        string='Rollback Package Path',
        help='Path to the backup for rollback'
    )

    # Reintentos
    retry_count = fields.Integer(string='Retry Count', default=0)
    max_retries = fields.Integer(string='Max Retries', default=3)
    next_retry_time = fields.Datetime(string='Next Retry Time')

    # Metadatos
    metadata = fields.Text(
        string='Metadata',
        help='JSON with additional metadata'
    )

    @api.depends('branch_id', 'package_id', 'create_date')
    def _compute_name(self):
        for record in self:
            branch_code = record.branch_id.code or 'N/A'
            package_ref = record.package_id.reference or 'N/A'
            date_str = record.create_date.strftime('%Y%m%d-%H%M') if record.create_date else 'N/A'
            record.name = f"{branch_code}/{package_ref}/{date_str}"

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for record in self:
            if record.start_time and record.end_time:
                delta = record.end_time - record.start_time
                record.duration = delta.total_seconds()
            else:
                record.duration = 0

    def action_retry(self):
        """Reintenta la actualización fallida."""
        self.ensure_one()
        if self.state != 'failed':
            return

        self.write({
            'state': 'pending',
            'retry_count': self.retry_count + 1,
            'error_message': False,
            'error_traceback': False,
            'start_time': False,
            'end_time': False,
        })

    def action_rollback(self):
        """Ejecuta el rollback de esta actualización."""
        self.ensure_one()
        if not self.rollback_available:
            return

        # Crear log de rollback
        rollback_log = self.create({
            'branch_id': self.branch_id.id,
            'package_id': self.package_id.id,
            'action': 'rollback',
            'state': 'pending',
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rollback Scheduled'),
                'message': _('Rollback will be executed on next branch connection.'),
                'type': 'info',
                'sticky': False,
            }
        }

    def mark_downloading(self, progress=0, bytes_downloaded=0):
        """Marca el log como descargando."""
        self.write({
            'state': 'downloading',
            'start_time': fields.Datetime.now() if not self.start_time else self.start_time,
            'download_progress': progress,
            'bytes_downloaded': bytes_downloaded,
        })

    def mark_downloaded(self):
        """Marca el log como descargado."""
        self.write({
            'state': 'downloaded',
            'download_progress': 100,
        })

    def mark_verifying(self):
        """Marca el log como verificando."""
        self.write({'state': 'verifying'})

    def mark_applying(self):
        """Marca el log como aplicando."""
        self.write({'state': 'applying'})

    def mark_success(self, applied_modules=None, rollback_path=None):
        """Marca el log como exitoso."""
        vals = {
            'state': 'success',
            'success': True,
            'end_time': fields.Datetime.now(),
            'checksum_verified': True,
        }

        if applied_modules:
            vals['applied_modules'] = json.dumps(applied_modules)

        if rollback_path:
            vals['rollback_available'] = True
            vals['rollback_package_path'] = rollback_path

        self.write(vals)

        # Actualizar información en la sucursal
        self.branch_id.sudo().write({
            'current_package_id': self.package_id.id,
            'current_version': self.package_id.version,
            'last_update_date': fields.Datetime.now(),
            'last_update_status': 'success',
        })

        # Incrementar contador en el paquete
        self.package_id.increment_install_count(success=True)

    def mark_failed(self, error_message, traceback=None):
        """Marca el log como fallido."""
        self.write({
            'state': 'failed',
            'success': False,
            'end_time': fields.Datetime.now(),
            'error_message': error_message,
            'error_traceback': traceback,
        })

        # Actualizar información en la sucursal
        self.branch_id.sudo().write({
            'last_update_status': 'failed',
        })

        # Incrementar contador en el paquete
        self.package_id.increment_install_count(success=False)

    def mark_rolled_back(self):
        """Marca el log como revertido."""
        self.write({
            'state': 'rolled_back',
            'end_time': fields.Datetime.now(),
        })

    def set_metadata(self, key, value):
        """Establece un valor en los metadatos."""
        try:
            metadata = json.loads(self.metadata or '{}')
        except json.JSONDecodeError:
            metadata = {}

        metadata[key] = value
        self.metadata = json.dumps(metadata)

    def get_metadata(self, key, default=None):
        """Obtiene un valor de los metadatos."""
        try:
            metadata = json.loads(self.metadata or '{}')
            return metadata.get(key, default)
        except json.JSONDecodeError:
            return default

    @api.model
    def cleanup_old_logs(self, days=90):
        """Limpia logs antiguos."""
        cutoff_date = datetime.now() - timedelta(days=days)
        old_logs = self.search([
            ('create_date', '<', cutoff_date),
            ('state', 'in', ['success', 'rolled_back']),
        ])
        count = len(old_logs)
        old_logs.unlink()
        _logger.info(f"Cleaned up {count} old update logs")
        return count

    @api.model
    def get_statistics(self, branch_id=None, days=30):
        """Obtiene estadísticas de actualizaciones."""
        from datetime import timedelta

        domain = [
            ('create_date', '>=', datetime.now() - timedelta(days=days)),
        ]
        if branch_id:
            domain.append(('branch_id', '=', branch_id))

        logs = self.search(domain)

        return {
            'total': len(logs),
            'success': len(logs.filtered(lambda l: l.state == 'success')),
            'failed': len(logs.filtered(lambda l: l.state == 'failed')),
            'pending': len(logs.filtered(lambda l: l.state == 'pending')),
            'rolled_back': len(logs.filtered(lambda l: l.state == 'rolled_back')),
            'avg_duration': sum(logs.mapped('duration')) / len(logs) if logs else 0,
        }
