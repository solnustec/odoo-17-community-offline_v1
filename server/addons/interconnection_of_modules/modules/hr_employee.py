# -*- coding: utf-8 -*-

import logging
from odoo import models, api, Command

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    """
    Extensión de hr.employee para automatización de asignación a POS
    basada en departamento.

    Cuando un empleado cambia de departamento:
    1. Se remueve de los POS del departamento anterior
    2. Se asigna a los POS del nuevo departamento (usando pos.config.department_id)
    3. Se actualiza allowed_pos del usuario correspondiente
    """
    _inherit = "hr.employee"

    def write(self, vals):
        """
        Override write para manejar cambios de departamento.
        Sincroniza automáticamente las asignaciones de POS.
        """
        # Guardar departamentos anteriores para comparación
        old_departments = {emp.id: emp.department_id.id if emp.department_id else False for emp in self}

        res = super(HrEmployee, self).write(vals)

        # Sincronizar cuando cambia el departamento
        if 'department_id' in vals:
            for employee in self:
                old_dept_id = old_departments.get(employee.id)
                new_dept_id = employee.department_id.id if employee.department_id else False

                # Solo procesar si realmente cambió el departamento
                if old_dept_id != new_dept_id:
                    # Remover de POS del departamento anterior
                    if old_dept_id:
                        employee._unlink_from_department_pos(old_dept_id)
                    # Asignar a POS del nuevo departamento
                    if new_dept_id:
                        employee._assign_to_department_pos()

        # Si se asigna user_id y ya tiene departamento, sincronizar
        if 'user_id' in vals and vals.get('user_id'):
            for employee in self:
                if employee.department_id:
                    employee._assign_to_department_pos()

        return res

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create para asignar automáticamente a POS
        cuando se crea un empleado con departamento.
        """
        employees = super(HrEmployee, self).create(vals_list)

        for employee in employees:
            if employee.department_id and employee.user_id:
                employee._assign_to_department_pos()

        return employees

    def _unlink_from_department_pos(self, department_id):
        """
        Remueve al empleado de los POS del departamento especificado.
        También actualiza allowed_pos del usuario.
        """
        self.ensure_one()

        PosConfig = self.env['pos.config'].sudo()

        # Buscar POS del departamento donde el empleado está asignado
        pos_configs = PosConfig.search([
            ('department_id', '=', department_id),
            '|',
            ('basic_employee_ids', 'in', [self.id]),
            ('advanced_employee_ids', 'in', [self.id]),
        ])

        if not pos_configs:
            return

        # Remover empleado de cada POS
        for pos_config in pos_configs:
            pos_config.with_context(skip_user_sync=True, skip_dept_sync=True).write({
                'basic_employee_ids': [Command.unlink(self.id)],
                'advanced_employee_ids': [Command.unlink(self.id)],
            })

        # Actualizar allowed_pos del usuario (remover estos POS)
        if self.user_id:
            current_allowed = self.user_id.allowed_pos.ids
            new_allowed = [pos_id for pos_id in current_allowed if pos_id not in pos_configs.ids]
            self.user_id.sudo().with_context(skip_pos_sync=True).write({
                'allowed_pos': [(6, 0, new_allowed)]
            })

        _logger.info(
            "Empleado '%s' removido de POS del departamento anterior: %s",
            self.name, pos_configs.mapped('name')
        )

    def _assign_to_department_pos(self):
        """
        Asigna al empleado a los POS de su departamento actual.

        Flujo:
        1. Buscar POS donde pos.config.department_id == employee.department_id
        2. Agregar empleado a basic_employee_ids de esos POS
        3. Actualizar allowed_pos del usuario
        """
        self.ensure_one()

        if not self.department_id:
            _logger.debug("Empleado '%s' sin departamento, omitiendo asignación POS", self.name)
            return False

        if not self.user_id:
            _logger.debug("Empleado '%s' sin usuario vinculado, omitiendo asignación POS", self.name)
            return False

        # Buscar POS del departamento del empleado
        pos_configs = self.env['pos.config'].sudo().search([
            ('department_id', '=', self.department_id.id)
        ])

        if not pos_configs:
            _logger.debug(
                "No se encontraron POS para departamento '%s'",
                self.department_id.name
            )
            return False

        # Agregar empleado a cada POS (usando link para no sobrescribir)
        for pos_config in pos_configs:
            if self.id not in pos_config.basic_employee_ids.ids:
                pos_config.with_context(skip_user_sync=True, skip_dept_sync=True).write({
                    'basic_employee_ids': [Command.link(self.id)]
                })

        # Actualizar allowed_pos del usuario (agregar, no sobrescribir)
        current_allowed = self.user_id.allowed_pos.ids
        new_allowed = list(set(current_allowed + pos_configs.ids))

        self.user_id.sudo().with_context(skip_pos_sync=True).write({
            'allowed_pos': [(6, 0, new_allowed)]
        })

        _logger.info(
            "Empleado '%s' asignado automáticamente a POS: %s (departamento: '%s')",
            self.name, pos_configs.mapped('name'), self.department_id.name
        )

        return True

    def action_reassign_pos(self):
        """
        Acción para reasignar manualmente los POS según el departamento actual.
        Útil para sincronizar empleados existentes o migración inicial.
        """
        reassigned_count = 0
        skipped_count = 0

        for employee in self:
            if not employee.user_id:
                skipped_count += 1
                continue

            # Remover de todos los POS actuales
            employee._unlink_from_all_pos()

            # Asignar a POS del departamento actual
            if employee.department_id:
                if employee._assign_to_department_pos():
                    reassigned_count += 1
                else:
                    skipped_count += 1
            else:
                skipped_count += 1

        message = f'{reassigned_count} empleado(s) reasignado(s) a sus POS correspondientes.'
        if skipped_count > 0:
            message += f' {skipped_count} omitido(s) (sin usuario o sin departamento con POS).'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Reasignación completada',
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }

    def _unlink_from_all_pos(self):
        """
        Remueve al empleado de TODOS los POS donde está asignado.
        Útil para reasignación masiva.
        """
        self.ensure_one()

        PosConfig = self.env['pos.config'].sudo()

        # Encontrar todos los POS donde el empleado está asignado
        pos_configs = PosConfig.search([
            '|',
            ('basic_employee_ids', 'in', [self.id]),
            ('advanced_employee_ids', 'in', [self.id]),
        ])

        if pos_configs:
            for pos_config in pos_configs:
                pos_config.with_context(skip_user_sync=True, skip_dept_sync=True).write({
                    'basic_employee_ids': [Command.unlink(self.id)],
                    'advanced_employee_ids': [Command.unlink(self.id)],
                })

        # Limpiar allowed_pos del usuario
        if self.user_id:
            self.user_id.sudo().with_context(skip_pos_sync=True).write({
                'allowed_pos': [(5, 0, 0)]
            })

        _logger.debug("Empleado '%s' removido de todos los POS", self.name)
