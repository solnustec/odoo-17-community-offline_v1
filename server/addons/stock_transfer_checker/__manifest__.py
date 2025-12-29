{
    'name': 'Stock Transfer Checker',
    'version': '17.0.1.0.0',
    'summary': 'Permite verificar manualmente productos de una transferencia',
    'description': """
Módulo que agrega un wizard de verificación en las transferencias de inventario.
Los empleados deben reingresar productos y cantidades para validar que coincidan
con lo esperado en la transferencia.
""",
    'author': 'Tu Nombre',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_transfer_check_views.xml',
    ],
    'installable': True,
    'application': False,
}
