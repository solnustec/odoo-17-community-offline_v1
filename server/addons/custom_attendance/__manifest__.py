# -*- coding: utf-8 -*-
{
    'name': "Dirección de Biometrico en Asistencias",

    'summary': "Añade campo de referncia para ubicación de Biométrico",

    'description': """
Long description of module's purpose
    """,

    'author': "Klever Ontaneda",
    'website': "https://www.solnustec.com",
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'hr_attendance', "employee_shift_scheduling_app"],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/template_mail.xml',
        'views/views.xml',
        'views/modal_process_attendances.xml',
        'views/attendance_general_view.xml',
        'views/incositencias_attendances_view.xml',
        'views/import_personalized.xml',
        'views/autocomplete_hours_attendance.xml',
        'views/attendances_form.xml',
        'views/projection_employee_view.xml',
        'views/schedule_history.xml',
        'views/expected_attendances_view.xml',
        'views/popup_errors_contracts_work_entry.xml',
        'data/cron_expected_attendance.xml',
        'views/res_config_settings_view.xml',
        'views/popup_attendance_general.xml',
    ],

}

