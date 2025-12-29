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


class ResConfigSettings(models.TransientModel):
    """Inheriting the res config settings model"""
    _inherit = 'res.config.settings'

    show_create_task = fields.Boolean(string="Crear tareas",
                                      config_parameter='odoo_website_helpdesk.show_create_task',
                                      help='Habilite esta opción para que los usuarios '
                                           'puedan crear tareas directamente desde '
                                           'el módulo de soporte técnico. Al activarla,'
                                           ' los usuarios podrán generar y asignar tareas '
                                           'como parte de su flujo de trabajo dentro de la '
                                           'interfaz del soporte técnico.')
    show_category = fields.Boolean(string="Categoría",
                                   config_parameter='odoo_website_helpdesk.show_category',
                                   help='Habilite esta opción para mostrar el campo de'
                                        ' categoría en los tickets del Soporte técnico.'
                                        ' Esto puede ser útil para organizar y filtrar los '
                                        'tickets según su categoría..',
                                   implied_group='odoo_website_helpdesk.group_show_category')
    product_website = fields.Boolean(string="Producto en el sitio web",
                                     config_parameter='odoo_website_helpdesk.product_website',
                                     help='Producto en el sitio web')
    auto_close_ticket = fields.Boolean(string="Cierre automático de tickets",
                                       config_parameter='odoo_website_helpdesk.auto_close_ticket',
                                       help='Ticket de cierre automático')
    no_of_days = fields.Integer(string="Número de días",
                                config_parameter='odoo_website_helpdesk.no_of_days',
                                help='Número de días')
    closed_stage_id = fields.Many2one(
        'ticket.stage', string='Etapa de cierre',
        help='Etapa de cierre del ticket.',
        config_parameter='odoo_website_helpdesk.closed_stage_id')

    reply_template_id = fields.Many2one('mail.template',
                                        domain="[('model', '=', 'ticket.helpdesk')]",
                                        config_parameter='odoo_website_helpdesk.reply_template_id',
                                        help='Plantilla de respuesta del ticket del Soporte técnico.')
    helpdesk_menu_show = fields.Boolean('Menú del Soporte técnico',
                                        config_parameter=
                                        'odoo_website_helpdesk.helpdesk_menu_show',
                                        help='Menú del Soporte técnico')

    @api.onchange('closed_stage_id')
    def _onchange_closed_stage_id(self):
        """Closing stage function"""
        if self.closed_stage_id:
            stage = self.closed_stage_id.id
            in_stage = self.env['ticket.stage'].search([('id', '=', stage)])
            not_in_stage = self.env['ticket.stage'].search(
                [('id', '!=', stage)])
            in_stage.closing_stage = True
            for each in not_in_stage:
                each.closing_stage = False

    @api.constrains('show_category')
    def _constrains_show_category_subcategory(self):
        """Show category and the sub category"""
        if self.show_category:
            group_cat = self.env.ref(
                'odoo_website_helpdesk.group_show_category')
            group_cat.write({
                'users': [(4, self.env.user.id)]
            })

        else:
            group_cat = self.env.ref(
                'odoo_website_helpdesk.group_show_category')
            group_cat.write({
                'users': [(5, False)]
            })
