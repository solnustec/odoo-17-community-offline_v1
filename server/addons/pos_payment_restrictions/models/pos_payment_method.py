from odoo import models, fields


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    payment_restrictions = fields.Boolean(string="Habilitar restricciones de pagos 1",
                                          compute="_compute_payment_restrictions",
                                          help_text="Habilita las restricciones para tener solo dos metodos de pago")

    def _compute_payment_restrictions(self):
        """Carga el valor de restricciones globales desde ir.config_parameter."""
        config_value = self.env['ir.config_parameter'].sudo().get_param(
            'pos_payment_restrictions.payment_restrictions', default=True
        )
        for record in self:
            record.payment_restrictions = config_value == 'True'
