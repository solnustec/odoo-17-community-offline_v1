{
    'name': 'Website sales custom',
    'version': '1.0',
    'summary': '',
    'author': 'Holger Jaramillo',
    'category': 'Tools',
    'depends': ['website_sale'],
    'data': [
        'views/assets.xml',
        'views/product_price_list_item_view.xml',
        'views/website_product_view.xml',

    ],
    'assets': {
        'web.assets_frontend': [
            '/custom_website_sale/static/src/css/website.css',
            # Añade tu archivo CSS aquí
            '/custom_website_sale/static/src/js/custom_sale_order.js',
        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'application': True,
}
