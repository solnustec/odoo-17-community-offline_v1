# -*- coding: utf-8 -*-
{
    'name': "pos-old-ordes",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """Long description of module's purpose """,

    'author': "SOLNUS",
    'website': "https://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': ['base', 'point_of_sale'],
    'data': [
        # 'views/sale_return_view.xml',
        # 'views/sale_return_menu.xml',
        # 'security/ir.model.access.csv',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos-old-ordes/static/src/js/*.js',
            'pos-old-ordes/static/src/xml/*.xml',
        ],

    },
}
