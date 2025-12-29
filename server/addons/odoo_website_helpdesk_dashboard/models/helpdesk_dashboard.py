# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
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
#############################################################################
import calendar
from odoo import api, models


class TicketHelpdesk(models.Model):
    """ Inherited class to get help desk ticket details...."""
    _inherit = 'ticket.helpdesk'

    @api.model
    def check_user_group(self):
        """Checking user group"""
        user = self.env.user
        if user.has_group('base.group_user'):
            return True
        return False

    @api.model
    def get_tickets_count(self, domain=None):
        if domain is None:
            domain = []

        # Get total number of tickets to calculate percentages
        total_tickets = self.env['ticket.helpdesk'].search_count(domain)

        # Get counts for each stage
        tickets_new_count = self.env['ticket.helpdesk'].search_count(
            [['stage_id.name', '=', 'Bandeja de Entrada']] + domain)
        tickets_in_progress_count = self.env['ticket.helpdesk'].search_count(
            [['stage_id.name', '=', 'En Curso']] + domain)
        tickets_in_wait_count = self.env['ticket.helpdesk'].search_count(
            [['stage_id.name', '=', 'En Espera']] + domain)
        tickets_done_count = self.env['ticket.helpdesk'].search_count(
            [['stage_id.name', '=', 'Resuelto']] + domain)
        tickets_cancelled_count = self.env['ticket.helpdesk'].search_count(
            [['stage_id.name', '=', 'Cancelado']] + domain)

        # Get counts for each priority level
        low_count = self.env['ticket.helpdesk'].search_count([['priority', '=', '1']] + domain)
        normal_count = self.env['ticket.helpdesk'].search_count([['priority', '=', '2']] + domain)
        high_count = self.env['ticket.helpdesk'].search_count([['priority', '=', '3']] + domain)
        very_high_count = self.env['ticket.helpdesk'].search_count([['priority', '=', '4']] + domain)

        # Calculate percentages (avoid division by zero)
        if total_tickets > 0:
            low_count1 = round((low_count / total_tickets) * 100, 2)
            normal_count1 = round((normal_count / total_tickets) * 100, 2)
            high_count1 = round((high_count / total_tickets) * 100, 2)
            very_high_count1 = round((very_high_count / total_tickets) * 100, 2)
        else:
            low_count1 = 0
            normal_count1 = 0
            high_count1 = 0
            very_high_count1 = 0

        tickets = self.env['ticket.helpdesk'].search(
            [['stage_id.name', '=', 'Bandeja de Entrada']] + domain)
        p_tickets = [ticket.name for ticket in tickets]

        values = {
            'inbox_count': tickets_new_count,
            'progress_count': tickets_in_progress_count,
            'wait_count': tickets_in_wait_count,
            'done_count': tickets_done_count,
            'cancelled_count': tickets_cancelled_count,
            'p_tickets': p_tickets,
            'low_count1': low_count1,
            'normal_count1': normal_count1,
            'high_count1': high_count1,
            'very_high_count1': very_high_count1,
        }
        return values

    @api.model
    def get_tickets_view(self, domain=None):
        """Devuelve los tickets asignados por usuario"""
        if domain is None:
            domain = []

        # Obtener el grupo de usuarios asignables
        group = self.env.ref('odoo_website_helpdesk.helpdesk_assigned_user', raise_if_not_found=False)
        if not group:
            return {'error': 'Grupo no encontrado'}

        # Obtener los usuarios en el grupo
        assigned_users = self.env['res.users'].search([('groups_id', 'in', group.id)])

        result = []
        for user in assigned_users:
            count = self.search_count([('assigned_user_ids', 'in', [user.id])] + domain)
            result.append({
                'id': user.id,
                'name': user.name,
                'ticket_count': count,
            })

        return {
            'assigned_users_ticket_counts': result
        }

    @api.model
    def get_ticket_month_pie(self, domain=None):
        """For pie chart"""
        if domain is None:
            domain = []

        month_count = []
        month_value = []
        tickets = self.env['ticket.helpdesk'].search(domain)
        for rec in tickets:
            month = rec.create_date.month
            if month not in month_value:
                month_value.append(month)
            month_count.append(month)
        month_val = []
        for index in range(len(month_value)):
            value = month_count.count(month_value[index])
            month_name = calendar.month_name[month_value[index]]
            month_val.append({'label': month_name, 'value': value})
        name = []
        for record in month_val:
            name.append(record.get('label'))
        count = []
        for record in month_val:
            count.append(record.get('value'))
        month = [count, name]
        return month

    @api.model
    def get_team_ticket_count_pie(self, domain=None):
        """For bar chart"""
        if domain is None:
            domain = []

        ticket_count = []
        team_list = []
        tickets = self.env['ticket.helpdesk'].search(domain)
        for rec in tickets:
            if rec.team_id:
                team = rec.team_id.name
                if team not in team_list:
                    team_list.append(team)
                ticket_count.append(team)
        team_val = []
        for index in range(len(team_list)):
            value = ticket_count.count(team_list[index])
            team_name = team_list[index]
            team_val.append({'label': team_name, 'value': value})
        name = []
        for record in team_val:
            name.append(record.get('label'))
        count = []
        for record in team_val:
            count.append(record.get('value'))
        team = [count, name]
        return team