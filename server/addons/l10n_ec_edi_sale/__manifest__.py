{
    'name': 'Ecuador EDI Sale Order Integration',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Integrates discounts directly in sale order lines for Ecuador EDI',
    'description': """
    This module modifies how discounts are handled in sale orders for Ecuador EDI compliance.
    Instead of creating separate discount lines, discounts are applied directly to the product lines
    in the discount percentage column.
    """,
    'author': 'Custom',
    'depends': [
        'sale',
        'account',
        'l10n_ec_edi',
        'loyalty',
    ],
    'data': [
        'views/hide_promotions.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
