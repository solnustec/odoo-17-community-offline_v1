# -*- coding: utf-8 -*-
from odoo import models, fields, registry, api

class HrDepartment(models.Model):
    _inherit = 'hr.department'

    city_id = fields.Many2one(
        'hr.department.city',
        string="Ciudad",
        tracking = True
    )
    code = fields.Char("Codigo de Departamento", tracking=True)
    periodes_leaves = fields.Char(
        string="Períodos de Vacaciones",
        tracking = True,
        help="Campo informativo para mostrar en el perfil del empleado las fechas en las que puede tener vacaciones"
    )
    resource_id = fields.Many2many(
        'resource.calendar',
        'hr_department_resource_calendar_rel',  # nombre de tabla intermedia
        string="Horarios de Sucursal/Departamento",
        tracking=True
    )

    active = fields.Boolean(
        tracking=True
    )

    name = fields.Char(
        tracking=True
    )

    parent_id = fields.Many2one(
        'hr.department',
        tracking=True
    )

    company_id = fields.Many2one(
        'res.company',
        tracking=True
    )

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for department in self:
            if self.env.context.get('hierarchical_naming', True):
                department.complete_name = department.name

class EmployeeSchedule(models.Model):
    _inherit = 'hr.employee'



    horarios_departamento_ids = fields.Many2many(
        'resource.calendar',
        string='Horarios del Departamento',
    )
    horarios_departamento_computed = fields.Many2many(
        'resource.calendar',
        string='Horarios del Departamento',
        compute='default_get_custom'
    )


    @api.model
    def default_get_custom(self):
        self.horarios_departamento_computed = self.department_id.resource_id.ids or []


class CityForDepartment(models.Model):
    _name = 'hr.department.city'

    name = fields.Char("Ciudad del departamento/sucursal")


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    department_ids = fields.Many2many(
        'hr.department',
        'hr_department_resource_calendar_rel',
        string="Departamentos"
    )

    employee_ids = fields.One2many(
        'hr.employee',
        'resource_calendar_id',
        string="Empleados que usan este horario"
    )