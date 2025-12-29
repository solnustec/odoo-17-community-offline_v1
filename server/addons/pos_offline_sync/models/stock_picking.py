# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    """
    Extensión del modelo stock.picking para sincronización offline.
    """
    _inherit = 'stock.picking'

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

    # Campo para identificar transferencias creadas desde POS
    created_from_pos = fields.Boolean(
        string='Creado desde POS',
        default=False,
        copy=False,
        help='Indica si la transferencia fue creada desde el punto de venta'
    )

    def mark_as_synced(self, cloud_id=None):
        """Marca la transferencia como sincronizada."""
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
        Busca una transferencia existente.

        Args:
            data: Diccionario con datos de la transferencia

        Returns:
            stock.picking: Transferencia encontrada o None
        """
        picking = None

        # 1. Buscar por cloud_sync_id
        if data.get('cloud_sync_id'):
            picking = self.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)
            if picking:
                return picking

        # 2. Buscar por nombre exacto
        if data.get('name') and data['name'] != '/':
            picking = self.search([('name', '=', data['name'])], limit=1)
            if picking:
                return picking

        # 3. Buscar por id_database_old + picking_type
        if data.get('id_database_old') and data.get('picking_type_id'):
            picking = self.search([
                ('id_database_old', '=', str(data['id_database_old'])),
                ('picking_type_id', '=', data['picking_type_id'])
            ], limit=1)
            if picking:
                return picking

        return None


class StockMove(models.Model):
    """
    Extensión del modelo stock.move para sincronización offline.
    """
    _inherit = 'stock.move'

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
