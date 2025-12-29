# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AccountFiscalPosition(models.Model):
    """
    Extensión del modelo account.fiscal.position para sincronización offline.
    Las posiciones fiscales se usan para descuentos institucionales y mapeo de impuestos.
    """
    _inherit = 'account.fiscal.position'

    # Campos de Sincronización
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

    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True,
        copy=False
    )

    # Campos adicionales para POS offline
    is_institutional = fields.Boolean(
        string='Es Institucional',
        default=False,
        help='Indica si esta posición fiscal es para descuentos institucionales'
    )
    institutional_discount = fields.Float(
        string='Descuento Institucional (%)',
        default=0.0,
        help='Porcentaje de descuento a aplicar para clientes institucionales'
    )

    def mark_as_synced(self, cloud_id=None):
        """
        Marca la posición fiscal como sincronizada.

        Args:
            cloud_id: ID del registro en el cloud (opcional)
        """
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id

        self.write(vals)

    @api.model
    def find_or_create_from_sync(self, data):
        """
        Busca una posición fiscal existente.

        Args:
            data: Diccionario con datos de la posición fiscal

        Returns:
            account.fiscal.position: Posición encontrada o None
        """
        fiscal_position = None

        # 1. Buscar por cloud_sync_id
        if data.get('cloud_sync_id'):
            fiscal_position = self.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)
            if fiscal_position:
                return fiscal_position

        # 2. Buscar por id_database_old + name
        if data.get('id_database_old'):
            domain = [('id_database_old', '=', str(data['id_database_old']))]
            if data.get('name'):
                domain.append(('name', '=', data['name']))
            fiscal_position = self.search(domain, limit=1)
            if fiscal_position:
                return fiscal_position

        # 3. Buscar por nombre exacto
        if data.get('name'):
            fiscal_position = self.search([('name', '=', data['name'])], limit=1)
            if fiscal_position:
                return fiscal_position

        return None


class AccountFiscalPositionTax(models.Model):
    """
    Extensión del modelo account.fiscal.position.tax para sincronización offline.
    """
    _inherit = 'account.fiscal.position.tax'

    # Campos de Sincronización
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


class AccountFiscalPositionAccount(models.Model):
    """
    Extensión del modelo account.fiscal.position.account para sincronización offline.
    """
    _inherit = 'account.fiscal.position.account'

    # Campos de Sincronización
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
