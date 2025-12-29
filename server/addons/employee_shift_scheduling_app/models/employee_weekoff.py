# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class EmployeeWeekOff(models.Model):
    _name = "employee.week.off"
    _description = "Employee Weekoff"
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', tracking=True)
    day_no = fields.Integer(string='Day Number')
