# -*- coding: utf-8 -*-

{
    'name': 'Point of Sale Logo',
    'version': '17.0.1.0.0',
    'category': 'Point of Sale',
    'summary': "Logo For Every Point of Sale (Screen & Receipt)",
    'description': "This module helps you to set a logo for every POS"
                   "This will help you to identify the point of sale easily."
                   "You can also see this logo in pos screen and pos receipt.",
    'author': 'Solnustec',
    'company': 'Solnustec',
    'maintainer': "Solnustec",
    'website': "Solnustec",
    'depends': ['point_of_sale'],
    'data': [
        'views/res_config_settings.xml'
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'point_of_sale_logo/static/src/xml/navbar_logo.xml',
        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
