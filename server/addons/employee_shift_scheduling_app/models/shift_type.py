# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ShiftType(models.Model):
    _name = "shift.type"
    _description = "Shift type"
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', tracking=True)
    work_hours = fields.Float(string='Work Hours', tracking=True)
