from odoo import api, fields, models

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    # Override default value from purchase_stock module
    buy_to_resupply = fields.Boolean(default=False)

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
    is_main_warehouse = fields.Boolean(
        string='Es Bodega Principal',
        default=False,
        help='Si está activo, los orderpoints creados tendrán trigger manual. '
             'Si no, tendrán trigger automático.'
    )