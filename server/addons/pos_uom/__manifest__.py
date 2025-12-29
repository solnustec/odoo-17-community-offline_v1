# -*- coding: utf-8 -*-
{
    'name': "POS UOM Integration",
    'summary': 'Integración del campo UOM en POS',
    'description': """
    Long description of module's purpose
    """,
    'author': "Fabricio",
    'website': "https://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': ['base', 'pos_custom_check'
               ],
    'data': [
         ##'security/ir.model.access.csv',
         #'views/product_template_view.xml',
    ],
    
    'assets': {
        'point_of_sale._assets_pos': [ 
            'pos_uom/static/src/xml/*.xml',

        ],
        
    },
    'installable': True,
    'auto_install': False,  
}
