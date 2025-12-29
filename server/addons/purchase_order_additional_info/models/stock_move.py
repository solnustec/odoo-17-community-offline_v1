import requests

from odoo import models, fields, api
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    product_image = fields.Binary(
        string='Imagen',
        related='product_id.image_128',
        readonly=True
    )
    pvf = fields.Float(string='Precio Venta Final', help='Unit price of the'
                                                         ' product')

