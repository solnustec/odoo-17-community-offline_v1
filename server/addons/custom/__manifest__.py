{
    'name': 'Campos personalizados',
    'version': '1.0',
    'summary': 'Módulo para agregar campos personalizados a cualquier modelo de Odoo',
    'author': 'Holger Jaramillo',
    'category': 'Tools',
    'depends': ['base', 'base_setup', 'web', 'hr_recruitment', 'hr', 'website_hr_recruitment', 'website',
                'website_mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/category_view.xml',
        'views/template_apply.xml',
        'views/hr_applicant_form.xml',
        'views/hr_job_from.xml',
        'views/hr_employee_form.xml',
        'views/job_thank_you.xml',
    ],

    'images': ['static/description/icon.png'],
    'license': 'AGPL-3',
    'installable': True,
    'application': True,
}
