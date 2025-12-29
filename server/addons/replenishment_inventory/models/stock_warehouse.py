from odoo import api, fields, models

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    replenishment_based_on_sales = fields.Boolean(
        string='Reabastecimiento basado en Ventas',
        default=False,
        help='Si está activo, el cálculo de máximos y mínimos se basa en ventas'
    )
    replenishment_based_on_transfers = fields.Boolean(
        string='Reabastecimiento basado en Transferencias',
        default=False,
        help='Si está activo, el cálculo de máximos y mínimos se basa en transferencias'
    )