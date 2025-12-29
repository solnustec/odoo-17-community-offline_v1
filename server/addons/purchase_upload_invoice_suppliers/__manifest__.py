{
    'name': 'Importar Facturas SRI desde TXT',
    'version': '17.0.1.0.0',
    'summary': 'Importa facturas de proveedor del SRI desde archivo TXT con claves de autorización',
    'category': 'Accounting',
    'author': 'Solnustec',
    'website': 'https://solnustec.com',
    'depends': ['base', 'account', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/import_sri_txt_wizard_view.xml',
    ],
    'assets': {
            'web.assets_backend': [
                'purchase_upload_invoice_suppliers/static/src/xml/accountViewUploadButton.xml',
                'purchase_upload_invoice_suppliers/static/src/js/account_upload.js',
            ]
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
