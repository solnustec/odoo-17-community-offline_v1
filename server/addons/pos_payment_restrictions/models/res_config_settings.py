from odoo import models, fields


class PosResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payment_restrictions = fields.Boolean(
        readonly=False,
        config_parameter="pos_payment_restrictions.""payment_restrictions",
        # related="pos_payment_method_id.payment_restrictions",
        string="Habilitar restricciones de pagos",
        help_text="Habilita las restricciones para tener solo dos metodos de pago")

