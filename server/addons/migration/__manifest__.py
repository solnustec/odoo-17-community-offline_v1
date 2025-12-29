# -*- coding: utf-8 -*-
{
    'name': "migration",

    'summary': "Modulo to migration",

    'description': """
migration
    """,
    'author': "My Company",
    'website': "https://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'point_of_sale', 'product', 'stock', 'barcodes','web_editor', 'digest', 'stock_account'],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/institutions.xml',
        'views/credit_card_view.xml',
        'views/stock_warehouse_view.xml',
        'views/cron.xml',
        'views/cron_assign_company_services.xml',
    ],
    # only loaded in demonstration mode
    'installable': True,
    'application': True,
}
