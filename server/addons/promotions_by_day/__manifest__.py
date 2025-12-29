# -*- coding: utf-8 -*-
{
    'name': "promotions_by_day",

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
    'depends': ['base', 'point_of_sale'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        "views/pos_weekday_promotion_views.xml",
    ],
    # only loaded in demonstration mode
    "assets": {
        'point_of_sale._assets_pos': [
            "promotions_by_day/static/src/js/pos_discount.js",
            "promotions_by_day/static/src/js/pos_order.js",
        ],
    },
    'demo': [
        'demo/demo.xml',
    ],
}

