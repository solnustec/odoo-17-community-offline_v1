from odoo import models, fields

class ProductTemplateInherit(models.Model):
    _inherit = 'product.template'

    monthly_standard_deviation = fields.Float(
        string='Desviación Estandar Mensual',
        tracking=True
    )