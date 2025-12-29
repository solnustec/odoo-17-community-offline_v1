# Copyright 2015-2016 Pedro M. Baeza <pedro.baeza@tecnativa.com>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = ["multi.company.abstract", "product.template"]
    _name = "product.template"

    company_ids = fields.Many2many(
        comodel_name="res.company",
        column1="product_id",
        column2="company_id",
        relation="product_template_company_rel",
        string="Empresas",
        help="Listado de empresas asociadas a este producto.",
    )

    company_group_ids = fields.Many2many(
        comodel_name="company.group",
        relation="product_template_company_group_rel",
        column1="product_id",
        column2="group_id",
        string="Grupos de Empresas",
        help="Listado de grupos de empresas asociados a este producto.",
    )

    @api.onchange('company_group_ids')
    def _onchange_company_group_ids(self):
        for product in self:
            if product.company_group_ids:
                companies = product.company_group_ids.mapped('company_ids')
                product.company_ids = [(6, 0, companies.ids)]
