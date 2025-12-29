
{
    'name': 'Unir Cotizaciones',
    'version': '17.0.1.0.0',
    'category': 'Purchases',
    'summary': """This module merege two or more RFQ by cancelling or deleting
        the others in RFQ and RFQ sent state.""",
    'description': """'Merge RFQ' is a module for Odoo 17 that allows users to 
    merge multiple Requests for Quotations (RFQs) into a single one by 
    cancelling or deleting the others in RFQ and RFQ sent state.""",
    'author': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com',
    'depends': ['purchase'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/merge_rfq_wizard.xml'
    ],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application':False,
}
