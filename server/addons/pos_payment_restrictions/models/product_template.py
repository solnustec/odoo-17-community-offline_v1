# -*- coding: utf-8 -*-

from odoo import models, fields


# from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    cumulative = fields.Boolean(string='Acumulable', default=False)
    cumulative_note = fields.Text(string='Nota', help_text="Nota")
