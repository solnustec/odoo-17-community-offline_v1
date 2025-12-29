# -*- coding: utf-8 -*-
{
    'name': "Métricas del Chatbot",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'Uncategorized',
    'version': '0.1',

    'depends': ['base', 'sale'],

    'data': [
        'security/ir.model.access.csv',
        'views/chatbot_products.xml',
        'views/chatbot_location.xml',
        'views/chatbot_city.xml',
        'views/chatbot_menu.xml',
        'views/chatbot_delivery_price.xml',
        'views/website_chatbot.xml'
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    "license": "LGPL-3",
}
