# -*- coding: utf-8 -*-

import logging

from odoo import models, api, fields, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    """
    Extensión de pos.config para sincronización automática bidireccional
    entre basic_employee_ids, allowed_pos y department_id.

    Funcionalidades:
    1. Cuando se modifica basic_employee_ids → actualiza allowed_pos del usuario
    2. Cuando se asigna department_id → agrega automáticamente todos los empleados
       del departamento a basic_employee_ids y allowed_pos
    """
    _inherit = 'pos.config'

    department_id = fields.Many2one(
        'hr.department',
        string='Departamento',
        help='Departamento asociado a este Punto de Venta. '
             'Los empleados de este departamento serán asignados automáticamente.',
        tracking=True,
    )

    def write(self, vals):
        """
        Override write para sincronizar automáticamente:
        - allowed_pos cuando se modifica basic_employee_ids
        - empleados cuando se modifica department_id
        """
        # Guardar departamentos anteriores para detectar cambios
        old_departments = {pos.id: pos.department_id.id for pos in self}

        res = super(PosConfig, self).write(vals)

        # Sincronizar allowed_pos cuando cambian los empleados
        if 'basic_employee_ids' in vals and not self.env.context.get('skip_user_sync'):
            self._sync_allowed_pos_from_employees()

        # Sincronizar empleados cuando cambia el departamento
        if 'department_id' in vals and not self.env.context.get('skip_dept_sync'):
            for pos_config in self:
                old_dept_id = old_departments.get(pos_config.id)
                new_dept_id = pos_config.department_id.id if pos_config.department_id else False

                if old_dept_id != new_dept_id:
                    # Remover empleados del departamento anterior
                    if old_dept_id:
                        pos_config._remove_employees_from_old_department(old_dept_id)
                    # Agregar empleados del nuevo departamento
                    if new_dept_id:
                        pos_config._sync_employees_from_department()

        return res

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create para sincronizar empleados si se crea con departamento.
        """
        pos_configs = super(PosConfig, self).create(vals_list)

        for pos_config in pos_configs:
            if pos_config.department_id:
                pos_config._sync_employees_from_department()

        return pos_configs

    def _sync_allowed_pos_from_employees(self):
        """
        Sincroniza allowed_pos de los usuarios cuando se modifican
        los empleados asignados al POS.

        Flujo:
        - POS tiene basic_employee_ids = [Emp1, Emp2]
        - Usuario de Emp1 y Emp2 reciben este POS en su allowed_pos
        """
        for pos_config in self:
            employees = pos_config.basic_employee_ids

            for employee in employees:
                user = employee.user_id
                if not user:
                    continue

                if pos_config.id not in user.allowed_pos.ids:
                    user.sudo().with_context(skip_pos_sync=True).write({
                        'allowed_pos': [Command.link(pos_config.id)]
                    })
                    _logger.info(
                        "POS '%s' agregado automáticamente a usuario '%s'",
                        pos_config.name, user.name
                    )

    def _sync_employees_from_department(self):
        """
        Sincroniza todos los empleados del departamento asignado al POS.

        Flujo:
        - POS tiene department_id = "Sucursal Norte"
        - Busca todos los empleados con department_id = "Sucursal Norte" Y que tengan user_id
        - Los agrega a basic_employee_ids
        - Actualiza allowed_pos de sus usuarios
        """
        self.ensure_one()

        if not self.department_id:
            return

        # Buscar empleados del departamento que tengan usuario vinculado
        employees = self.env['hr.employee'].sudo().search([
            ('department_id', '=', self.department_id.id),
            ('user_id', '!=', False),
        ])

        if not employees:
            _logger.debug(
                "No se encontraron empleados con usuario para departamento '%s'",
                self.department_id.name
            )
            return

        # Agregar empleados al POS
        for employee in employees:
            if employee.id not in self.basic_employee_ids.ids:
                self.with_context(skip_user_sync=True, skip_dept_sync=True).write({
                    'basic_employee_ids': [Command.link(employee.id)]
                })

        # Actualizar allowed_pos de los usuarios
        for employee in employees:
            user = employee.user_id
            if user and self.id not in user.allowed_pos.ids:
                user.sudo().with_context(skip_pos_sync=True).write({
                    'allowed_pos': [Command.link(self.id)]
                })

        _logger.info(
            "POS '%s' sincronizado con %d empleado(s) del departamento '%s': %s",
            self.name,
            len(employees),
            self.department_id.name,
            employees.mapped('name')
        )

    def _remove_employees_from_old_department(self, old_department_id):
        """
        Remueve los empleados del departamento anterior del POS.

        Flujo:
        - Busca empleados que pertenecían al departamento anterior
        - Los remueve de basic_employee_ids
        - Remueve este POS de allowed_pos de sus usuarios
        """
        self.ensure_one()

        # Buscar empleados del departamento anterior que están en este POS
        employees_to_remove = self.basic_employee_ids.filtered(
            lambda e: e.department_id.id == old_department_id
        )

        if not employees_to_remove:
            return

        # Remover empleados del POS
        for employee in employees_to_remove:
            self.with_context(skip_user_sync=True, skip_dept_sync=True).write({
                'basic_employee_ids': [Command.unlink(employee.id)]
            })

            # Remover este POS de allowed_pos del usuario
            user = employee.user_id
            if user and self.id in user.allowed_pos.ids:
                user.sudo().with_context(skip_pos_sync=True).write({
                    'allowed_pos': [Command.unlink(self.id)]
                })

        _logger.info(
            "Empleados del departamento anterior removidos de POS '%s': %s",
            self.name,
            employees_to_remove.mapped('name')
        )

    def action_sync_department_employees(self):
        """
        Acción para sincronizar manualmente los empleados del departamento.
        Útil para migración inicial o re-sincronización.
        """
        synced_count = 0
        for pos_config in self:
            if pos_config.department_id:
                pos_config._sync_employees_from_department()
                synced_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sincronización completada',
                'message': f'{synced_count} POS sincronizado(s) con sus departamentos.',
                'type': 'success',
                'sticky': False,
            }
        }

    def open_ui(self):
        for config in self:
            if not config.has_active_session:
                return super(PosConfig, self).open_ui()
            if self.validate_access_for_user(config):
                return super(PosConfig, self).open_ui()
            else:
                raise UserError(
                    "La sesión se encuentra activa con otro empleado. "
                    "Debe usar otra caja o esperar a que la sesión actual se cierre."
                )

    def validate_access_for_user(self, config):
        valid = True
        invalid = False
        user_active = self.env.uid
        user_boot = 1
        user_admin = 2
        user_current = config.current_session_id.user_id.id

        if user_active == user_boot or user_active == user_admin or user_active == user_current:
            return valid

        return invalid
