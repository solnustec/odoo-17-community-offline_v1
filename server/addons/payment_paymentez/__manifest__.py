# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Payment Provider: Paymentez',
    'version': '1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "Custom Module of Payment Providers of the Paymentez",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['payment'],
    'author': 'SolnusTec',
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_paymentez_templates.xml',
        'views/payment_token_view.xml',
        'views/payment_transaction_view.xml',
        'views/payment_templates.xml',

        'data/payment_provider_data.xml', 

    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_frontend': [
            'payment_paymentez/static/src/**/*',
        ],
    },
    'images': ['static/description/icon.png'],  
    'license': 'LGPL-3',
}
