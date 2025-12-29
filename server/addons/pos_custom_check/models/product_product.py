
from odoo import models, fields, api, _
class LoyaltyProgram(models.Model):
    _inherit = 'product.product'


    is_reward_product = fields.Boolean("Es producto de Recompensa", default=False)