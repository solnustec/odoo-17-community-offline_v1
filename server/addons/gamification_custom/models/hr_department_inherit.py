# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrDepartment(models.Model):
    _inherit = "hr.department"

    gamification_assignment_ids = fields.One2many(
        "gamification.department.assignment",
        "department_id",
        string="Asignaciones Gamification",
        help="Asignaciones de esta farmacia a una categoría de gamification.",
    )

    gamification_category_id = fields.Many2one(
        "gamification.department.category",
        string="Categoría Gamification",
        compute="_compute_gamification_category",
        inverse="_inverse_gamification_category",
        store=True,
        help="Categoría usada para filtrar usuarios en los desafíos.",
    )


    @api.depends("gamification_assignment_ids.category_id")
    def _compute_gamification_category(self):
        for department in self:
            assignment = department.gamification_assignment_ids[:1]
            department.gamification_category_id = assignment.category_id if assignment else False

    def _inverse_gamification_category(self):
        Assignment = self.env["gamification.department.assignment"]
        for department in self:
            assignment = department.gamification_assignment_ids[:1]
            category = department.gamification_category_id

            if category:
                if assignment:
                    assignment.category_id = category
                else:
                    Assignment.create(
                        {
                            "department_id": department.id,
                            "category_id": category.id,
                        }
                    )
            elif assignment:
                assignment.unlink()