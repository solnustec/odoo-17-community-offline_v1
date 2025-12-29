from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    allow_pos_payment = fields.Boolean(
        related="pos_config_id.allow_pos_payment", readonly=False
    )
    allow_pos_invoice = fields.Boolean(
        related="pos_config_id.allow_pos_invoice", readonly=False
    )
    allow_all_invoices = fields.Boolean(
        related="pos_config_id.allow_all_invoices", readonly=False
    )
