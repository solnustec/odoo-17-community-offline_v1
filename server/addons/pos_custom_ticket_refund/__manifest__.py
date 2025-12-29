# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Rembolso Personalisado POS',
    'version': '17.0.0.2',
    'category': 'Point of Sale',
    'summary': 'Pos check information on pos cheque info on point of sale cheque details point of sales check information on receipt in pos cheque number on pos receipt check info pos order receipt cheque info pos payment cheque info point of sales cheque',
    'description': """The Point of Sale Check Info odoo app helps users to manage crucial information related to checks like the bank, customer name, account number, and check number within point of sale operations for businesses that accept check payments. It ensures efficient check management from point of sale.""",
    'author': 'SOLNUS',
    'website': 'https://www.browseinfo.com/demo-request?app=bi_pos_check_info&version=17&edition=Community',
    "price": 20,
    "currency": 'EUR',
    'depends': ['base', 'point_of_sale', 'pos_loyalty',"pos_custom_check"],
    'data': [
        'data/rules_registre.xml',
        'views/note_credit/note_credit.xml',
    ],
    'demo': [],
    'test': [],
    'license': 'OPL-1',
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_custom_ticket_refund/static/src/js/*.js',
            'pos_custom_ticket_refund/static/src/css/*.css',
            'pos_custom_ticket_refund/static/src/xml/*.xml',

        ],

    },
    'installable': True,
    'auto_install': False,
}
