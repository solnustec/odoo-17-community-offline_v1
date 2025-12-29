
{
    'name': "Accesos a módulos general",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'Tools',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'utm', 'hr', 'hr_holidays', 'fleet', 'hr_recruitment',
                'hr_attendance', 'stock', 'purchase', 'formio',
                'document_knowledge', 'mass_mailing', 'website', 'account_accountant',
                'point_of_sale', 'spreadsheet_dashboard', 'sale_management', 'crm',
                'payroll_other_discounts', 'contacts', 'pragtech_whatsapp_base',
                'custom', 'calendar', 'mail', 'survey', 'project', 'project_todo'],

    'data': [
         #
         'security/group_for_modules.xml',
         'views/menu_views.xml',
    ],

    'demo': [
        'demo/demo.xml',
    ],
}


