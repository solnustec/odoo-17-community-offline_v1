# -*- coding: utf-8 -*-
{
    'name': "guide_remision",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

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
    'depends': [
        'base',
        'stock',
        'fleet',
    ],

    # always loaded
    'data': [
        'report/stock_picking_report.xml',
        'views/guia_remision_views.xml',
        'views/stock_picking_views.xml',
        'views/guia_remision_template_sri.xml',
        'data/ir_sequence_data.xml',
        'views/report.xml',
        'views/report_referral_guide_template.xml',
        'views/res_company_views.xml',
        'views/stock_move.xml',

    ],
    'assets': {
        'web.assets_backend': [
            'guide_remision/static/src/css/stock_warning.css',
        ],
    },

    'demo': [
        'demo/demo.xml',
    ],
}
