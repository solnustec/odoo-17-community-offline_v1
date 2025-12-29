from odoo import fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    analytic_account_id = fields.Many2one(
        string="Cuenta analítica",
        tracking=True,
        help="Agregar la cuenta analítica a los productos que son servicios. que paga la empresa.",
        comodel_name="account.analytic.account",
        inverse_name="product_template_analytic_id",
    )

    def create(self, vals_list):
        res = super().create(vals_list)
        if not vals_list.get('analytic_account_id'):
            raise ValidationError(
                "El producto no tiene una cuenta analítica asignada. Contacte con el administrador."
            )
        return res

    def write(self, vals):
        res = super().write(vals)
        if not self.analytic_account_id:
            raise ValidationError(
                "El producto no tiene una cuenta analítica asignada. Contacte con el administrador."
            )
        return res
