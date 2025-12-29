from odoo import models, fields, api
from odoo.exceptions import UserError

class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    chat_bot_ok = fields.Boolean(string='Chatbot', default=False)

    def _reset_conflicting_channels(self, current_field):
        rules = {
            # 'app_mobile_ok': ['pos_ok', 'ecommerce_ok'],
            'ecommerce_ok': ['pos_ok', 'sale_ok'],
            # 'pos_ok': ['app_mobile_ok', 'ecommerce_ok'],
            'pos_ok': ['ecommerce_ok'],
        }

        for rec in self:
            for field in rules.get(current_field, []):
                setattr(rec, field, False)

    # @api.onchange('app_mobile_ok')
    # def _onchange_app_mobile_ok(self):
    #     for rec in self:
    #         if rec.app_mobile_ok:
    #             rec._reset_conflicting_channels('app_mobile_ok')

    @api.onchange('ecommerce_ok')
    def _onchange_ecommerce_ok(self):
        for rec in self:
            if rec.ecommerce_ok:
                rec._reset_conflicting_channels('ecommerce_ok')
        for program in self:
            program.reward_ids.write({
                'is_main_chat_bot': program.ecommerce_ok
            })

    @api.onchange('pos_ok')
    def _onchange_pos_ok(self):
        for rec in self:
            if rec.pos_ok:
                rec._reset_conflicting_channels('pos_ok')

    def write(self, vals):
        res = super().write(vals)
        if 'ecommerce_ok' in vals:
            for program in self:
                program.reward_ids.write({
                    'is_main_chat_bot': program.ecommerce_ok
                })
        return res