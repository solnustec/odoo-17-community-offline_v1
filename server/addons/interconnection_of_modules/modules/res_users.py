# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, Command

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    """
    Extensión de res.users para sincronización automática bidireccional
    entre allowed_pos y basic_employee_ids en pos.config.

    Esto elimina la necesidad de doble configuración manual.
    """
    _inherit = 'res.users'

    def write(self, vals):
        """
        Override write para sincronizar automáticamente basic_employee_ids
        cuando se modifica allowed_pos.
        """
        res = super(ResUsers, self).write(vals)

        # Evitar recursión usando contexto
        if 'allowed_pos' in vals and not self.env.context.get('skip_pos_sync'):
            self._sync_employee_to_pos_config()

        return res

    def _sync_employee_to_pos_config(self):
        """
        Sincroniza el empleado asociado al usuario con los POS configurados
        en allowed_pos. Agrega automáticamente el empleado a basic_employee_ids.

        Flujo:
        - Usuario tiene allowed_pos = [POS1, POS2]
        - Empleado del usuario se agrega a basic_employee_ids de POS1 y POS2
        - Empleado se elimina de otros POS donde ya no tiene acceso
        """
        PosConfig = self.env['pos.config'].sudo()

        for user in self:
            # Obtener el empleado asociado al usuario
            employee = user.employee_id
            if not employee:
                continue

            allowed_pos_ids = user.allowed_pos.ids

            # Encontrar todos los POS donde el empleado está asignado actualmente
            current_pos_configs = PosConfig.search([
                ('basic_employee_ids', 'in', [employee.id])
            ])
            current_pos_ids = current_pos_configs.ids

            # POS a los que hay que agregar el empleado
            pos_to_add = set(allowed_pos_ids) - set(current_pos_ids)
            # POS de los que hay que remover el empleado
            pos_to_remove = set(current_pos_ids) - set(allowed_pos_ids)

            # Agregar empleado a nuevos POS
            if pos_to_add:
                pos_configs_add = PosConfig.browse(list(pos_to_add))
                for pos_config in pos_configs_add:
                    pos_config.write({
                        'basic_employee_ids': [Command.link(employee.id)]
                    })
                _logger.info(
                    "Empleado %s agregado automáticamente a POS: %s",
                    employee.name, pos_configs_add.mapped('name')
                )

            # Remover empleado de POS donde ya no tiene acceso
            if pos_to_remove:
                pos_configs_remove = PosConfig.browse(list(pos_to_remove))
                for pos_config in pos_configs_remove:
                    pos_config.write({
                        'basic_employee_ids': [Command.unlink(employee.id)]
                    })
                _logger.info(
                    "Empleado %s removido automáticamente de POS: %s",
                    employee.name, pos_configs_remove.mapped('name')
                )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create para sincronizar después de crear usuario con allowed_pos.
        """
        users = super(ResUsers, self).create(vals_list)

        for user, vals in zip(users, vals_list):
            if vals.get('allowed_pos'):
                user._sync_employee_to_pos_config()

        return users
