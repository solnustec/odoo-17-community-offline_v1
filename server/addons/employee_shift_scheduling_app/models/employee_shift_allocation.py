# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, time

import math

from odoo import api, fields, models, _ , tools
from pytz import timezone, utc


class HREmployeeInherited(models.Model):
    # _inherit = "hr.employee"
    _name = 'hr.employee.inherited'
    allocation_ids = fields.One2many('employee.shift.allocation', 'employee_id', string='Allocation')
    workday_ids = fields.One2many('employee.work.day', 'employee_id', string='Work Days')
    weekend_ids = fields.One2many('employee.week.end', 'employee_id', string='Week Ends')


class EmployeeShiftAllocation(models.Model):
    _name = "employee.shift.allocation"
    _description = "Employee Shift Allocation"
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name')
    shift_id = fields.Many2one('employee.shift', string='Shift', tracking=True)
    user_id = fields.Many2one('res.users', string='Responsible', store=True, related='shift_id.user_id')
    shift_type_id = fields.Many2one('shift.type', string='Shift Type', tracking=True)
    from_date = fields.Date(string='From Date', tracking=True)
    to_date = fields.Date(string='To Date', tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id,
                                 tracking=True)

    state = fields.Selection([('draft', 'Draft'), ('done', 'Done'), ('cancel', 'Cancel')], default='draft',
                             tracking=True)

    workday_ids = fields.One2many('employee.work.day', 'allocation_id', ondelete='cascade', string='Work Days')
    weekend_ids = fields.One2many('employee.week.end', 'allocation_id', ondelete='cascade',string='Week Ends')
    @api.model
    def create(self, vals):
        res = super(EmployeeShiftAllocation, self).create(vals)
        res['name'] = self.env['ir.sequence'].next_by_code('employee.shift.allocation') or 'New'
        template_id = self.env.ref('employee_shift_scheduling_app.employee_shift_allocation_mail_template').id
        template = self.env['mail.template'].browse(template_id)
        # template.subject = vals['name']
        template.sudo().send_mail(res.id, force_send=True)
        return res

    @api.onchange('shift_id')
    def onchange_shift_id(self):
        for rec in self:
            rec.shift_type_id = rec.shift_id.shift_type_id

    def action_done(self):
        for rec in self:
            rec.state = 'done'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'



class EmployeeWorkDay(models.Model):
    _name = "employee.work.day"
    _description = "Employee Shift Allocation"
    _rec_name = 'employee_id'

    allocation_id = fields.Many2one('employee.shift.allocation', ondelete='cascade', string='Asignación de turnos')
    shift_id = fields.Many2one('employee.shift', string='Shift')
    date = fields.Date(string='Date of Week')
    date_start = fields.Datetime(string='Start Date')
    date_stop = fields.Datetime(string="End Time")
    employee_id = fields.Many2one('hr.employee', string='Employee', related='allocation_id.employee_id', store=True)
    user_id = fields.Many2one('res.users', string='Responsible', related='allocation_id.shift_id.user_id', store=True)
    observation = fields.Text(string='Observación')
    time_in = fields.Char()
    time_out = fields.Char()
    worked_hours = fields.Float()

    @api.model
    def create(self, vals):
        # Si se actualiza el shift_id o la fecha, recalculamos las horas del nuevo turno
        shift_id = vals.get('shift_id')
        if shift_id:
            shift = self.env['employee.shift'].sudo().browse(shift_id)
            if shift:
                date = vals.get('date')
                time_from = time(int(shift.time_from),
                                 int((shift.time_from % 1) * 60))
                time_to = time(int(shift.time_to), int((shift.time_to % 1) * 60))
                date_start = datetime.combine(fields.Date.from_string(date),
                                              time_from)
                date_stop = datetime.combine(fields.Date.from_string(date), time_to)
                # Añadir 5 horas
                date_start += timedelta(hours=5)
                date_stop += timedelta(hours=5)

                vals['date_start'] = date_start
                vals['date_stop'] = date_stop
        res = super(EmployeeWorkDay, self).create(vals)
        return res

    @api.model
    def write(self, vals):
        for record in self:
            # Si se actualiza el shift_id o la fecha, recalculamos las horas del nuevo turno
            shift_id = record.shift_id.id
            if shift_id:
                shift = self.env['employee.shift'].browse(shift_id)
                if shift:
                    date = vals.get('date') or record.date
                    time_from = time(int(shift.time_from), int((shift.time_from % 1) * 60))
                    time_to = time(int(shift.time_to), int((shift.time_to % 1) * 60))
                    date_start = datetime.combine(fields.Date.from_string(date), time_from)
                    date_stop = datetime.combine(fields.Date.from_string(date), time_to)
                    # Añadir 5 horas
                    date_start += timedelta(hours=5)
                    date_stop += timedelta(hours=5)

                    vals['date_start'] = date_start
                    vals['date_stop'] = date_stop
            super(EmployeeWorkDay, record).write(vals)
        return True

    def name_get(self):
        res = []
        for rec in self:
            name = str(rec.employee_id.name) + " " + str(rec.date)
            res.append((rec.id, name))
        return res


class EmployeeWeekEnd(models.Model):
    _name = "employee.week.end"
    _description = "Employee Week End"
    _rec_name = 'allocation_id'

    allocation_id = fields.Many2one('employee.shift.allocation', ondelete='cascade', string='Asignación de turnos')
    week_off_id = fields.Many2one('employee.week.off', string='Day of Week')
    week_day_id = fields.Many2one('employee.week.day', string='Number of Week')
    shift_id = fields.Many2one('employee.shift', string='Shift', related='allocation_id.shift_id', store=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', related='allocation_id.employee_id', store=True)
    user_id = fields.Many2one('res.users', string='Responsible', related='allocation_id.shift_id.user_id', store=True)
    date = fields.Date(string='Date of Week')

    def name_get(self):
        res = []
        for rec in self:
            name = str(rec.employee_id.name) + " " + str(rec.date)
            res.append((rec.id, name))
        return res


class ReportShiftAllocation(models.AbstractModel):
    _name = 'report.employee_shift_scheduling_app.shift_report'
    _description = 'Shift Allocation Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['employee.shift.allocation'].browse(docids)
        for doc in docs:
            query_times = self.env['hr.attendance'].search(
                [('employee_id', '=', doc.employee_id.id)],
                order='create_date asc'
            )
            user_tz_str = query_times.employee_id.resource_calendar_id.tz or 'UTC'
            system_tz = timezone(user_tz_str)
            if query_times:
                for days_work in doc.workday_ids:
                    hours_in = ""
                    hours_out = ""
                    hours_worked = False
                    for query in query_times:
                        if (days_work.date.strftime("%Y-%m-%d") == (query.check_in).strftime("%Y-%m-%d")
                                and query.employee_id.id == days_work.employee_id.id):
                            hours_in+= str(query.check_in.astimezone(system_tz).strftime('%H:%M:%S')) + ' a '
                        if (days_work.date.strftime("%Y-%m-%d") == (query.check_out).strftime("%Y-%m-%d")
                                and query.employee_id.id == days_work.employee_id.id):
                            hours_out += str(query.check_out.astimezone(system_tz).strftime('%H:%M:%S')) + ' a '
                            hours_worked += query.worked_hours
                        if query.worked_hours and hours_worked :
                            vals = {
                                'worked_hours': self.round_down(hours_worked, 2),
                            }
                            days_work.write(vals)

                    days_work.write({
                        'time_in': self.remove_last(hours_in),
                    })
                    days_work.write({
                        'time_out': self.remove_last(hours_out),
                    })



        return {
            'doc_ids': docids,
            'doc_model': 'employee.shift.allocation',
            'docs': docs,
        }

    def remove_last(self,s):
        if len(s) > 1 and s[-2:] == 'a ':
            return s[:-2]
        return s

    def round_down(self,value, decimals):
        factor = 10 ** decimals
        return math.floor(value * factor) / factor
