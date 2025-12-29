#-*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, time, timedelta
from collections import defaultdict
import pytz

from odoo import models, fields, api, exceptions, _



class HrAttendance(models.Model):
    _name = 'hr.attendance.inconsistencies'
    _description = 'HR Attendance Inconsistencies'

    employee_id = fields.Many2one('hr.employee', string='Employee')
    date = fields.Date(string="Entrada")
    count_inconsistencies = fields.Integer(string="Count", default=0)




