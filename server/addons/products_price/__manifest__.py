
{
    'name': "Precios de Productos Global",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'product', 'point_of_sale', 'website_sale'],

    # always loaded
    'assets': {
        'point_of_sale._assets_pos': [
            'products_price/static/src/js/*.js',
        ],
    },
    'data': [
         #
        # 'security/access_to_utilities.xml',
        #  'views/settings_account_view.xml',
        #  'views/utilidades_view.xml',
        #  'security/ir.model.access.csv',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}


