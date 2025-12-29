{
    'name': 'Invoice Discount Modifier',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Remove discount lines from invoices and apply discounts to product lines',
    'description': """
        This module automatically processes invoices to:
        - Remove specific discount lines from invoices
        - Apply the discount amount to the discount column of product lines
        - Keep sales orders unchanged with their discount lines
    """,
    'author': 'Custom Development',
    'depends': ['account', 'sale'],
    'data': [
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}