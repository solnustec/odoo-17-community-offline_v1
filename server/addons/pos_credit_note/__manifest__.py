{
    'name': 'POS Credit Note',
    'version': '1.0',
    'category': 'Point of Sale',
    'summary': 'Log all data related to credit notes from POS',
    'description': 'This module logs all data involved in credit note creation from the POS.',
    'author': 'Tu Nombre',
    'website': 'https://tusitio.com',
    'depends': ['point_of_sale', 'account'],
    'data': [
        'views/pos_config_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
