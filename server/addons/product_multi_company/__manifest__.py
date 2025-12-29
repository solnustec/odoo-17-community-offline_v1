# Copyright 2015-2016 Pedro M. Baeza <pedro.baeza@tecnativa.com>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

{
    "name": "Product multi-company",
    "summary": "Select individually the product template visibility on each " "company",
    "author": "SolnusTec",
    "category": "Product Management",
    "version": "17.0.1.0.1",
    "license": "AGPL-3",
    "depends": ["base_multi_company", "product"],
    "data": [
        "views/product_template_view.xml", 
        "views/company_group_views.xml", 
        "security/ir.model.access.csv"
        ]
}
