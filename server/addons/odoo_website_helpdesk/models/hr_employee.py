from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    helpdesk_area_ids = fields.Many2many(
        'helpdesk.area',
        string='Áreas de Soporte',
        help='Áreas de soporte técnico a las que está asignado el empleado'
    )

    @api.constrains('helpdesk_area_ids')
    def _check_helpdesk_user_group(self):
        """Valida que el empleado sea parte del grupo helpdesk_assigned_user si tiene áreas asignadas"""
        for employee in self:
            if employee.helpdesk_area_ids:
                user = employee.user_id
                if not user:
                    raise ValidationError(
                        _("El empleado %s debe estar asociado a un usuario para asignarle áreas de soporte.") % employee.name
                    )
                group = self.env.ref('odoo_website_helpdesk.helpdesk_assigned_user', raise_if_not_found=False)
                if group and user not in group.users:
                    raise ValidationError(
                        _("El usuario asociado al empleado %s no pertenece al grupo 'Usuarios Asignados de Helpdesk'.") % employee.name
                    )