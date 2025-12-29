# -*- coding: utf-8 -*-

{
    "name": "Firebase Push Notification",
    'version': '17.0.2.0.0',
    'category': 'Discuss,Extra Tools',
    'summary': """Enviar notificaciones de Firebase a los usuarios de la app movil""",
    'description': 'Enviar notificaciones de Firebase a los usuarios de la app movil',
    'author': 'solnustec',
    'company': 'solnustec',
    'maintainer': 'solnustec',
    'website': "https://www.solnustec.com",
    "depends": ["base", "web",],
    "data": [
        "security/ir.model.access.csv",
        # "views/res_config_settings_views.xml",
        "views/firebase_notifications_views.xml",
        "views/firebase_devices_view.xml",
        "views/website_menus.xml",
        'data/ir_cron.xml',

    ],
    "external_dependencies": {"python": ["firebase_admin"]},
    'images': ['static/description/banner.jpg'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
