# -*- coding: utf-8 -*-
{
    'name': "Consolidated POS",

    'summary': "Consolidado punto de venta",

    'description': """Long description of module's purpose""",

    'author': "NOVACODESOLUTIONS",
    'website': "",
    'category': '',
    'version': '0.1',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_daily_warehouse_report_views.xml',
        'views/report_pos_daily_warehouse_ticket.xml',
    ],

}
