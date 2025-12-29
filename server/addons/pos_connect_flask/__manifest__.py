{
    'name': 'JSON Storage for POS',
    'version': '1.0',
    'category': 'Point Of Sale',
    'summary': 'Module to store JSON records linked to Point of Sale',
    'author': 'Your Name',
    'depends': ['base', 'point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/json_storage_views.xml',
        'views/json_storage_note_credit_views.xml',
        'views/json_stock_regulation_views.xml',
        'views/json_pos_session_views.xml',
        'views/jason_transfers.xml',
        'views/json_transfers_edits.xml',
        'data/cron.xml'
    ],
    'license': 'GPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
