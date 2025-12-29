from odoo import models, fields

class GamificationChallengeLine(models.Model):
    _inherit = "gamification.challenge.line"

    x_bonification=fields.Text(string="Bonificación")
    x_bonification_amount = fields.Float(string="Bonificación monetaria", digits=(16, 2), default=0.0)