# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_coupon_printing = fields.Boolean(
        string='Impresión de Cupones',
        default=False,
        help='Cuando está habilitado, imprime un cupón por cada $10 gastados'
    )
