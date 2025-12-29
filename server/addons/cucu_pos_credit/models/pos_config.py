from odoo import fields, models


class POSConfigPayment(models.Model):
    _inherit = "pos.config"

    allow_pos_payment = fields.Boolean("Allow POS Payments")
    allow_pos_invoice = fields.Boolean("Allow POS Invoice Payment and Validation")
    allow_all_invoices = fields.Boolean("Allow POS Invoice Payment and Validation")
