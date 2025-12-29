from odoo import models, fields, api
from odoo.exceptions import ValidationError


class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    app_ok = fields.Boolean(
        string="Disponible en la App Móvil",
        default=False,
        help="Indica si el programa de lealtad está disponible en la aplicación móvil."
    )

    # veriffy if have a unique program with app_ok = True
    @api.constrains('app_ok')
    def _check_unique_app_ok(self):
        for record in self:
            if record.app_ok:
                existing_program = self.search([
                    ('app_ok', '=', True),
                    ('id', '!=', record.id)
                ])
                if existing_program:
                    raise ValidationError(
                        "Solo puede haber un programa de lealtad 'Para la App Móvil' activado. Desactive el otro programa antes de activar este."
                    )
