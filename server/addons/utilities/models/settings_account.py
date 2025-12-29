from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    daily_payment_of_utilities = fields.Many2one(
        'account.account', string="Pago Diario de Utilidades"
    )
    profit_sharing_account = fields.Many2one(
        'account.account', string="Cuenta de Participación en Utilidades"
    )
    judicial_withholding_account = fields.Many2one(
        'account.account', string="Cuenta de Retención Judicial"
    )
    advance_profit_account = fields.Many2one(
        'account.account', string="Cuenta de Adelanto de Utilidades"
    )
    profit_payable_account = fields.Many2one(
        'account.account', string="Cuenta de Utilidades por Pagar"
    )
    solidarity_benefits_account_to_iees = fields.Many2one(
        'account.account', string="Cuenta de Beneficios Solidarios al IESS"
    )