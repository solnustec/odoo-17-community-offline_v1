# -*- coding: utf-8 -*-
##############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Dhanya B (odoo@cybrosys.com)
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
from odoo import fields, models, _
from odoo.exceptions import UserError


class TicketStage(models.Model):
    """Stage Ticket model """
    _name = 'ticket.stage'
    _description = 'Ticket Stage'
    _order = 'sequence, id'
    _fold_name = 'fold'

    name = fields.Char('Nombre', help='Nombre de la etapa del ticket')
    active = fields.Boolean(string='Activo', default=True,
                            help='Opción activa para la etapa del ticket')
    sequence = fields.Integer(string='Secuencia', default=50,
                              help='Número de secuencia de la etapa del ticket')
    closing_stage = fields.Boolean('Etapa de cierre', default=False,
                                   help='Indica si es la etapa de cierre del ticket')
    cancel_stage = fields.Boolean('Etapa de cancelación', default=False,
                                  help='Indica si es la etapa de cancelación del ticket')
    starting_stage = fields.Boolean('Etapa inicial', default=False,
                                    help='Indica si es la etapa inicial del ticket')
    folded = fields.Boolean('Colapsado en Kanban', default=False,
                            help='Etapa colapsada en vista Kanban')
    template_id = fields.Many2one('mail.template',
                                  help='Plantilla de correo',
                                  string='Plantilla',
                                  domain="[('model', '=', 'ticket.helpdesk')]")
    group_ids = fields.Many2many('res.groups', help='Grupos de usuarios',
                                 string='Grupos')
    fold = fields.Boolean(string='Colapsar', help='Opción de colapsar en el ticket')

    def unlink(self):
        """Unlinking Function to unlink the stage"""
        for rec in self:
            tickets = rec.search([])
            sequence = tickets.mapped('sequence')
            lowest_sequence = tickets.filtered(
                lambda x: x.sequence == min(sequence))
            if self.name == "Draft":
                raise UserError(_("Cannot Delete This Stage"))
            if rec == lowest_sequence:
                raise UserError(_("Cannot Delete '%s'" % (rec.name)))
            else:
                res = super().unlink()
                return res
