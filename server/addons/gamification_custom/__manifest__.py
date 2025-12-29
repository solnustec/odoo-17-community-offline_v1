# -*- coding: utf-8 -*-
{
    'name': 'Gamification Custom',
    'version': '17.0.1.1.0',
    'category': 'Gamification',
    'summary': 'Custom gamification features and extensions',
    'description': """
Gamification Custom
==================

This module provides custom gamification features and extensions for Odoo 17.
""",
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'gamification',
        'hr',
        'web',
        'hr_payroll',
        'ec_payroll',
        'payroll_other_discounts',
        'report_xlsx',
    ],
    'data': [
        'security/gamification_security.xml',
        'security/ir.model.access.csv',
        'data/discount_category.xml',
        'views/views.xml',
        'views/gamification_dashboard_views.xml',
        'views/gamification_badge_user_views_inherit.xml',
        'views/gamification_goal_definition_views_inherit.xml',
        'views/gamification_goal_views_inherit.xml',
        'views/gamification_department_category_views.xml',
        'views/gamification_challenge_views_inherit.xml',
        'views/gamification_challenge_history_views.xml',
        'views/gamification_goal_history_views.xml',
        'reports/gamification_goal_progress_report.xml',
        'reports/gamification_challenge_history_report.xml',
        'wizard/gamification_add_users_wizard_views.xml',
        'views/menus.xml',
    ],
    "assets": {
        "web.assets_backend": [
            "gamification_custom/static/src/js/gam_domain_widget.js",
            "gamification_custom/static/src/xml/gam_domain_widget.xml",
        ],
    },
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    "icon": "/gamification_custom/static/description/icon.png",
    'license': 'LGPL-3',
}
