{
    'name': "POS Sales Order",
    'summary': """POS Sales Order""",
    'description': """POS Sales Order""",

    'category': 'Sales/Point of Sale',
    'author': 'Adevx',
    'license': "OPL-1",
    'website': 'https://adevx.com',
    "price": 0,
    "currency": 'USD',

    'depends': ['sale_stock', 'pos_sale', 'pos_custom_check'],
    'data': [
        # Views
        'views/pos_config.xml',
        'views/sale_order.xml',
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "adevx_pos_sales_order/static/src/**/*"
        ]
    },

    'installable': True,
    'application': True,
    'auto_install': False,
}
