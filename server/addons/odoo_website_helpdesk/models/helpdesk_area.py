# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HelpdeskArea(models.Model):
    _name = 'helpdesk.area'
    _description = 'Área de Ticket de Soporte'
    _order = 'name asc'

    name = fields.Char('Nombre', required=True, translate=True)
    subarea_ids = fields.One2many('helpdesk.subarea', 'area_id', string='Subáreas')
