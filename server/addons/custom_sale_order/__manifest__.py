{
    'name': 'Campos personalizados Ventas',
    'version': '1.0',
    'summary': 'Añade campos personalizados al modelo de sale order',
    'description': 'Este módulo añade campos personalizados al modelo de sale order.',
    'author': 'Manoel Malon',
    'category': 'Custom',
    'depends': ['sale'],
    'data': [
        'views/sale_order_line.xml',
        'views/sale_order_report.xml',
        'views/sale_order.xml',
    ],
    'installable': True,
    'application': False,
}
