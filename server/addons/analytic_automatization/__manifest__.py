# -*- coding: utf-8 -*-
{
    'name': "Cuentas Analíticas Automáticas",

    'summary': "Agrega las cuentas analíticas a las lines de ventas, compras y facturas, automáticamente considerando la cuenta configurada al departamento, bodega",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale_management', 'purchase', 'account', 'stock',
                'analytic_base_department'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/stock_warehouse_view.xml',
        'views/product_template_invoice_view.xml',
    ],
    # only loaded in demonstration mode
    "installable": True,
    "application": False,
}
