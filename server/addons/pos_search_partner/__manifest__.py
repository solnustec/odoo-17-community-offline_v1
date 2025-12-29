# -*- coding: utf-8 -*-
{
    'name': "Pos partner search",

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
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_search_partner/static/src/js/*.js',
            "pos_search_partner/static/src/xml/*.xml"

        ],

    },
    'license': 'LGPL-3',
}
