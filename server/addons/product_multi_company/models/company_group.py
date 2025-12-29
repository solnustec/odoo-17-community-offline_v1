from odoo import fields, models

class CompanyGroup(models.Model):
    _name = "company.group"
    _description = "Grupo de Empresas"

    name = fields.Char(string="Nombre del grupo", required=True)
    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="company_group_res_company_rel",
        column1="group_id",
        column2="company_id",
        string="Empresas",
    )
