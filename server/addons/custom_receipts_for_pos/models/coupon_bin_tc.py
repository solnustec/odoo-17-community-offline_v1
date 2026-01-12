# -*- coding: utf-8 -*-
from odoo import fields, models, api


class CouponBinTC(models.Model):
    """
    Model to store BIN TC patterns that trigger coupon duplication.
    When a payment's BIN TC starts with any of these patterns and
    coupon printing is enabled, the coupons will be printed twice.
    """
    _name = 'coupon.bin.tc'
    _description = 'BIN TC para Duplicación de Cupones'
    _order = 'id'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre descriptivo para identificar esta cadena de BIN TC'
    )
    bin_pattern = fields.Char(
        string='Cadena BIN TC',
        required=True,
        help='Cadena que debe coincidir con el inicio del BIN TC para duplicar los cupones. '
             'Por ejemplo: "411111" o "4111"'
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        help='Si está desactivado, esta cadena no se considerará para la duplicación de cupones'
    )
    description = fields.Text(
        string='Descripción',
        help='Descripción adicional sobre esta cadena de BIN TC'
    )

    _sql_constraints = [
        ('bin_pattern_unique', 'UNIQUE(bin_pattern)',
         'La cadena de BIN TC debe ser única.')
    ]

    @api.model
    def get_all_bin_patterns(self):
        """
        Returns all active BIN patterns for use in POS.
        """
        patterns = self.search([('active', '=', True)])
        return patterns.mapped('bin_pattern')
