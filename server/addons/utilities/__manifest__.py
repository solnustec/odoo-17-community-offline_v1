
{
    'name': "Utilidades en nomina",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'Human Resources',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'hr_payroll', 'hr_payroll_account'],

    # always loaded
    # 'assets': {
    #     'web.assets_backend': [
    #         # 'utilities/static/src/js/date_picker_custom.js',
    #     ],
    # },
    'data': [
         #
        'security/access_to_utilities.xml',
         'views/settings_account_view.xml',
         'views/utilidades_view.xml',
         'security/ir.model.access.csv',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}


