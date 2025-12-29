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
from odoo import api, fields, models


class MergeTicket(models.Model):
    """Tickets merging class"""
    _name = 'merge.ticket'
    _description = 'Merging the selected tickets'
    _rec_name = 'support_ticket_id'

    user_id = fields.Many2one('res.partner',
                              string='Usuario responsable',
                              help='Nombre de usuario de la persona responsable.',
                              default=lambda self: self.env.user.partner_id.id)
    support_team_id = fields.Many2one('team.helpdesk',
                                      string='Equipo de soporte',
                                      help='Nombre del equipo de soporte.')
    customer_id = fields.Many2one('res.partner', string='Cliente',
                                  help='Nombre del Cliente ')
    support_ticket_id = fields.Many2one('ticket.helpdesk',
                                        string='Ticket de soporte',
                                        help="Nombre del ticket de soporte")
    new_ticket = fields.Boolean(string='¿Crear nuevo ticket?',
                                help='Crear nuevos tickets o no.',
                                default=False)
    subject = fields.Char(string='Asunto', help='Ingrese el nuevo asunto del ticket')
    merge_reason = fields.Char(string='Motivo de fusión',
                               help='Motivo de la fusión de los tickets. ')
    support_ticket_ids = fields.One2many('support.ticket',
                                         'support_ticket_id',
                                         string='Tickets de soporte',
                                         help='Tickets fusionados')
    active = fields.Boolean(string='Deshabilitar registro', help='Deshabilitar registro',
                            default=True)

    def default_get(self, fields_list):
        """Override the default_get method to provide default values for fields
        when creating a new record."""
        defaults = super(MergeTicket, self).default_get(fields_list)
        active_ids = self._context.get('active_ids', [])
        selected_tickets = self.env['ticket.helpdesk'].browse(active_ids)
        customer_ids = selected_tickets.mapped('customer_id')
        subjects = selected_tickets.mapped('subject')
        display_names = selected_tickets.mapped('display_name')
        helpdesk_team = selected_tickets.mapped('team_id')
        descriptions = selected_tickets.mapped('description')
        if len(customer_ids):
            defaults.update({
                'customer_id': customer_ids[0].id,
                'support_team_id': helpdesk_team,
                'support_ticket_ids': [(0, 0, {
                    'subject': subject,
                    'display_name': display_name,
                    'description': description,
                }) for subject, display_name, description in
                                       zip(subjects, display_names,
                                           descriptions)]
            })
        return defaults

    def action_merge_ticket(self):
        """Merging the tickets or creating new tickets"""
        if self.new_ticket:
            description = "\n\n".join(
                f"{ticket.subject}\n{'-' * len(ticket.subject)}\n{ticket.description}"
                for ticket in self.support_ticket_ids
            )
            self.env['ticket.helpdesk'].create({
                'subject': self.subject,
                'description': description,
                'customer_id': self.customer_id.id,
                'team_id': self.support_team_id.id,
            })
        else:
            if len(self.support_ticket_ids):
                description = "\n\n".join(
                    f"{ticket.subject}\n{'-' * len(ticket.subject)}\n{ticket.description}"
                    for ticket in self.support_ticket_ids
                )
                self.support_ticket_id.write({
                    'description': description,
                    'merge_ticket_invisible': True,
                    'merge_count': len(self.support_ticket_ids),
                })

    @api.onchange('support_ticket_id')
    def _onchange_support_ticket_id(self):
        """Onchange function to add the support ticket id."""
        self.support_ticket_ids.write({
            'merged_ticket': self.support_ticket_id
        })
