from odoo import models, api
from datetime import date

class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    @api.model
    def cron_set_all_loyalty_programs_2026(self):
        start_date = date(2026, 1, 1)
        end_date = date(2026, 12, 31)

        # 1️⃣ ACTUALIZAR TODAS LAS RECOMPENSAS (cualquier tipo)
        rewards = self.env['loyalty.reward'].search([])

        rewards.write({
            'date_from': start_date,
            'date_to': end_date,
        })

        # 2️⃣ ACTUALIZAR TODOS LOS PROGRAMAS (todos los tipos)
        programs = self.search([])

        programs.write({
            'date_from': start_date,
            'date_to': end_date,
        })
