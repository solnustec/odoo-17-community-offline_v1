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
    replenishment_alert_based_on = fields.Selection(
        selection=[
            ('min_qty', 'Cantidad Mínima'),
            ('reorder_point', 'Punto de Reorden'),
        ],
        string='Alerta de Reabastecimiento basada en',
        default='min_qty',
        help='Define qué valor se usa para calcular la cantidad a ordenar:\n'
             '- Cantidad Mínima: Usa el campo "Cantidad Mínima" del orderpoint\n'
             '- Punto de Reorden: Usa el campo "Punto de Reorden" del orderpoint'
    )