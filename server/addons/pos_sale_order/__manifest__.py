{
    'name': 'Pos Notas de Entrega',
    'version': '17.0.0.0',
    'category': 'Point of Sale',
    'summary': 'Generar notas de entrega desde POS',
    'description': """
        Genera notas de entrega y las confirma, desde el punto de venta
    """,
    'depends': ['base', 'sale', 'point_of_sale', 'sale_management'],
    'data': [
        'views/pos_sale_order.xml',
        'views/sale_order_menu.xml',
        'views/res_config_settings.xml',
        'views/pos_order_tree_inherit.xml',
        'views/actions.xml',
        'views/wizard.xml',
        'security/ir.model.access.csv'
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_sale_order/static/src/js/PaymentScreen.js',
            'pos_sale_order/static/src/xml/PaymentScreen.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
