
{
    'name': "Project Custom",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'sale_project', 'project'],

    # always loaded
    # 'assets': {
    #     'web.assets_backend': [
    #         # 'utilities/static/src/js/date_picker_custom.js',
    #     ],
    # },
    'data': [
        # 'security/access_to_utilities.xml',
         'views/sale_order_views.xml',

    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}


