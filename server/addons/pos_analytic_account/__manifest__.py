{
    'name': "POS Analytic Account",

    'category': 'Sales/Point of Sale',
    'author': 'Adevx',
    'license': "OPL-1",
    'website': 'https://adevx.com',
    "price": 0,
    "currency": 'USD',

    'depends': ['point_of_sale', 'analytic', 'account'],
    'data': [
        # Views
        'views/pos_config.xml',
    ],

    'installable': True,
    'auto_install': False,
    'application': True,
}
