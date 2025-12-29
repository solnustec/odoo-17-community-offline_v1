from odoo import models, api
from odoo.exceptions import ValidationError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.onchange('product_id')
    def _onchange_product_set_analytic_distribution(self):
        self.ensure_one()
        if self.analytic_distribution:
            return None

        if self.move_type == 'out_invoice' and self.product_id.product_tmpl_id.detailed_type == 'service':
            if not self.product_id.analytic_account_id:
                raise ValidationError(
                    "El producto seleccionado no tiene una cuenta analítica asignada."
                )
            self.analytic_distribution = {
                self.product_id.analytic_account_id.id: 100}
            return None
        return None
