# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HelpdeskSubarea(models.Model):
    _name = 'helpdesk.subarea'
    _description = 'Subárea de Ticket de Soporte'
    _order = 'area_id, name asc'

    name = fields.Char('Nombre', required=True, translate=True)
    area_id = fields.Many2one('helpdesk.area', string='Área', required=True, ondelete='cascade')