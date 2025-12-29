# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) PySquad Informetics (<https://www.pysquad.com/>).
#
#    For Module Support : contact@pysquad.com
#
##############################################################################

{
    'name': 'Purchase Product History',
    'version': '17.0',
    'category': 'Purchase',
    'summary': 'Product Purchase History',
    'description': """
            This module allows users Keep the record of product purchase history and export in excel.
            """,

    'author': 'Pysquad Informatics LLP',
    'website': 'https://www.pysquad.com',
    'depends': ['base', 'purchase', 'migration','sales_report','replenishment_inventory'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_view.xml',
        'views/purchase_history_view.xml',
        'data/cron.xml'
        # 'wizard/purchase_product_history_wizard_view.xml',
    ],
    'images': [
        'static/description/icon_banner.png'
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
