# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    uom_po_factor_inv = fields.Float(
        string="Factor inverso de UdM compra",
        related="uom_po_id.factor_inv",
        store=True,
    )






