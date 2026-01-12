# -*- coding: utf-8 -*-
{
    'name': 'Transferencias Automáticas de Reabastecimiento',
    'version': '17.0.2.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Genera transferencias automáticas individuales por producto mediante cola de ejecución',
    'description': """
Transferencias Automáticas de Reabastecimiento
===============================================

Este módulo extiende el sistema de reglas de reordenamiento (orderpoints) para generar
transferencias automáticas mediante un sistema de cola eficiente.

Características principales:
----------------------------
* Sistema de cola para procesar orderpoints de forma eficiente
* Soporte para modo Individual (1 picking por producto) o Agrupado (estándar Odoo)
* Procesamiento batch con FOR UPDATE SKIP LOCKED para concurrencia
* Dedupe key para idempotencia (evita duplicados en el mismo día)
* Integración con replenishment_inventory vía hook
* Menú dedicado para cola y transferencias automáticas
* Soporte multi-company y múltiples almacenes

Flujo:
------
1. replenishment_inventory actualiza orderpoints con qty_to_order
2. Hook encola automáticamente los orderpoints con trigger='auto' y qty_to_order > 0
3. Cron procesa la cola en batches y crea transferencias
4. Limpieza automática de registros procesados

Configuración:
--------------
1. Ir a Inventario > Configuración > Ajustes
2. Activar "Reabastecimiento Automático"
3. Seleccionar modo: Individual o Agrupado
4. Configurar el almacén origen en cada almacén destino
    """,
    'author': 'SOLNUSTEC SA',
    'website': 'https://www.solnustec.com',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'interconnection_of_modules',
        'replenishment_inventory',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_warehouse_views.xml',
        'views/stock_warehouse_orderpoint_views.xml',
        'views/procurement_queue_views.xml',
        'views/replenishment_dashboard_views.xml',
        'views/auto_replenishment_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_auto_replenishment/static/src/js/replenishment_dashboard.js',
            'stock_auto_replenishment/static/src/xml/replenishment_dashboard.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
