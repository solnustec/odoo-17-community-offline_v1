# -*- coding: utf-8 -*-
"""
Extensión de los modelos institution e institution.client para sincronización POS.

Agrega campos y lógica necesaria para sincronizar instituciones de crédito/descuento
entre servidores offline y el servidor principal.
"""

from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class Institution(models.Model):
    """
    Extensión del modelo institution para sincronización.

    Agrega campos de sincronización y lógica para agregar registros
    a la cola de sincronización cuando se crean o modifican.
    """
    _inherit = 'institution'

    # Campos de sincronización
    cloud_sync_id = fields.Integer(
        string='Cloud Sync ID',
        index=True,
        help='ID del registro en el servidor cloud/principal'
    )
    sync_state = fields.Selection([
        ('pending', 'Pendiente'),
        ('synced', 'Sincronizado'),
        ('error', 'Error')
    ], string='Estado Sync', default='pending', index=True)
    last_sync_date = fields.Datetime(string='Última Sincronización')
    id_database_old = fields.Char(
        string='ID Database Antiguo',
        index=True,
        help='ID original del sistema anterior'
    )

    @api.model
    def create(self, vals):
        """Override para agregar a cola de sincronización al crear."""
        record = super().create(vals)

        if self.env.context.get('skip_sync_queue'):
            return record

        self._add_to_sync_queue(record, 'create')
        return record

    def write(self, vals):
        """Override para agregar a cola de sincronización al modificar."""
        result = super().write(vals)

        if self.env.context.get('skip_sync_queue'):
            return result

        # Solo sincronizar si cambian campos relevantes
        sync_fields = {'name', 'id_institutions', 'type_credit_institution',
                       'additional_discount_percentage', 'court_day', 'pvp'}
        if sync_fields & set(vals.keys()):
            for record in self:
                self._add_to_sync_queue(record, 'write')

        return result

    def _add_to_sync_queue(self, record, operation):
        """Agrega el registro a la cola de sincronización."""
        try:
            SyncQueue = self.env['pos.sync.queue'].sudo()
            SyncManager = self.env['pos.sync.manager'].sudo()

            # Buscar configuración de sync activa
            sync_config = self.env['pos.sync.config'].sudo().search([
                ('active', '=', True)
            ], limit=1)

            if not sync_config:
                return

            # Serializar datos
            data = SyncManager.serialize_institution(record)

            # Crear registro en cola
            SyncQueue.create({
                'model_name': 'institution',
                'record_id': record.id,
                'record_ref': record.name,
                'operation': operation,
                'data': data,
                'sync_config_id': sync_config.id,
            })

            _logger.info(f'Institution {record.name} agregada a cola de sync ({operation})')

        except Exception as e:
            _logger.warning(f'Error agregando institution a cola de sync: {e}')


class InstitutionClient(models.Model):
    """
    Extensión del modelo institution.client para sincronización.

    IMPORTANTE: Este modelo sincroniza los cambios de crédito/saldo (available_amount)
    entre el servidor offline y el servidor principal, asegurando que los consumos
    de crédito realizados en cualquier punto se reflejen correctamente.
    """
    _inherit = 'institution.client'

    # Campos de sincronización
    cloud_sync_id = fields.Integer(
        string='Cloud Sync ID',
        index=True,
        help='ID del registro en el servidor cloud/principal'
    )
    sync_state = fields.Selection([
        ('pending', 'Pendiente'),
        ('synced', 'Sincronizado'),
        ('error', 'Error')
    ], string='Estado Sync', default='pending', index=True)
    last_sync_date = fields.Datetime(string='Última Sincronización')

    @api.model
    def create(self, vals):
        """Override para agregar a cola de sincronización al crear."""
        record = super().create(vals)

        if self.env.context.get('skip_sync_queue'):
            return record

        self._add_to_sync_queue(record, 'create')
        return record

    def write(self, vals):
        """
        Override para agregar a cola de sincronización al modificar.

        IMPORTANTE: Siempre sincroniza cuando cambia available_amount o sale,
        ya que estos representan cambios en el crédito del cliente.
        """
        result = super().write(vals)

        if self.env.context.get('skip_sync_queue'):
            return result

        # Siempre sincronizar si cambia el saldo disponible o el cupo
        sync_fields = {'available_amount', 'sale'}
        if sync_fields & set(vals.keys()):
            for record in self:
                self._add_to_sync_queue(record, 'write')
                _logger.info(
                    f'institution.client actualizado - partner={record.partner_id.name}, '
                    f'available_amount={record.available_amount}, sale={record.sale}'
                )

        return result

    def _add_to_sync_queue(self, record, operation):
        """Agrega el registro a la cola de sincronización."""
        try:
            SyncQueue = self.env['pos.sync.queue'].sudo()
            SyncManager = self.env['pos.sync.manager'].sudo()

            # Buscar configuración de sync activa
            sync_config = self.env['pos.sync.config'].sudo().search([
                ('active', '=', True)
            ], limit=1)

            if not sync_config:
                return

            # Serializar datos
            data = SyncManager.serialize_institution_client(record)

            # Crear registro en cola
            SyncQueue.create({
                'model_name': 'institution.client',
                'record_id': record.id,
                'record_ref': f'{record.partner_id.name} - {record.institution_id.name}',
                'operation': operation,
                'data': data,
                'sync_config_id': sync_config.id,
            })

            _logger.info(
                f'institution.client agregado a cola de sync ({operation}): '
                f'partner={record.partner_id.name}, amount={record.available_amount}'
            )

        except Exception as e:
            _logger.warning(f'Error agregando institution.client a cola de sync: {e}')
