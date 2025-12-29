from odoo import models, fields

class LoyaltyReward(models.Model):
    _inherit = 'loyalty.reward'

    is_temporary = fields.Boolean(
        string="Recompensa Temporal",
        help="Indica si esta recompensa es temporal."
    )