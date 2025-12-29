
{
    'name': "Extensión módulo base",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'uncategorized',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base'],

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


