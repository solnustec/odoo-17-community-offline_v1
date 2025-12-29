# -*- coding: utf-8 -*-

{
    'name': 'Pos Regulación de Inventario',
    'version': '17.0.1.0.0',
    'category': 'Point of Sale',
    'summary': "Allows to Directly Stock Regulation From the Current POS"
               " Session",
    'description': "This module allows for the immediate update producto  stock "
                   "within the same point-of-sale (POS) session.",
    'author': 'solnustec',
    'company': 'solnustec',
    'maintainer': 'solnustec',
    'website': 'https://www.solnustec.com',
    'depends': ['base', 'point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_config_view.xml',
        'views/inventory_schedule_views.xml',
        'views/inventory_schedule_menu_views.xml',
    ],
    'qweb': [
        'static/src/xml/custom_modal_template.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            '/pos_inventory_regulation/static/src/xml/stock_regulation_button.xml',
            # '/pos_inventory_regulation/static/src/xml/regulation_ref_popup.xml',
            '/pos_inventory_regulation/static/src/xml/regulation_create_popup.xml',
            # '/pos_inventory_regulation/static/src/xml/stock_regulation_receipt.xml',
            '/pos_inventory_regulation/static/src/js/stock_regulation.js',
            '/pos_inventory_regulation/static/src/js/regulation_create_popup.js',
            # '/pos_inventory_regulation/static/src/js/regulation_ref_popup.js',
            # '/pos_inventory_regulation/static/src/js/stock_regulation_receipt.js',
            '/pos_inventory_regulation/static/src/js/custom_modal.js',
            '/pos_inventory_regulation/static/src/js/modal_print.js',
            # '/pos_inventory_regulation/static/src/js/historicalPopup.js',
            '/pos_inventory_regulation/static/src/xml/custom_modal_template.xml',
            # '/pos_inventory_regulation/static/src/css/custom_styles.css',

        ],
    },
    'license': 'GPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
