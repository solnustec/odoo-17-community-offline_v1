# -*- coding: utf-8 -*-
{
    'name': "App Mobile Store",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '0.1',
    # any module necessary for this one to work correctly
    'depends': ['base', 'l10n_latam_base', 'l10n_ec', 'website',
                'sale_loyalty', 'payment','website_sale','pos_connect_flask'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_view.xml',
        'views/app_mobile_views.xml',
        'views/payment_method.xml',
        'views/website_app_mobile_menus.xml',
        'views/stock_warehouse_view.xml',
        'views/res_country_state_view.xml',
        'views/payment_transaction_view.xml',
        'views/product_public_category_view.xml',
        'views/loyalty_program_views.xml',
        'views/app_order_views.xml',
        'views/json_storage_view.xml',
        'data/cron.xml'
    ],
    # always loaded
    # only loaded in demonstration mode
    "installable": True,
    "application": True,
    'license': 'AGPL-3',
}
