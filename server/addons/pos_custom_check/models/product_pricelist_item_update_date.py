from odoo import models, api
from datetime import date

class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    @api.model
    def cron_set_loyalty_cards_2026(self):
        start_date = date(2025, 10, 1)
        end_date = date(2026, 12, 31)

        # 1️⃣ SOLO PROGRAMAS TIPO TARJETA DE LEALTAD
        programs = self.search([
            ('program_type', '=', 'loyalty'),
        ])

        programs.write({
            'date_from': start_date,
            'date_to': end_date,
        })

        # 2️⃣ SOLO RECOMPENSAS DE TARJETAS DE LEALTAD
        rewards = self.env['loyalty.reward'].search([
            ('program_id.program_type', '=', 'loyalty'),
        ])

        rewards.write({
            'date_from': start_date,
            'date_to': end_date,
        })
