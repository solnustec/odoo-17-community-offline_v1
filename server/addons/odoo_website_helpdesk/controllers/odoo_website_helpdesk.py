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
import datetime as DT
from odoo import http
from odoo.http import request


class HelpDeskDashboard(http.Controller):
    """Controller for handling Help Desk dashboard requests."""

    @http.route(['/helpdesk_dashboard'], type='json', auth="public")
    def helpdesk_dashboard(self):
        """Retrieves statistics for tickets in different stages.
        Returns:dict: Dashboard statistics including counts and IDs for each
        stage.
        """
        stage_names = ['Bandeja de Entrada', 'En Curso', 'En Espera', 'Finalizado', 'Cancelado']

        stage_ids = {
            name: request.env['ticket.stage'].search([('name', '=', name)],
                                                     limit=1).id for name in
            stage_names}
        new_stages = [stage_ids['Bandeja de entrada']]
        def get_ticket_data(stage_ids):
            tickets = request.env["ticket.helpdesk"].search(
                [('stage_id', 'in', stage_ids)])
            return len(tickets), [ticket.id for ticket in tickets]
        dashboard_values = {
            'new': (get_ticket_data(new_stages))[0],
            'new_id': (get_ticket_data(new_stages))[1],
            'in_progress': (get_ticket_data([stage_ids['En curso']]))[0],
            'in_progress_id': (get_ticket_data([stage_ids['En curso']]))[1],
            'canceled': (get_ticket_data([stage_ids['Cancelado']]))[0],
            'canceled_id': (get_ticket_data([stage_ids['Cancelado']]))[1],
            'done': (get_ticket_data([stage_ids['Listo']]))[0],
            'done_id': (get_ticket_data([stage_ids['Listo']]))[1],
            'closed': (get_ticket_data([stage_ids['Cerrado']]))[0],
            'closed_id': (get_ticket_data([stage_ids['Cerrado']]))[1]}
        return dashboard_values

    def helpdesk_dashboard_week(self):
        """ Retrieves statistics for tickets created in the past week.
        Returns:
        dict: Dashboard statistics including counts and IDs for each stage."""
        today = DT.date.today()
        week_ago = str(today - DT.timedelta(days=7)) + ' '
        stage_names = ['Bandeja de Entrada', 'En Curso', 'En Espera', 'Finalizado', 'Cancelado']
        stages = {
            name: request.env['ticket.stage'].search([('name', '=', name)],
                                                     limit=1).id for name in
            stage_names}
        stage_ids = [stages['Bandeja de entrada']]
        def get_ticket_data(stage_id):
            count = request.env["ticket.helpdesk"].search_count(
                [('stage_id', '=', stage_id), ('create_date', '>', week_ago)])
            ids = request.env["ticket.helpdesk"].search(
                [('stage_id', '=', stage_id),
                 ('create_date', '>', week_ago)]).ids
            return count, ids
        new_count, new_ids = get_ticket_data(stage_ids)
        in_progress_count, in_progress_ids = get_ticket_data(
            stages['En curso'])
        canceled_count, canceled_ids = get_ticket_data(stages['Cancelado'])
        done_count, done_ids = get_ticket_data(stages['Listo'])
        closed_count, closed_ids = get_ticket_data(stages['Cerrado'])
        dashboard_values = {
            'new': new_count,
            'in_progress': in_progress_count,
            'canceled': canceled_count,
            'done': done_count,
            'closed': closed_count,
            'new_id': new_ids,
            'in_progress_id': in_progress_ids,
            'canceled_id': canceled_ids,
            'done_id': done_ids,
            'closed_id': closed_ids,
        }
        return dashboard_values

    @http.route(['/helpdesk_dashboard_month'], type='json', auth="public")
    def helpdesk_dashboard_month(self):
        """Retrieves statistics for tickets created in the past month.
        Returns:
          dict: Dashboard statistics including counts and IDs for each stage."""
        today = DT.date.today()
        month_ago = today - DT.timedelta(days=30)
        week_ago = str(month_ago) + ' '
        stages = request.env['ticket.stage'].search([('name', 'in',
                                                      ['Bandeja de Entrada', 'En Curso', 'En Espera', 'Finalizado', 'Cancelado'])])
        stage_ids = {stage.name: stage.id for stage in stages}
        def get_stage_data(stage_names):
            stage_ids_list = [stage_ids[name] for name in stage_names]
            tickets = request.env["ticket.helpdesk"].search(
                [('stage_id', 'in', stage_ids_list),
                 ('create_date', '>', week_ago)])
            return len(tickets), [ticket.id for ticket in tickets]
        new_count, new_ids = get_stage_data(['Bandeja de entrada'])
        in_progress_count, in_progress_ids = get_stage_data(['En curso'])
        canceled_count, canceled_ids = get_stage_data(['Cancelado'])
        done_count, done_ids = get_stage_data(['Listo'])
        closed_count, closed_ids = get_stage_data(['Cerrado'])
        dashboard_values = {
            'new': new_count,
            'in_progress': in_progress_count,
            'canceled': canceled_count,
            'done': done_count,
            'closed': closed_count,
            'new_id': new_ids,
            'in_progress_id': in_progress_ids,
            'canceled_id': canceled_ids,
            'done_id': done_ids,
            'closed_id': closed_ids,
        }
        return dashboard_values

    @http.route(['/helpdesk_dashboard_year'], type='json', auth="public")
    def helpdesk_dashboard_year(self):
        """Retrieves statistics for tickets created in the past year.
        Returns:
            dict: Dashboard statistics including counts and IDs for each stage.
        """
        today = DT.date.today()
        year_ago = today - DT.timedelta(days=360)
        stages = ['Bandeja de Entrada', 'En Curso', 'En Espera', 'Finalizado', 'Cancelado']
        stage_ids = {
            stage: request.env['ticket.stage'].search([('name', '=', stage)],
                                                      limit=1).id for stage in
            stages}
        def get_ticket_data(stage_name):
            stage_id = stage_ids[stage_name]
            tickets = request.env["ticket.helpdesk"].search(
                [('stage_id', '=', stage_id), ('create_date', '>', year_ago)])
            return len(tickets), [ticket.id for ticket in tickets]
        dashboard_values = {}
        for stage in stages:
            count, ids = get_ticket_data(stage)
            dashboard_values[stage.lower()] = count
            dashboard_values[f'{stage.lower()}_id'] = ids
        return dashboard_values
