from odoo import http
from odoo.http import request

class HelpdeskController(http.Controller):

    @http.route('/helpdesk/assigned_users', type='json', auth='user')
    def get_assigned_users(self):
        try:
            group = request.env.ref('odoo_website_helpdesk.helpdesk_assigned_user')
        except ValueError:
            return {'error': 'Grupo no encontrado'}

        users = request.env['res.users'].search([('groups_id', 'in', group.id)])
        return [{'id': u.id, 'name': u.name} for u in users]

    @http.route('/helpdesk/employees', type='json', auth='user')
    def get_employees(self):
        try:
            group = request.env.ref('odoo_website_helpdesk.helpdesk_employee')
        except ValueError:
            return {'error': 'Grupo no encontrado'}

        employees = request.env['res.users'].search([('groups_id', 'in', group.id)])
        return [{'id': emp.id, 'name': emp.name} for emp in employees]
