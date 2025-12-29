from odoo import api, fields, models

class HrJobGroupRule(models.Model):
    _name = "hr.job.group.rule"
    _description = "Reglas de grupos por cargo"

    name = fields.Char(
        string="Nombre de la regla",
        required=True,
        default=lambda self: "Regla por Cargo"
    )
    job_id = fields.Many2one(
        "hr.job",
        string="Cargo",
        required=True,
        index=True
    )
    access_group_ids = fields.Many2many(
        "res.groups",
        "hr_job_group_rule_access_group_rel",
        "rule_id",
        "group_id",
        string="Grupos a asignar",
        required=True,
    )
    apply_mode = fields.Selection(
        [
            ("add_only", "Agregar solamente"),
            ("replace_managed", "Reemplazar lo gestionado por cargo"),
        ],
        string="Modo de aplicación",
        default="add_only",
        required=True,
    )
    active = fields.Boolean(
        string="Activo",
        default=True
    )
