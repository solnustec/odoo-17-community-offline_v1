# -*- coding: utf-8 -*-
{
    'name': "Custom Holidays",

    'summary': "Permite, la asignacion en la fecha de contrato",

    'description': """
Permite, la asignacion en la fecha de contrato
    """,

    'author': "Klever Ontaneda",
    'website': "https://www.solnustec.com",
    'category': 'Uncategorized',
    'version': '0.1',

    'depends': ['base','hr_holidays', 'ec_payroll'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/hr_leave_accrual_plan.xml',
        'views/hr_leave_view.xml',
        'views/hr_leave_group_validation_views.xml',
        'report/report.xml',
        'report/vacation_report.xml',
    ],

    'assets': {
        'web.assets_backend': [
                'custom_holidays/static/src/xml/*.xml',
                'custom_holidays/static/src/js/*.js',
                'custom_holidays/static/src/css/*.css',
            ],
        },
}