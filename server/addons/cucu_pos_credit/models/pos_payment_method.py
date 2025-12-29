from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    payment_key = fields.Char(string="Payment Method Key")
