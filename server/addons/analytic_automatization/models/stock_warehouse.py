from odoo import models, fields, api
from odoo.exceptions import ValidationError


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    analytic_account_id = fields.Many2one(
        string="Cuenta analítica",
        tracking=True,
        comodel_name="account.analytic.account",
        inverse_name="stock_warehouse_analytic_id",
    )

    @api.constrains('analytic_account_id', 'name')
    def _check_analytic_account_id(self):
        for warehouse in self:
            if not warehouse.analytic_account_id:
                raise ValidationError(
                    f"La bodega {warehouse.name} debe tener una cuenta analítica asignada."
                )
