{
    'name': "Solo Lectura Global",

    'summary': "Restringe a los usuarios con este grupo a solo lectura en todo Odoo",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'Human Resources',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base'],

    # always loaded
    # 'assets': {
    #     'web.assets_backend': [
    #         # 'utilities/static/src/js/date_picker_custom.js',
    #     ],
    # },
    'data': [
         #
        'security/global_read_only_groups.xml',
    ],
    # 'post_load': 'post_load_hook',
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}


