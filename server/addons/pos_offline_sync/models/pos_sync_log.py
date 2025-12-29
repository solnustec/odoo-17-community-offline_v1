# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class PosSyncLog(models.Model):
    """
    Registro de logs para operaciones de sincronización.

    Mantiene un historial de todas las operaciones de sincronización
    para auditoría y depuración.
    """
    _name = 'pos.sync.log'
    _description = 'Log de Sincronización POS'
    _order = 'create_date desc'

    name = fields.Char(
        string='Referencia',
        compute='_compute_name',
        store=True
    )

    # Contexto
    sync_config_id = fields.Many2one(
        'pos.sync.config',
        string='Configuración',
        ondelete='cascade',
        index=True
    )
    queue_id = fields.Many2one(
        'pos.sync.queue',
        string='Registro de Cola',
        ondelete='set null'
    )
    warehouse_id = fields.Many2one(
        related='sync_config_id.warehouse_id',
        string='Almacén',
        store=True
    )

    # Detalles de la Operación
    action = fields.Selection([
        ('full_sync', 'Sincronización Completa'),
        ('push', 'Subida (Push)'),
        ('pull', 'Descarga (Pull)'),
        ('sync_success', 'Sincronización Exitosa'),
        ('sync_error', 'Error de Sincronización'),
        ('connection_test', 'Prueba de Conexión'),
        ('cleanup', 'Limpieza'),
        ('manual', 'Operación Manual'),
    ], string='Acción', required=True, index=True)

    model_name = fields.Char(
        string='Modelo',
        index=True
    )
    record_id = fields.Integer(
        string='ID del Registro'
    )
    record_ref = fields.Char(
        string='Ref. Registro'
    )

    # Mensaje y Nivel
    level = fields.Selection([
        ('debug', 'Debug'),
        ('info', 'Información'),
        ('warning', 'Advertencia'),
        ('error', 'Error'),
        ('critical', 'Crítico'),
    ], string='Nivel', default='info', required=True, index=True)

    message = fields.Text(
        string='Mensaje',
        required=True
    )
    details = fields.Text(
        string='Detalles Adicionales',
        help='Información técnica adicional (JSON)'
    )

    # Métricas
    duration = fields.Float(
        string='Duración (seg)',
        help='Tiempo de ejecución en segundos'
    )
    records_processed = fields.Integer(
        string='Registros Procesados'
    )
    errors_count = fields.Integer(
        string='Errores'
    )

    # Usuario
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.user
    )

    @api.depends('action', 'create_date')
    def _compute_name(self):
        """Genera nombre descriptivo para el log."""
        action_labels = dict(self._fields['action'].selection)
        for record in self:
            date_str = record.create_date.strftime('%Y-%m-%d %H:%M') if record.create_date else ''
            action_label = action_labels.get(record.action, record.action)
            record.name = f'{action_label} - {date_str}'

    @api.model
    def log(self, sync_config_id, action, message, level='info',
            model_name=None, record_id=None, details=None,
            duration=None, records_processed=None, errors_count=None):
        """
        Crea un registro de log.

        Args:
            sync_config_id: ID de la configuración de sincronización
            action: Tipo de acción
            message: Mensaje descriptivo
            level: Nivel de log
            model_name: Nombre del modelo (opcional)
            record_id: ID del registro (opcional)
            details: Detalles adicionales (opcional)
            duration: Duración en segundos (opcional)
            records_processed: Número de registros procesados (opcional)
            errors_count: Número de errores (opcional)

        Returns:
            pos.sync.log: Registro de log creado
        """
        vals = {
            'sync_config_id': sync_config_id,
            'action': action,
            'message': message,
            'level': level,
        }

        if model_name:
            vals['model_name'] = model_name
        if record_id:
            vals['record_id'] = record_id
        if details:
            vals['details'] = details
        if duration is not None:
            vals['duration'] = duration
        if records_processed is not None:
            vals['records_processed'] = records_processed
        if errors_count is not None:
            vals['errors_count'] = errors_count

        return self.create(vals)

    @api.model
    def log_info(self, sync_config_id, message, **kwargs):
        """Atajo para log de nivel info."""
        return self.log(sync_config_id, kwargs.pop('action', 'manual'),
                       message, level='info', **kwargs)

    @api.model
    def log_warning(self, sync_config_id, message, **kwargs):
        """Atajo para log de nivel warning."""
        return self.log(sync_config_id, kwargs.pop('action', 'manual'),
                       message, level='warning', **kwargs)

    @api.model
    def log_error(self, sync_config_id, message, **kwargs):
        """Atajo para log de nivel error."""
        return self.log(sync_config_id, kwargs.pop('action', 'manual'),
                       message, level='error', **kwargs)

    @api.model
    def cleanup_old_logs(self, days=90):
        """
        Limpia logs antiguos.

        Args:
            days: Número de días de antigüedad para eliminar

        Returns:
            int: Número de registros eliminados
        """
        cutoff_date = fields.Datetime.now() - timedelta(days=days)

        # Mantener logs de error por más tiempo
        old_logs = self.search([
            '|',
            '&', ('level', 'not in', ['error', 'critical']),
                 ('create_date', '<', cutoff_date),
            '&', ('level', 'in', ['error', 'critical']),
                 ('create_date', '<', cutoff_date - timedelta(days=days)),
        ])

        count = len(old_logs)
        old_logs.unlink()

        _logger.info(f'Limpiados {count} logs antiguos')
        return count

    @api.model
    def get_recent_errors(self, sync_config_id=None, limit=50):
        """
        Obtiene errores recientes.

        Args:
            sync_config_id: ID de configuración (opcional)
            limit: Número máximo de registros

        Returns:
            pos.sync.log: Registros de error
        """
        domain = [('level', 'in', ['error', 'critical'])]
        if sync_config_id:
            domain.append(('sync_config_id', '=', sync_config_id))

        return self.search(domain, limit=limit, order='create_date desc')

    @api.model
    def get_sync_stats(self, sync_config_id, days=7):
        """
        Obtiene estadísticas de sincronización.

        Args:
            sync_config_id: ID de la configuración
            days: Número de días a analizar

        Returns:
            dict: Estadísticas de sincronización
        """
        cutoff_date = fields.Datetime.now() - timedelta(days=days)

        logs = self.search([
            ('sync_config_id', '=', sync_config_id),
            ('create_date', '>=', cutoff_date),
        ])

        total = len(logs)
        errors = len(logs.filtered(lambda l: l.level in ['error', 'critical']))
        success = len(logs.filtered(lambda l: l.action == 'sync_success'))

        total_duration = sum(logs.mapped('duration'))
        total_records = sum(logs.mapped('records_processed'))

        return {
            'total_operations': total,
            'successful': success,
            'errors': errors,
            'success_rate': (success / total * 100) if total else 0,
            'total_duration': total_duration,
            'total_records_processed': total_records,
            'avg_duration': (total_duration / total) if total else 0,
        }
