{
    'name': 'Campos Extra Productos',
    'version': '1.0',
    'summary': 'Añade campos personalizados al modelo de productos',
    'description': 'Este módulo añade campos personalizados al modelo de productos.',
    'author': 'Luis Fernando Velez.',
    'category': 'Custom',
    'depends': ['product', 'website', 'website_sale'],
    'data': [
        'views/product_views.xml',
        'views/laboratory_views.xml',
        'views/brand_views.xml',
        'views/manufacturer_views.xml',
        'views/laboratory_menus.xml',
        'views/product_image_alt.xml',
        'security/ir.model.access.csv',
        'views/product_image_refer_text.xml',
        'views/product_category_view.xml'
    ],
    'installable': True,
    'application': False,
}
