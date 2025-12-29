
from odoo import models, fields

class ErrorPopup(models.TransientModel):
    _name = 'error.popup.custom'
    _description = 'Error Popup Contracts'

    date_start = fields.Date(required=False)
    date_end = fields.Date(required=False)

    error_messages = fields.Text(string="Errors", readonly=True)


    def continue_process(self):
        attendances = self.env['hr.work.entry'].sudo().search([
            ('date_start', '>=', self.date_start),
            ('date_stop', '<=', self.date_end)
        ])

        if attendances.exists():
            attendances.sudo().unlink()
        parent_model = 'hr.attendance.general.modal'
        # parent_model = self.env.context.get('active_model')
        # parent_record = self.env[parent_model].browse(self.env.context.get('active_id'))
        parent_record = self.env[parent_model].sudo().search([], order='id desc', limit=1)
        continue_attendance = True
        result = parent_record.process(False, continue_attendance=continue_attendance)

        if result:
            return result
    # def action_confirm(self):

