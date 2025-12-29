{
    'name': 'Importar Notas de Crédito SRI desde TXT',
    'version': '17.0.1.0.0',
    'summary': 'Importa notas de crédito de proveedores del SRI desde archivo TXT con claves de autorización',
    'category': 'Accounting',
    'author': 'Solnustec',
    'website': 'https://solnustec.com',
    'depends': ['base', 'account', 'web', 'l10n_ec_edi'],
    'data': [
        'security/ir.model.access.csv',
        'views/import_sri_credit_note_txt_wizard_view.xml',
        'views/account_move_view.xml',
        'views/credit_note_type_view.xml',
        'views/account_move_menu_action_custom.xml',
    ],
    'assets': {
            'web.assets_backend': [
                'purchase_upload_credit_note_suppliers/static/src/xml/accountViewUploadButton.xml',
                'purchase_upload_credit_note_suppliers/static/src/js/account_upload.js',
            ]
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
