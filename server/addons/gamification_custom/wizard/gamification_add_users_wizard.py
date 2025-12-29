# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GamificationAddUsersWizard(models.TransientModel):
    _name = 'gamification.add.users.wizard'
    _description = 'Agregar Usuarios al Grupo de Gamificación'

    selection_type = fields.Selection([
        ('all_employees', 'Todos los empleados'),
        ('by_department', 'Por departamento'),
        ('manual', 'Selección manual'),
    ], string='Tipo de selección', default='all_employees', required=True)

    department_ids = fields.Many2many(
        'hr.department',
        string='Departamentos',
        help='Seleccione los departamentos cuyos empleados serán agregados'
    )

    user_ids = fields.Many2many(
        'res.users',
        string='Usuarios',
        domain=[('share', '=', False)],
        help='Seleccione los usuarios a agregar manualmente'
    )

    preview_user_ids = fields.Many2many(
        'res.users',
        'gamification_wizard_preview_users_rel',
        string='Usuarios a agregar',
        compute='_compute_preview_users',
        store=False
    )

    preview_count = fields.Integer(
        string='Cantidad de usuarios',
        compute='_compute_preview_users'
    )

    already_in_group_count = fields.Integer(
        string='Ya en el grupo',
        compute='_compute_preview_users'
    )

    @api.depends('selection_type', 'department_ids', 'user_ids')
    def _compute_preview_users(self):
        group = self.env.ref('gamification_custom.group_gamification_user', raise_if_not_found=False)

        for wizard in self:
            users = self.env['res.users']
            already_count = 0

            if wizard.selection_type == 'all_employees':
                # Obtener todos los usuarios que tienen empleado asociado
                employees = self.env['hr.employee'].search([('active', '=', True)])
                users = employees.mapped('user_id').filtered(lambda u: u.active and not u.share)

            elif wizard.selection_type == 'by_department':
                if wizard.department_ids:
                    employees = self.env['hr.employee'].search([
                        ('department_id', 'in', wizard.department_ids.ids),
                        ('active', '=', True)
                    ])
                    users = employees.mapped('user_id').filtered(lambda u: u.active and not u.share)

            elif wizard.selection_type == 'manual':
                users = wizard.user_ids

            # Contar los que ya están en el grupo
            if group and users:
                already_count = len(users.filtered(lambda u: group in u.groups_id))

            wizard.preview_user_ids = users
            wizard.preview_count = len(users)
            wizard.already_in_group_count = already_count

    def action_add_users(self):
        """Agregar los usuarios seleccionados al grupo de gamificación"""
        self.ensure_one()

        group = self.env.ref('gamification_custom.group_gamification_user', raise_if_not_found=False)
        if not group:
            raise UserError(_('No se encontró el grupo "Usuario Gamificación". Verifique que el módulo esté correctamente instalado.'))

        users_to_add = self.preview_user_ids.filtered(lambda u: group not in u.groups_id)

        if not users_to_add:
            raise UserError(_('No hay usuarios nuevos para agregar. Todos los usuarios seleccionados ya están en el grupo.'))

        # Agregar usuarios al grupo
        group.write({
            'users': [(4, user.id) for user in users_to_add]
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Usuarios agregados'),
                'message': _('Se agregaron %s usuarios al grupo "Usuario Gamificación".') % len(users_to_add),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_users_in_group(self):
        """Ver los usuarios que ya están en el grupo"""
        group = self.env.ref('gamification_custom.group_gamification_user', raise_if_not_found=False)
        if not group:
            raise UserError(_('No se encontró el grupo "Usuario Gamificación".'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Usuarios en Grupo Gamificación'),
            'res_model': 'res.users',
            'view_mode': 'tree,form',
            'domain': [('groups_id', 'in', [group.id])],
            'context': {'create': False},
        }
