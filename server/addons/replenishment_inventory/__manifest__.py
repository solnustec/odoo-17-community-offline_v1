{
    'name': "Reglas de Abastecimiento para Gestión de Inventario",

    'summary': "Módulo para definir y gestionar reglas automáticas de abastecimiento en el inventario.",

    'description': """
Este módulo permite configurar reglas de abastecimiento automáticas para optimizar la gestión de inventario. 
    """,

    'author': "SOLNUSTEC SA",
    'website': "https://www.tuempresa.com",

    'category': 'Inventory',
    'version': '0.1',

    # cualquier módulo necesario para que este funcione correctamente
    'depends': ['base', 'stock', 'point_of_sale', 'sales_report'],

    'data': [
         'security/ir.model.access.csv',
         'data/stock_rule_replenishment.xml',
         'data/ir_cron_queue_processor.xml',
         'views/stock_rule_replenishment_views.xml',
         'views/stock_rutes_products.xml',
         'views/stock_warehouse_orderpoint.xml',
         'views/stock_picking_type_views.xml',
         'views/stock_warehouse_views.xml',
         'views/warehouse_views_tree.xml',
         'views/replenishment_monitoring_views.xml',
         'wizard/migration_wizard_views.xml',
    ],
}
