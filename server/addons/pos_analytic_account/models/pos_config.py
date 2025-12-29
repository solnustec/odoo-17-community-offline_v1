from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',  string="Analytic account",
        help="Add Analytic account for the current session")
