# -*- coding: utf-8 -*-
{
    'name': "Pos Restricción de métodos de pago",

    'summary': "Restricciones de meétodos de pagos en el punto de venta",

    'description': """
        Solo se permiten dos metodos de pago por factura, si son dos
        uno de ellos obligatoriamente debe ser Efectivo, sino lanza una alerta
    """,

    'author': "Solnus",
    'website': "https://www.solnustec.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['point_of_sale','pos_custom_check'],

    # always loaded
    'data': [
        'views/pos_product_view.xml',
        'views/pos_res_config_settings.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_payment_restrictions/static/src/js/*.js',
        ]
    },
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3'
}
