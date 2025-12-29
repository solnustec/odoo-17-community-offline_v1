#-*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, time, timedelta
from collections import defaultdict
import pytz

from odoo import models, fields, api, exceptions, _



class HrAttendance(models.Model):
    _name = 'hr.work.entry.delays'
    _description = 'HR Attendance Delays'

    employee_id = fields.Many2one('hr.employee', string='Employee')
    date_mount_start = fields.Date(string="Desde")
    date_mount_end = fields.Date(string="Hasta")
    count_delays = fields.Integer(string="Count", default=0)

    def download_xlsx_repor(self):
        download_url = '/report-delays/download-xlsx/{}'.format(self.id)

        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }


