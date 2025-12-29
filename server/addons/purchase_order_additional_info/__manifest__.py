# -*- coding: utf-8 -*-

{
    'name': "Purchase Order, Additional Information",
    'version': "17.0.0.0",
    'category': "Purchase",
    'license': 'OPL-1',
    'summary': "Mostrar la imagen del producto en la línea de la orden de compra y en recepciones, pvf",
    'description': """
		
			Mostrar la imagen del producto en la línea de la orden de compra y en recepciones
			Precio de venta final

	""",
    'author': "author",
    "website": "https://www.web.com",
    'depends': ['base', 'purchase', 'purchase_upload_credit_note_suppliers'],
    'data': [
        'views/view_purchase_order.xml',
        'views/wizard_sri_info.xml',
        'views/stock_move_view.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
