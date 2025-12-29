from datetime import timedelta

from odoo import models, fields, api

class EmployeeScheduleHistory(models.Model):
    _name = 'employee.schedule.history'
    _description = 'Employee Schedule History'

    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True, ondelete='cascade')
    calendar_id = fields.Many2one('resource.calendar', string="Horario", required=True)
    start_datetime = fields.Datetime(string="Fecha de Inicio", required=True)
    end_datetime = fields.Datetime(string="Fecha de Finalización")
    email_that_sender = fields.Char(
        string="Email That Sender",
        compute='_compute_email_that_sender')

    @api.model
    def create(self, vals):
        employee = super(EmployeeScheduleHistory, self).create(vals)
        if employee:
            employee.sender_email_schedule()
        return employee


    def _compute_email_that_sender(self):
        for record in self:
            email_server_id = self.env['ir.config_parameter'].sudo().get_param(
                'employee_shift_scheduling_app.email_that_sender')
            if email_server_id:
                mail_server = self.env['ir.mail_server'].browse(int(email_server_id))
                record.email_that_sender = mail_server.smtp_user
            else:
                record.email_that_sender = False


    def sender_email_schedule (self):
        for rec in self:
            if self.env['ir.config_parameter'].sudo().get_param(
                'employee_shift_scheduling_app.enable_email'):
                template_id = self.env.ref(
                    "custom_attendance.change_schedule_employee_template").id
                template = self.env['mail.template'].browse(template_id)
                template.sudo().send_mail(rec.id, force_send=True, email_values={})



class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def create(self, vals):
        employee = super(HrEmployee, self).create(vals)
        active_schedule = employee.get_active_schedule_based_on_config()
        if active_schedule:
            employee._create_schedule_history(active_schedule.id)

        return employee

    def write(self, vals):
        res = super(HrEmployee, self).write(vals)

        for employee in self:
            if 'resource_calendar_id' in vals or 'horarios_departamento_ids' in vals:
                active_schedule = employee.get_active_schedule_based_on_config()
                if active_schedule:
                    employee._create_schedule_history(active_schedule.id)

        return res

    def _create_schedule_history(self, new_calendar_id):
        now = fields.Datetime.now()

        current_history = self.env['employee.schedule.history'].sudo().search([
            ('employee_id', '=', self.id),
            ('end_datetime', '=', False)
        ], limit=1)

        if current_history and current_history.calendar_id.id == new_calendar_id:
            return

        if current_history:
            current_history.write({'end_datetime': now - timedelta(seconds=1)})

        self.env['employee.schedule.history'].create({
            'employee_id': self.id,
            'calendar_id': new_calendar_id,
            'start_datetime': now,
        })

    def get_active_schedule_based_on_config(self):
        self.ensure_one()

        type_of_resource = self.env['ir.config_parameter'].sudo().get_param(
            'hr_payroll.mode_of_attendance'
        )

        if not type_of_resource:
            return None

        if type_of_resource == 'employee':
            return self.resource_calendar_id

        elif type_of_resource == 'departament':
            if self.department_id and self.horarios_departamento_ids:
                return self.horarios_departamento_ids[:1]
            else:
                return None
