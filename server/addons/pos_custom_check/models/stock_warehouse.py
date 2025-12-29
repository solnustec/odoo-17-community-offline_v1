from odoo import models, fields

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    # Definir el nuevo campo para almacenar el ID personalizado
    external_id = fields.Char(string='ID Externo')

    id_digital_payment = fields.Char(
        string="Código Punto de Venta",
        default=False,
        tracking=True,
        help="Este id será usado para el pago mediante la app De Una"
    )
