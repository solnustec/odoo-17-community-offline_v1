# -*- coding: utf-8 -*-

{
    'name': 'Validaciones para Nómina',
    "author": "Klever Ontaneda",
    'version': '17.0.1.0',
    "images":['static/description/main_screenshot.png'],
    'summary': "Este modulo permite hacer validaciones de Nómina, como excepciones, horas extraordinarias",
    'description': """Este modulo permite hacer validaciones de Nómina, como excepciones, horas extraordinarias""",
    "license" : "OPL-1",
    'depends': ['hr_holidays','hr', 'hr_payroll','hr_contract', "account_edi",
        "l10n_ec"],
    'data': [
           'security/ir.model.access.csv',
           'data/sequence.xml',
           'data/paperformat.xml',
           # 'data/type_entry_for_nomina.xml',
           'report/report.xml',
           'data/mail_template.xml',
           'security/validation_hours_extra.xml',
           'views/employee_weekoff_view.xml',
           'views/shift_type_view.xml',
           'views/employee_week_day_view.xml',
           'views/employee_shift_view.xml',
            'views/employee_shift_allocation_view.xml',
           'views/employee_shift_changes_view.xml',
           'wizard/bulk_allocation_wizard_view.xml',
           # 'report/shift_report.xml',
            'views/work_entry_custom.xml',
            'views/custom_resource_calendar_view.xml',
            'report/shift_change_report.xml',
            'views/shift_settings.xml',
            # 'views/tester.xml',
           # 'wizard/employee_shift_roster_report_view.xml',
            ],
    'installable': True,
    'auto_install': False,
    'price': 35,
    'currency': "EUR",
    'category': 'Human Resources',

}


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
