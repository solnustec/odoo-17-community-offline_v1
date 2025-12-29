# -*- coding: utf-8 -*-
{
    'name': "Allocations of Consumable Products",
    'summary': "Gestión de asignaciones de productos de consumo",
    'description': """
Módulo para gestionar asignaciones y consumos de productos dentro de la empresa.
    """,
    'author': "Novacode Solutions",
    'website': "https://www.yourcompany.com",
    'category': 'Inventory',
    'version': '0.1',
    'depends': ['base', 'stock', 'report_xlsx'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/menu.xml',
        'views/intake_views.xml',
        'views/move_views.xml',
        'report/consumable_report_xlsx.xml',
        'report/consumable_move_report.xml'
    ],
    'images': ['static/description/icon.png'],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
