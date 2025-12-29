from odoo import models, fields


class ResPartnerCredit(models.Model):
    _inherit = "res.partner"
    _description = __doc__

    account_payments_ids = fields.One2many(
        "account.payment", "partner_id", string="Account Payments"
    )

    account_move_ids = fields.One2many(
        "account.move",
        "partner_id",
        string="Account Moves",
        domain=[("payment_state", "=", "partial")],
    )
