# -*- coding: utf-8 -*-
{
    'name': "Supplier Invoice Restriction",
    'summary': "Restricción de metodos de pago en las facturas de proveedores",
    'description': """
si el monto de una factura de proveedor supera los 500, establece una forma de pago predeterminada
las liquidaciones de compras solo pueden ser con cedula
    """,
    'author': "Solnustec",
    'website': "https://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account', 'l10n_ec'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        # 'views/views.xml',
        # 'views/templates.xml',
    ],
    'auto_install': False,
    'installable': True,
    'application': True,
}
