from odoo import models, fields, api

class GamificationGoalDefinition(models.Model):
    _inherit = "gamification.goal.definition"

    x_model_technical_name = fields.Char(
        string="Nombre técnico del modelo",
        related="model_id.model",
        store=False,
        readonly=True,
    )

    @api.onchange('model_id')
    def _onchange_model_id_reset_domain(self):
        for rec in self:
            rec.domain = '[]'