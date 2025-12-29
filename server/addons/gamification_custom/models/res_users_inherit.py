# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    # gamification_department_id = fields.Many2one(
    #     "hr.department",
    #     string="Departamento (Gamification)",
    #     related="employee_id.department_id",
    #     store=True,
    #     readonly=True,
    # )
    #
    # gamification_department_category_id = fields.Many2one(
    #     "gamification.department.category",
    #     string="Categoría de departamento (Gamification)",
    #     related="employee_id.department_id.gamification_category_id",
    #     store=True,
    #     readonly=True,
    # )
