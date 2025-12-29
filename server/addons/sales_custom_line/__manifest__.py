# -*- coding: utf-8 -*-
{
    'name': 'Sales Custom Line',
    'summary': 'Personalizaciones ligeras para ventas (sales).',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/sales_custom_line_views.xml',
    ],
    'installable': True,
    'application': False,
}
