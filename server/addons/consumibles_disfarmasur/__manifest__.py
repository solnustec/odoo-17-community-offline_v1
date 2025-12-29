# -*- coding: utf-8 -*-
{
    'name': "Consumibles DisfarmaSur",
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
        "security/ir.model.access.csv",
        "views/product_views.xml",
        'views/consumibles_intake_views.xml',
        'views/consumibles_stock_transfer_views.xml',
        'views/consumibles_kardex_views.xml',
        'views/consumibles_kardex_graph_views.xml',
        'views/consumibles_kardex_dashboard_views.xml',
        'views/consumibles_kardex_dashboard_views.xml',
        'views/consumibles_kardex_server_actions.xml',
    ],
    'images': ['static/description/icon.png'],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
