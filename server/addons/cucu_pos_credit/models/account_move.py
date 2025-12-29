from odoo import models, fields


class AccountMoveCredit(models.Model):
    _inherit = "account.move"

    pos_session_id = fields.Many2one("pos.session", "Pos Session")
    pos_config_id = fields.Many2one(
        related="pos_session_id.config_id", string="Pos Config"
    )
