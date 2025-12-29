# -*- coding: utf-8 -*-
{
    'name': "vademecum",
    'summary': "Extiende la funcionalidad del POS para integrar la búsqueda de medicamentos con la API del vademécum",
    'description': """
         **Configuración del Token:**
        - El token de autenticación `api_token` debe ser configurado en los parámetros del sistema de Odoo para que la API funcione correctamente.
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
                'web_editor', 'digest', 'stock_account', 'website'],
    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        "views/pixel_template.xml",
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'vademecum/static/src/js/models.js',
            'vademecum/static/src/js/clear_button.js',
            'vademecum/static/src/js/info_popup.js',
            'vademecum/static/src/js/product_info_loading_block.js',
            'vademecum/static/src/js/product_info_popup_unblock_patch.js',
            'vademecum/static/src/xml/clear_button_templates.xml',
            'vademecum/static/src/css/vademecum.css',
            'vademecum/static/src/css/orderline_discount_patch.xml',
            'vademecum/static/src/css/pos_discount.css',
            'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
        ],
    },
    'qweb': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    # only loaded in demonstration mode
}