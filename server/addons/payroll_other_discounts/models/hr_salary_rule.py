
from odoo import api, Command, fields, models, _

class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    condition_python = fields.Text(default='''
    # Available variables:
    #----------------------
    # payslip: hr.payslip object
    # employee: hr.employee object
    # contract: hr.contract object
    # rules: dict containing the rules code (previously computed)
    # categories: dict containing the computed salary rule categories (sum of amount of all rules belonging to that category).
    # worked_days: dict containing the computed worked days
    # inputs: dict containing the computed inputs.
    # lines: dict containing the computed lines.
    # result_rules: dict containing the computed rules.
    # is_import: True if the payslip is imported.
    # get_employee_discounts(self, employee_id=None, category=False, is_percentage=False, date_from=None, date_to=None): Get employe discounts.
    # get_values_for_holidays(self, employee_id, date_start, date_end): Trae la cantidad de vacaiones en dias del ultimo periodo.

    # Note: returned value have to be set in the variable 'result'

    result = rules['NET'] > categories['NET'] * 0.10''')

    amount_python_compute = fields.Text(default='''
    # Available variables:
    #----------------------
    # payslip: hr.payslip object
    # employee: hr.employee object
    # contract: hr.contract object
    # rules: dict containing the rules code (previously computed)
    # categories: dict containing the computed salary rule categories (sum of amount of all rules belonging to that category).
    # worked_days: dict containing the computed worked days
    # inputs: dict containing the computed inputs.
    # lines: dict containing the computed lines.
    # result_rules: dict containing the computed rules.
    # is_import: True if the payslip is imported.
    # get_employee_discounts(self, employee_id=None, category=False, is_percentage=False, date_from=None, date_to=None): Get employe discounts.

    # Note: returned value have to be set in the variable 'result'

    result = rules['NET'] > categories['NET'] * 0.10''')
