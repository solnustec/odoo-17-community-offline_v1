from odoo import models, fields, api

class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    in_blacklist = fields.Boolean(string="En lista negra", default=False)

    @api.model
    def create(self, vals):
        hr_applicant = super(HrApplicant, self).create(vals)
        if 'identification' in vals:
            hr_applicant.check_in_blacklist()
        return hr_applicant

    def write(self, vals):
        result = super(HrApplicant, self).write(vals)
        if 'identification' in vals:
            self.check_in_blacklist()
        return result


    def check_in_blacklist(self):
        for applicant in self:
            employee = self.env['hr.employee'].with_context(active_test=False).search(
                [('identification_id', '=', applicant.identification)],
                limit=1
            )
            if employee.exists() and employee.is_on_the_blacklist:
                applicant.write({
                    'in_blacklist': True,
                    'color': 1,
                    'kanban_state': 'blocked',
                })
            elif employee.exists() and not employee.is_on_the_blacklist:
                applicant.write({
                    'in_blacklist': False,
                    'color': 0,
                    'kanban_state': 'normal',
                })
