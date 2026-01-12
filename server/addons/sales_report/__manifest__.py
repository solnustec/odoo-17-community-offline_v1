# -*- coding: utf-8 -*-
{
    'name': "Reporte de Ventas",

    'summary': "Provides detailed sales report and analytics for better business insights.",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'stock', 'point_of_sale','purchase',
                'purchase_order_additional_info'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/product_warehouse_sale_summary_views.xml',
        'views/loyalty_sync_view.xml',
        'views/product_sync_view.xml',
        'views/sales_report_view.xml',
        'views/purchase_report_inherit.xml',
        'views/purchase_order_inherit.xml',
        'views/promotions_view.xml',
        'views/config_settings.xml',
        'views/api_monitor_views.xml',
        'views/loyalty_reward.xml',
        'views/loyalty_program.xml',
        'data/cron.xml',
        'data/temporary_discount_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_report/static/src/js/*.js',
            'sales_report/static/src/xml/*.xml',
            'sales_report/static/src/css/styles.css',
            'sales_report/static/src/js/fullscreen.js',
        ],

    },
    # only loaded in demonstration mode
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
