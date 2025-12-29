# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
class ContractCreationPlanHolidays(models.Model):
    _inherit = 'hr.contract'

    def write(self, vals):
        contract = super(ContractCreationPlanHolidays, self).write(vals)

        if ("date_start" in vals or  "state" in vals) and self.state == 'open':
            self.create_plan_accrual()
        return contract

    def create_plan_accrual(self):
        plan_exist = self.env['hr.leave.accrual.plan'].sudo().search([
            ('name', '=', self.employee_id.name)
        ], limit=1)

        day = str(self.date_start.day) if self.date_start and self.date_start.day <= 28 else 'last'
        month_map = {
            1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun',
            7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
        }
        month = month_map.get(self.date_start.month, 'jan') if self.date_start else 'jan'

        if plan_exist:
            plan_exist.write({
                'name': self.employee_id.name,
                'is_plan_general': False,
                'day_plan_general': day,
                'month_plan_general': month,
            })
            plan_exist._prepare_leave_accrual_plan()
        else:
            plan_general = self.env['hr.leave.accrual.plan'].sudo().search([
                ('is_plan_general', '=', True)
            ], limit=1)

            if plan_general:
                new_plan = plan_general.copy(default={'is_plan_general': False})
                new_plan.write({
                    'name': self.employee_id.name,
                    'is_plan_general': False,
                    'day_plan_general': day,
                    'month_plan_general': month,
                })
                new_plan._prepare_leave_accrual_plan()
            else:
                raise ValidationError("No se encontró un plan de acumulación general para duplicar.")