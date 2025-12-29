from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    company_ids = fields.Many2many(
        comodel_name="res.company",
        column1="product_id",
        column2="company_id",
        relation="product_product_company_rel",
        related="product_tmpl_id.company_ids",
        compute_sudo=True,
        readonly=False,
        store=True,
    )

    company_group_ids = fields.Many2many(
        comodel_name="company.group",
        relation="product_company_group_rel",
        column1="product_id",
        column2="group_id",
        string="Grupos de empresas",
        help="Listado de grupos de empresas asociados a este producto.",
    )
