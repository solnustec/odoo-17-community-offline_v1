# -*- coding: utf-8 -*-
{
    'name': 'Branch Update Manager',
    'version': '17.0.1.0.0',
    'category': 'Technical',
    'summary': 'Sistema automatizado de distribución de actualizaciones para sucursales offline',
    'description': """
Branch Update Manager - Sistema de Distribución de Actualizaciones
===================================================================

Este módulo proporciona un sistema completo para distribuir actualizaciones
de módulos Odoo a múltiples sucursales que operan en modo offline.

Características principales:
----------------------------
* Gestión centralizada de versiones de módulos
* Empaquetado automático de actualizaciones (ZIP con checksums)
* API REST para distribución a sucursales
* Soporte para actualizaciones incrementales (delta)
* Sistema de rollback automático en caso de fallas
* Dashboard de monitoreo en tiempo real
* Cola de actualizaciones con reintentos exponenciales
* Soporte para 250+ sucursales
* Funciona con conectividad intermitente

Componentes:
------------
1. Servidor Central (Cloud):
   - Registro y versionado de módulos
   - Generación de paquetes de actualización
   - API de distribución
   - Dashboard de monitoreo

2. Agente de Sucursal (Branch):
   - Verificación automática de actualizaciones
   - Descarga con reintentos
   - Aplicación segura de actualizaciones
   - Rollback automático si falla

Uso:
----
1. En el servidor central: Crear un nuevo "Update Package"
2. Seleccionar los módulos a actualizar
3. Publicar el paquete
4. Las sucursales descargarán y aplicarán automáticamente

Requisitos:
-----------
* Odoo 17 Community Edition
* Python 3.10+
* Conectividad intermitente mínima
    """,
    'author': 'Sistema ERP',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'mail',
        'stock',  # Required for warehouse_id field in branch.registry
    ],
    'data': [
        # Security
        'security/branch_update_security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ir_cron.xml',
        'data/ir_sequence.xml',
        # Views - order matters! Actions must be loaded before menus that reference them
        'views/update_log_views.xml',
        'views/branch_registry_views.xml',
        'views/update_package_views.xml',
        'views/res_config_settings_views.xml',
        'views/dashboard_views.xml',
        # Menus last (they reference actions from other view files)
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'branch_update_manager/static/src/js/**/*',
            'branch_update_manager/static/src/xml/**/*',
            'branch_update_manager/static/src/css/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
}
