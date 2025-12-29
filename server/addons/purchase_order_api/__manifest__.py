# -*- coding: utf-8 -*-
{
    'name': "purchase_order_api",

    'summary': "Modulo de Sincronización de proveedores con Odoo",

    'description': """
Sincronización de proveedores con Odoo
    """,
    'author': "My Company",

    'website': "https://www.yourcompany.com",

    'category': 'Uncategorized',

    'version': '0.1',

    'depends': ['base', 'purchase_stock'],

    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_view.xml',
        'views/purchase_data_view.xml',
        'views/credit_note_data_view.xml',
        'data/cron.xml',
    ],

    'installable': True,

    'application': True,
}
