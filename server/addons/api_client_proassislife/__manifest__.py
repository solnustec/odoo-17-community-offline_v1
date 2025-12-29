# -*- coding: utf-8 -*-
{
    'name': "Api Client Proassislife",

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

    'depends': ['base'],

    # always loaded
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'api_client_proassislife/static/src/js/*.js',
            'api_client_proassislife/static/src/xml/*.xml',
            'api_client_proassislife/static/src/css/*.css',
        ],

    },
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
