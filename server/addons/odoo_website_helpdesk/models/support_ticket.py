# -*- coding: utf-8 -*-
##############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Dhanya Babu (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from odoo import fields, models


class SupportTicket(models.Model):
    """Creating onetoMany model"""
    _name = 'support.ticket'
    _description = 'Support Tickets'

    subject = fields.Char(string='Asunto', help='Asunto de las entradas fusionadas.')
    display_name = fields.Char(string='Nombre para mostrar',
                               help='Nombre para mostrar de los tickets fusionados.')
    description = fields.Char(string='Descripción',
                              help='Descripción de los tickets.')
    support_ticket_id = fields.Many2one('merge.ticket',
                                        string='Tickets de soporte',
                                        help='Tickets de soporte')
    merged_ticket = fields.Integer(string='ID de ticket fusionado',
                                   help='Almacenamiento del ID del ticket fusionado')
