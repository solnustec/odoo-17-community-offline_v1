# -*- coding: utf-8 -*-

{
    'name': 'Dynamic Odoo',
    'version': '1.2.1',
    'depends': ['base'],
    'data': [
        'data/dynamic_field_widgets_data.xml',
        'security/all_in_one_dynamic_custom_fields_security.xml',
        'security/ir.model.access.csv',
        'views/dynamic_fields_views.xml',
    ],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
