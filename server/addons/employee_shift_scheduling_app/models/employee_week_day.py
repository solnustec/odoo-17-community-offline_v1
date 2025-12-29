# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class EmployeeWeekDay(models.Model):
    _name = "employee.week.day"
    _description = "Employee Week Day"
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Day', tracking=True)
    day_no = fields.Integer(string='No')
