from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.constrains('account_move_line')
    def _get_analytic_lines(self):
        return