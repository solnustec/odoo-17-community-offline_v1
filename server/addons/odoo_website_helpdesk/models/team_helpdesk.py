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

class TeamHelpDesk(models.Model):
    """Helpdesk team"""
    _name = 'team.helpdesk'
    _description = 'Helpdesk Team'

    name = fields.Char('Nombre', help='Nombre del equipo de la mesa de ayuda')
    team_lead_id = fields.Many2one('res.users', string='Jefe de equipo',
                                   help='Nombre del líder del equipo')  # Eliminamos el dominio
    member_ids = fields.Many2many('res.users', string='Miembros',
                                  help='Miembros del equipo')  # Eliminamos el dominio
    email = fields.Char('Email', help='Email del miembro del equipo.')
    project_id = fields.Many2one('project.project',
                                 string='Proyecto',
                                 help='Equipo de soporte técnico relacionado con proyectos.')
    create_task = fields.Boolean(string="Crear tarea",
                                 help="Tarea creada o no")

    @api.onchange('team_lead_id')
    def _onchange_team_lead_id(self):
        """Members selection function"""
        fetch_members = self.env['res.users'].search([])
        filtered_members = fetch_members.filtered(
            lambda x: x.id != self.team_lead_id.id)
        return {'domain': {'member_ids': [('id', '=', filtered_members.ids)]}}