# -*- coding: utf-8 -*-
{
    'name': "search_warehouse",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Point of Sale',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'point_of_sale', 'product', 'stock', 'barcodes',
                'web_editor', 'digest', 'stock_account'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'search_warehouse/static/src/js/models.js',
            'search_warehouse/static/src/js/search_warehouse.js',
            'search_warehouse/static/src/xml/search_warehouse_templates.xml',
            'search_warehouse/static/src/js/product_card.js',
            'search_warehouse/static/src/xml/product_card.xml',
            'search_warehouse/static/src/scss/product_card.scss',
        ],
    },
    'qweb': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    # only loaded in demonstration mode
}

