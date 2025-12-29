

from odoo import fields, models, api, _

class HrWorkEntry(models.Model):
    _inherit = 'hr.work.entry'

    note = fields.Text()
    is_validator = fields.Boolean(string='Es Validador',
                                  compute='_compute_is_validator')

    @api.depends('create_uid')
    def _compute_is_validator(self):
        for record in self:
            record.is_validator = self.env.user.has_group(
                'employee_shift_scheduling_app.group_validators_entry_works_admin')

    def aprob_metod(self):
        for record in self:
            if record.state == 'draft':
                record.write({'state': 'validated'})

    def cancel_metod(self):
        for record in self:
            record.write({'state': 'cancelled'})

    def draft_metod(self):
        for record in self:
            record.write({'state': 'draft'})
