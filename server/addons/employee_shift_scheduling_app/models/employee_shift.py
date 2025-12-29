# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class EmployeeShift(models.Model):
    _name = "employee.shift"
    _description = "Employee Shift"
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Day', tracking=True)
    shift_type_id = fields.Many2one('shift.type', string='Shift Type', tracking=True)
    time_from = fields.Float(string='Desde la hora', tracking=True)
    time_to = fields.Float(string='Hasta la hora', tracking=True)
    overtime = fields.Float(string='Overtime Threshold')
    late = fields.Float(string='Late Threshold')
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id,
                                 tracking=True)
    resource_calendar_id = fields.Many2one('resource.calendar', string='Working Hours')
