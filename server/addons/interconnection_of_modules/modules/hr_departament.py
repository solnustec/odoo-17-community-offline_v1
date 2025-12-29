from odoo import models, fields, api
from odoo.exceptions import RedirectWarning


class HrDepartament(models.Model):
    _inherit = "hr.department"

    is_zone = fields.Boolean(string="¿Es una zona?", default=False)
    zone_id = fields.Many2one(
        'hr.department',
        string="Zona",
        compute='_compute_zone_id',
        store=True,
        help="Zona a la que pertenece este departamento (primer departamento padre con is_zone=True)"
    )

    @api.depends('parent_id', 'parent_id.is_zone', 'parent_id.zone_id', 'is_zone')
    def _compute_zone_id(self):
        for department in self:
            # Si el departamento es una zona, su zone_id es él mismo
            if department.is_zone:
                department.zone_id = department.id
            else:
                # Buscar en la jerarquía de padres
                zone = False
                parent = department.parent_id
                while parent:
                    if parent.is_zone:
                        zone = parent
                        break
                    parent = parent.parent_id
                department.zone_id = zone
