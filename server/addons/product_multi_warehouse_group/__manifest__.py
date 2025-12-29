{
    'name': 'Product Multi-Warehouse Group',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Manage warehouse groups and assign them to products',
    'depends': ['stock', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/stock_warehouse_group_views.xml',
    ],
    'installable': True,
    'application': False,
}
