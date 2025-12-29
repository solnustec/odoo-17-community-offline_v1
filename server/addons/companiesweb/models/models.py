# -*- coding: utf-8 -*-

from odoo import models, fields, api

class Province(models.Model):
    _inherit = 'res.company'

    provincia = fields.Char(string='Provincia')


