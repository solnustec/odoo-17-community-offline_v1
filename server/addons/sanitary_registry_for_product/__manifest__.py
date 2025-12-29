# -*- coding: utf-8 -*-
{
    'name': "sanitary_registry_for_product",

    'summary': 'Manage and track sanitary registries for products with expiration alerts and status indicators.',

    'description': """
        This module allows you to manage sanitary registries linked to products.
            Features include:
             - Multiple sanitary registries per product with sequence-based ordering.
             - Automatic status computation based on expiration dates (valid, about to expire, expired).
             - Visual alert messages displayed on the product form.
             - Drag-and-drop ordering of registries to prioritize the active one.
             - Attachment support for registry documentation.
             - Automatic activity creation for upcoming expirations.    """,

    'author': "Fabricio Franco",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Inventory',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'product', 'mail', 'stock','migration'],

    'assets': {
        'web.assets_backend': [

        ],
    },

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'static/src/xml/product_views_inherit.xml',
        'views/cron_sanitary_registry.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

