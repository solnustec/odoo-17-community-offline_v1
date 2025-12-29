# -*- coding: utf-8 -*-
{
    'name': 'Analisis de Rotacion de Productos',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Identifica productos con stock que han dejado de rotar',
    'description': """
Sistema de Analisis de Rotacion de Productos
=============================================

Sistema de alto rendimiento y escalable para identificar productos con stock
que han dejado de rotar en multiples bodegas.

Caracteristicas:
- Analisis incremental diario (sin recalculo completo)
- Detecta productos sin ventas, sin transferencias o sin movimiento
- Soporta 15,000+ productos y 300+ bodegas
- Optimizado para PostgreSQL con indices apropiados
- Soporte multi-compania y multi-bodega
- Vistas Kanban, tree y search con indicadores de color

Arquitectura Tecnica:
- Tabla unica de snapshot (product_rotation_daily)
- Actualizaciones incrementales pre-agregadas
- Usa product_warehouse_sale_summary para ventas (eficiente)
- Operaciones SQL masivas
- Sin triggers, actualizacion por cron
- Indices compuestos para rendimiento
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',

    'depends': [
        'base',
        'mail',
        'stock',
        'sale_stock',
        'sales_report',  # Para product_warehouse_sale_summary
    ],

    'data': [
        'security/product_rotation_security.xml',
        'security/ir.model.access.csv',
        'data/mail_activity_type_data.xml',
        'data/ir_cron_data.xml',
        'wizard/product_rotation_transfer_wizard_views.xml',
        'views/product_rotation_views.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
}
