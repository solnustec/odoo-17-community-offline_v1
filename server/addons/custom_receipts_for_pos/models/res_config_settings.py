# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_coupon_printing = fields.Boolean(
        string="Impresión de Cupones",
        related="company_id.enable_coupon_printing",
        readonly=False,
        help="Cuando está habilitado, imprime un cupón por cada $10 gastados"
    )
