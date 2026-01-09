# -*- coding: utf-8 -*-
{
    'name': 'POS Offline Sync',
    'version': '17.0.2.5.0',
    'category': 'Point of Sale',
    'summary': 'Sistema de sincronización offline para Point of Sale',
    'description': """
        Módulo de sincronización offline para POS en Odoo 17.

        Características principales:
        - Operación offline completa del POS
        - Sincronización bidireccional con la nube
        - Cola de sincronización para operaciones pendientes
        - Configuración por sucursal
        - Soporte para hasta 200 sucursales
        - Sin generación de registros contables en modo offline

        Modelos sincronizados:
        - pos.order (PUSH): Órdenes de venta
        - res.partner (PUSH/PULL BIDIRECCIONAL): Clientes - Sincronización completa en ambas direcciones
        - product.product (PULL): Productos
        - product.pricelist (PULL): Listas de precios
        - loyalty.program (PULL): Programas de lealtad/promociones con reglas y recompensas
        - loyalty.rule (PULL): Reglas de programas de lealtad
        - loyalty.reward (PULL): Recompensas de programas de lealtad
        - account.fiscal.position (PULL): Posiciones fiscales/descuentos institucionales
        - stock.quant (PULL): Inventario
        - hr.employee (PULL): Empleados
        - pos.payment.method (PULL): Métodos de pago

        Nuevas características v2.0:
        - Sincronización de productos
        - Sincronización de listas de precios
        - Sincronización de programas de lealtad y promociones
        - Sincronización de posiciones fiscales para descuentos institucionales
        - Push de notas de crédito/reembolsos
        - Configuración desde archivo .env
        - Soporte para tipo de identificación LATAM (cédula, RUC, etc.)

        Mejoras v2.1 (res.partner bidireccional):
        - Campo sync_source para rastrear origen de cambios (local/cloud)
        - Evitar loops de sincronización con skip_sync_queue
        - Método mark_from_cloud() para partners del cloud
        - Endpoint /pos_offline_sync/partner/sync para sync bidireccional en una llamada
        - Detección de conflictos entre cambios locales y del cloud

        Correcciones v2.2 (sincronización bidireccional funcional):
        - CORREGIDO: Partners creados/modificados offline ahora se sincronizan al cloud
        - CORREGIDO: Partners recibidos del cloud ya no se re-agregan a cola (evita loop infinito)
        - CORREGIDO: write() ahora sincroniza partners en estado 'local' además de 'synced'
        - Método _prepare_partner_vals_from_push() para procesar datos del offline
        - Mejor logging para debug de sincronización bidireccional

        Correcciones v2.3 (sincronización loyalty.program completa):
        - CORREGIDO: loyalty.program ahora usa serializer especializado que incluye rules y rewards
        - CORREGIDO: _serialize_records usa serialize_loyalty_program para datos completos
        - CORREGIDO: deserialize_loyalty_program marca sync_state='synced' correctamente
        - CORREGIDO: _process_loyalty_rules mapea product_ids por cloud_sync_id
        - CORREGIDO: _process_loyalty_rewards mapea reward_product_id y discount_product_ids
        - Agregados serializers especializados para product.product, product.pricelist, account.fiscal.position
        - Mejor logging para debug de sincronización de promociones

        Correcciones v2.3.1 (find_or_create_from_sync para loyalty.program):
        - CORREGIDO: find_or_create_from_sync ahora busca por data['id'] como cloud_sync_id
        - CORREGIDO: Programas de lealtad ahora se actualizan correctamente en lugar de crear duplicados
        - CORREGIDO: Búsqueda por nombre solo aplica a programas sin cloud_sync_id asignado
        - Mejor logging para debug de búsqueda de programas existentes

        Correcciones v2.3.2 (debugging y mejoras find_or_create_from_sync):
        - MEJORADO: Conversión explícita de cloud_id a entero para comparaciones seguras
        - MEJORADO: Búsqueda de programas sin cloud_sync_id usa 'in' [0, False] para campos Integer
        - MEJORADO: Logging detallado en deserialize_loyalty_program para debug
        - MEJORADO: cloud_sync_id siempre se establece/actualiza correctamente después de crear/actualizar

        Correcciones v2.3.3 (vinculación de programas existentes):
        - NUEVO: Búsqueda por ID local que coincida con ID del cloud (para BD clonadas)
        - NUEVO: Búsqueda por id_database_old que coincida con cloud_id
        - MEJORADO: Estrategia de búsqueda más robusta con 5 criterios en orden de prioridad
        - MEJORADO: Programas existentes ahora se vinculan correctamente aunque no tengan cloud_sync_id
        - MEJORADO: Validación de conflictos cuando un programa ya tiene cloud_sync_id diferente

        OPTIMIZACIONES v2.4.0 (rendimiento y estabilidad):
        - OPTIMIZADO: Bloqueo de concurrencia con SELECT FOR UPDATE SKIP LOCKED
        - OPTIMIZADO: Transacciones atómicas con savepoints para sincronización batch
        - OPTIMIZADO: Paginación en endpoint PULL para reducir carga de memoria
        - OPTIMIZADO: Cache de configuración de sincronización (60s TTL)
        - OPTIMIZADO: Hooks create/write con verificaciones tempranas
        - OPTIMIZADO: Serialización mejorada de órdenes con campos adicionales (reembolsos, fiscal_position)
        - OPTIMIZADO: Limpieza de registros antiguos con SQL directo (más eficiente)
        - OPTIMIZADO: Nuevo método get_ready_for_sync_batch para procesamiento atómico
        - OPTIMIZADO: Índices en campos cloud_sync_id y sync_state
        - CORREGIDO: Eliminado SQL directo para actualizar nombres de sesión
        - CORREGIDO: Evitar hooks durante instalación de módulo (install_mode)
        - NUEVO: Método cleanup_stuck_processing para limpiar registros atascados
        - NUEVO: Serialización en lotes para evitar problemas de memoria

        Correcciones v2.4.1 (facturación electrónica Ecuador/LATAM):
        - CORREGIDO: skip_invoice_generation ahora tiene default=False para permitir generación de facturas
        - CORREGIDO: La clave de acceso y autorización ahora se generan correctamente en POS
        - MEJORADO: Documentación del campo para indicar su impacto en facturación electrónica

        MEJORAS v2.5.0 (sincronización completa de órdenes con factura):
        - NUEVO: serialize_order ahora incluye datos de factura electrónica (clave de acceso, autorización)
        - NUEVO: deserialize_order procesa orden completa con pagos y marca como pagada
        - NUEVO: Creación de pagos (pos.payment) al deserializar orden
        - NUEVO: Creación de factura en cloud con la MISMA clave de acceso del offline
        - NUEVO: Herencia account.move para respetar clave de acceso existente
        - NUEVO: Contexto skip_l10n_ec_authorization para evitar regeneración de clave
        - MEJORADO: Órdenes sincronizadas llegan con estado correcto (paid/invoiced)
        - MEJORADO: Posición fiscal se aplica correctamente en orden deserializada
        - COMPATIBLE: Integración con l10n_ec_edi para facturación electrónica Ecuador
    """,
    'author': 'SolNusTec',
    'website': 'https://www.solnustec.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'point_of_sale',
        'stock',
        'loyalty',
        'pos_custom_check',
        'pos_sale_order',  # IMPORTANTE: Para que nuestro override de is_delivery_order funcione
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/config_data.xml',
        'data/cron.xml',
        'wizard/migration_wizard_views.xml',
        'views/pos_sync_config_views.xml',
        'views/pos_sync_queue_views.xml',
        'views/pos_sync_log_views.xml',
        'views/pos_sync_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
