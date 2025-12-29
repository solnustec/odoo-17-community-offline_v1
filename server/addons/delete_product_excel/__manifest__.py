{
    'name': 'Eliminar Productosl',
    'version': '1.0',
    'summary': 'Permite cargar un archivo Excel para eliminar productos en Odoo',
    'description': 'Un módulo que permite eliminar productos masivamente mediante un archivo Excel',
    'author': 'SOLNUS',
    'website': 'https://www.tuempresa.com',
    'depends': ['base', 'product',"stock"],
    'data': [
        # 'views/stock_remove_products_form.xml',
        'views/stock_remove_products_menu.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
