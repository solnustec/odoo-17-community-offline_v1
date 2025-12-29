from odoo import fields, models


class PaymentNote(models.Model):
    _inherit = "account.payment"

    notes_pos = fields.Text("Notes")
