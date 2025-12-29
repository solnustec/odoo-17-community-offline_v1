from odoo import fields, models, api, _


class DepartmentAssignment(models.Model):
    _name = "gamification.department.assignment"
    _description = "Asignación de Farmacias a Categorías"
    _rec_name = "department_id"

    department_id = fields.Many2one(
        "hr.department",
        string="Farmacia",
        required=True,
        ondelete="cascade",
    )

    category_id = fields.Many2one(
        "gamification.department.category",
        string="Categoría",
        required=True,
        ondelete="cascade",
    )

    _sql_constraints = [
        (
            "unique_assignment",
            "unique(department_id)",
            "Esta farmacia ya tiene una categoría asignada.",
        )
    ]


class GamificationDepartmentCategory(models.Model):
    _name = "gamification.department.category"
    _description = "Gamification Department Category"

    name = fields.Char(string="Nombre", required=True)

    code = fields.Selection(
        selection=[("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")],
        string="Categoría",
        required=True,
        help="Clasificación de la farmacia/departamento.",
    )

    department_ids = fields.One2many(
        "gamification.department.assignment",
        "category_id",
        string="Asignaciones",
    )

    department_count = fields.Integer(
        string="Número de farmacias",
        compute="_compute_department_count",
        store=True,
    )

    _sql_constraints = [
        (
            "category_code_unique",
            "unique(code)",
            _("Solo puede existir una categoría por código."),
        ),
    ]

    @api.depends("department_ids")
    def _compute_department_count(self):
        for record in self:
            record.department_count = len(record.department_ids)


