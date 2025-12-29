# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError

class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    allow_check_info = fields.Boolean(related="journal_id.allow_check_info")
    code_payment_method = fields.Char("Código de método de pago")

    @api.constrains('code_payment_method')
    def _check_code_payment_method(self):
        for record in self:

            domain = [('code_payment_method', '=', record.code_payment_method), ('id', '!=', record.id)]
            if self.search_count(domain) > 0:
                raise ValidationError(
                    "El código de método de pago '%s' ya existe. Debe ser único." % record.code_payment_method)






