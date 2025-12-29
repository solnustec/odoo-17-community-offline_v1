from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ResUsersJobGroupLink(models.Model):
    _name = "res.users.job_group_link"
    _description = "Tracking de grupos gestionados por cargo"
    _rec_name = "user_id"

    user_id = fields.Many2one("res.users", required=True, index=True, ondelete="cascade")
    group_id = fields.Many2one("res.groups", required=True, index=True, ondelete="cascade")
    job_id = fields.Many2one("hr.job", required=True, index=True, ondelete="cascade")

    _sql_constraints = [
        ("uniq_user_group_job", "unique(user_id, group_id, job_id)", "Ya existe este enlace."),
    ]
