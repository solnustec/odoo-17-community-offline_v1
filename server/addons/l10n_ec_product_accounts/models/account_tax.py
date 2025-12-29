
from odoo import fields, models
class AccountTax(models.Model):
    _inherit = 'account.tax'

    inventory_income_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Ingresos',
        help='Account used for income in inventory valuation for this tax.'
    )
    inventory_expense_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Gastos',
        help='Account used for expense in inventory valuation for this tax.'
    )
    inventory_stock_valuation_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Valorización de Inventario',
        help='Account used for stock valuation for this tax.'
    )


