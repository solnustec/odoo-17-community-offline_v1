
from odoo import api, Command, fields, models, _

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_base_local_dict(self):

        res = super()._get_base_local_dict()

        model_discount = self.env['hr.payroll.discounts']
        new_dict = {
            'get_employee_discounts': model_discount.get_employee_discounts,
        }

        res.update(new_dict)

        return res