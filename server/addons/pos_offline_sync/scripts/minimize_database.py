# -*- coding: utf-8 -*-
"""
Script para minimizar la base de datos de Odoo para uso offline en POS.

Este script identifica y desinstala módulos que no son necesarios para
el funcionamiento del POS offline con facturación electrónica de Ecuador.

Uso:
    python odoo-bin shell -d <database_name> < addons/pos_offline_sync/scripts/minimize_database.py

O desde el shell de Odoo:
    exec(open('addons/pos_offline_sync/scripts/minimize_database.py').read())

IMPORTANTE:
- Hacer backup de la base de datos antes de ejecutar
- Ejecutar en un ambiente de prueba primero
- Revisar la lista de módulos a desinstalar antes de confirmar
"""

import logging

_logger = logging.getLogger(__name__)

# =============================================================================
# MÓDULOS ESENCIALES - NO DESINSTALAR
# =============================================================================

# Módulos core de Odoo (siempre necesarios)
CORE_MODULES = {
    'base',
    'web',
    'bus',
    'mail',
    'contacts',
    'product',
    'uom',
    'digest',
    'barcodes',
    'web_editor',
}

# Módulos de POS (necesarios para Point of Sale)
POS_MODULES = {
    'point_of_sale',
    'pos_loyalty',
    'pos_sale',
    'pos_hr',
}

# Módulos custom de POS (tus módulos personalizados)
POS_CUSTOM_MODULES = {
    'pos_offline_sync',
    'pos_custom_check',
    'pos_connect_flask',
    'pos_restrict_product_stock',
    'multi_barcode_for_products',
    'pos_receipt_extend',
    'pos_custom_ticket_refund',
    'pos_credit_note',
    'custom_receipts_for_pos',
}

# Módulos de Stock/Inventario (necesarios para POS)
STOCK_MODULES = {
    'stock',
    'stock_account',
}

# Módulos de Contabilidad base
ACCOUNTING_MODULES = {
    'account',
    'account_edi',
    'account_payment',
}

# Módulos de Localización Ecuador (CRÍTICOS para facturación)
ECUADOR_MODULES = {
    'l10n_ec',
    'l10n_ec_edi',
    'l10n_ec_edi_pos',
    'l10n_latam_base',
    'l10n_latam_invoice_document',
    'l10n_ec_invoice_identification',
}

# Módulos de RRHH mínimos (para empleados en POS)
HR_MINIMAL_MODULES = {
    'hr',
}

# Módulos de Ventas mínimos
SALES_MINIMAL_MODULES = {
    'sale',
}

# Módulos de Tema/UI
UI_MODULES = {
    'muk_web_theme',
    'muk_web_appsbar',
    'muk_web_chatter',
    'muk_web_colors',
    'muk_web_dialog',
}

# Combinar todos los módulos esenciales
ESSENTIAL_MODULES = (
    CORE_MODULES |
    POS_MODULES |
    POS_CUSTOM_MODULES |
    STOCK_MODULES |
    ACCOUNTING_MODULES |
    ECUADOR_MODULES |
    HR_MINIMAL_MODULES |
    SALES_MINIMAL_MODULES |
    UI_MODULES
)

# =============================================================================
# MÓDULOS A ELIMINAR DEFINITIVAMENTE
# Estos módulos no son necesarios para POS offline
# =============================================================================

MODULES_TO_REMOVE = {
    # Website / E-commerce (no necesario para offline)
    'website',
    'website_sale',
    'website_sale_loyalty',
    'website_sale_stock',
    'website_livechat',
    'website_blog',
    'website_slides',
    'website_forum',
    'website_event',
    'website_membership',
    'website_payment',
    'custom_website_sale',
    'custom_website_loyalty',

    # HR / Payroll (no necesario para POS offline)
    'hr_payroll',
    'hr_payroll_account',
    'hr_recruitment',
    'hr_holidays',
    'hr_expense',
    'hr_timesheet',
    'hr_attendance',
    'hr_work_entry',
    'hr_work_entry_contract',
    'hr_work_entry_contract_attendance',
    'hr_work_entry_contract_enterprise',
    'hr_contract',
    'ec_payroll',
    'custom_holidays',
    'custom_attendance',
    'custom_employe',
    'employee_shift_scheduling_app',
    'payroll_other_discounts',

    # Helpdesk / Support
    'odoo_website_helpdesk',
    'odoo_website_helpdesk_dashboard',
    'helpdesk',

    # CRM / Sales avanzado
    'crm',
    'sale_crm',
    'sale_management',

    # Project / Tasks
    'project',
    'project_timesheet_holidays',

    # Manufacturing
    'mrp',
    'mrp_account',

    # Purchase (opcional - depende si necesitas compras)
    # 'purchase',
    # 'purchase_stock',

    # Fleet
    'fleet',

    # Events
    'event',
    'event_sale',

    # Survey / Forms
    'survey',
    'formio',

    # Knowledge / Documents
    'document_page',
    'document_page_access_group',
    'document_page_group',
    'document_page_tag',
    'document_url',
    'document_knowledge',

    # Gamification
    'gamification',
    'gamification_custom',

    # Chat / Messaging extras
    'chatbot_message',
    'chatbotapi',
    'im_livechat',

    # Firebase / Push notifications
    'firebase_push_notification',

    # Storage S3 (no necesario offline)
    'attachment_s3',
    'base_attachment_object_storage',

    # Backup automático (no necesario en offline pequeño)
    'auto_database_backup',

    # APIs externas
    'api_client_proassislife',
    'api_store',
    'inventaryapi',
    'conection_promotions_api',

    # Biometrics
    'biometrics_control_access',

    # Otros módulos no esenciales
    'companiesweb',
    'internal_control',
    'allocations_consumable_products',
    'analytic_automatization',
    'analytic_base_department',
    'email_format',
    'export_view_pdf',
    'delete_product_excel',
    'merge_rfq',
    'global_read_only',
    'om_data_remove',
    'all_in_one_dynamic_custom_fields',

    # Reportes avanzados (opcional)
    'account_reports',
    'l10n_ec_reports',
    'l10n_ec_reports_ats',

    # Account extras
    'account_accountant',
    'account_asset_management',
    'account_auto_transfer',
    'account_followup',
    'account_statement_base',
    'account_statement_import_base',
    'account_statement_import_file',
    'account_statement_import_sheet_file',

    # Payment providers (si no usas pagos online)
    'payment_stripe',
    'payment_paymentez',
    'payments_ahorita',
}

# =============================================================================
# MÓDULOS OPCIONALES - Revisar caso por caso
# =============================================================================

OPTIONAL_MODULES = {
    # Guías de remisión (necesario si haces despachos)
    'guide_remision',

    # Dashboard POS
    'dashboard_pos',

    # POS extras que podrían no ser necesarios
    'pos_analytic_account',
    'pos_close_session',
    'pos_controlled_interface',
    'pos_delete_orderline',
    'pos_inventory_regulation',
    'pos_invoice_note',
    'pos_numpad_show_hide',
    'pos_order_search',
    'pos_pads_location',
    'pos_payment_restrictions',
    'pos_restrict',
    'pos_sale_order',
    'pos_search_bar',
    'pos_search_partner',
    'pos_uom',
    'pos_zero_quantity_restrict',
    'point_of_sale_logo',
    'adevx_pos_sales_order',
    'cucu_pos_credit',
    'consolidated_pos',

    # Purchase (si no necesitas compras en offline)
    'purchase',
    'purchase_stock',
    'bi_picking_double_approval',
}


def get_installed_modules(env):
    """Obtiene todos los módulos instalados."""
    return env['ir.module.module'].search([
        ('state', '=', 'installed')
    ])


def get_modules_to_uninstall(env):
    """
    Identifica módulos que pueden ser desinstalados.
    Retorna una lista ordenada por dependencias (primero los que no tienen dependientes).
    """
    installed = get_installed_modules(env)
    to_uninstall = []

    for module in installed:
        if module.name in MODULES_TO_REMOVE:
            to_uninstall.append(module)

    return to_uninstall


def get_module_dependents(env, module_name):
    """Obtiene módulos que dependen del módulo dado."""
    module = env['ir.module.module'].search([('name', '=', module_name)], limit=1)
    if not module:
        return []

    dependents = env['ir.module.module'].search([
        ('state', '=', 'installed'),
        ('dependencies_id.name', '=', module_name)
    ])
    return dependents


def analyze_database(env):
    """Analiza la base de datos y muestra un resumen."""
    installed = get_installed_modules(env)

    print("\n" + "="*70)
    print("ANÁLISIS DE BASE DE DATOS ODOO PARA MINIMIZACIÓN")
    print("="*70)

    print(f"\nTotal de módulos instalados: {len(installed)}")

    # Clasificar módulos
    essential_installed = []
    to_remove = []
    optional = []
    other = []

    for module in installed:
        if module.name in ESSENTIAL_MODULES:
            essential_installed.append(module.name)
        elif module.name in MODULES_TO_REMOVE:
            to_remove.append(module.name)
        elif module.name in OPTIONAL_MODULES:
            optional.append(module.name)
        else:
            other.append(module.name)

    print(f"\n📌 Módulos ESENCIALES instalados: {len(essential_installed)}")
    for name in sorted(essential_installed):
        print(f"   ✓ {name}")

    print(f"\n🗑️  Módulos a ELIMINAR: {len(to_remove)}")
    for name in sorted(to_remove):
        print(f"   ✗ {name}")

    print(f"\n❓ Módulos OPCIONALES (revisar): {len(optional)}")
    for name in sorted(optional):
        print(f"   ? {name}")

    print(f"\n📦 Otros módulos (no clasificados): {len(other)}")
    for name in sorted(other):
        print(f"   - {name}")

    print("\n" + "="*70)
    print(f"RESUMEN: Se pueden eliminar aproximadamente {len(to_remove)} módulos")
    print("="*70)

    return {
        'essential': essential_installed,
        'to_remove': to_remove,
        'optional': optional,
        'other': other
    }


def uninstall_modules(env, module_names, dry_run=True):
    """
    Desinstala los módulos especificados.

    Args:
        env: Odoo environment
        module_names: Lista de nombres de módulos a desinstalar
        dry_run: Si True, solo muestra lo que haría sin ejecutar
    """
    Module = env['ir.module.module']

    print("\n" + "="*70)
    if dry_run:
        print("MODO SIMULACIÓN - No se realizarán cambios")
    else:
        print("⚠️  EJECUTANDO DESINSTALACIÓN - Los cambios son permanentes")
    print("="*70)

    # Ordenar módulos por dependencias (primero los que no tienen dependientes)
    modules_to_process = []
    for name in module_names:
        module = Module.search([('name', '=', name), ('state', '=', 'installed')], limit=1)
        if module:
            dependents = get_module_dependents(env, name)
            installed_dependents = [d.name for d in dependents if d.name in module_names]
            modules_to_process.append({
                'name': name,
                'module': module,
                'dependents': len(installed_dependents)
            })

    # Ordenar: primero los que tienen más dependientes (para desinstalarlos después)
    modules_to_process.sort(key=lambda x: x['dependents'], reverse=True)

    uninstalled = []
    errors = []

    for item in modules_to_process:
        name = item['name']
        module = item['module']

        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Procesando: {name}")

        # Verificar dependientes
        dependents = get_module_dependents(env, name)
        active_dependents = [d for d in dependents if d.state == 'installed' and d.name not in module_names]

        if active_dependents:
            dep_names = ', '.join([d.name for d in active_dependents])
            print(f"   ⚠️  Tiene dependientes activos: {dep_names}")
            print(f"   ⏭️  Saltando (desinstalar dependientes primero)")
            continue

        if not dry_run:
            try:
                module.button_immediate_uninstall()
                env.cr.commit()
                print(f"   ✓ Desinstalado correctamente")
                uninstalled.append(name)
            except Exception as e:
                print(f"   ✗ Error: {str(e)}")
                errors.append({'name': name, 'error': str(e)})
                env.cr.rollback()
        else:
            print(f"   → Se desinstalaría")
            uninstalled.append(name)

    print("\n" + "="*70)
    print(f"RESUMEN:")
    print(f"  {'Desinstalados' if not dry_run else 'A desinstalar'}: {len(uninstalled)}")
    print(f"  Errores: {len(errors)}")
    print("="*70)

    return uninstalled, errors


def run_minimization(env, dry_run=True, include_optional=False):
    """
    Ejecuta el proceso completo de minimización.

    Args:
        env: Odoo environment
        dry_run: Si True, solo simula (recomendado primero)
        include_optional: Si True, también elimina módulos opcionales
    """
    print("\n" + "="*70)
    print("MINIMIZACIÓN DE BASE DE DATOS ODOO PARA POS OFFLINE")
    print("="*70)
    print("\n⚠️  ADVERTENCIA: Este proceso eliminará módulos de la base de datos")
    print("⚠️  Asegúrese de tener un backup antes de continuar")

    # Analizar primero
    analysis = analyze_database(env)

    # Determinar qué eliminar
    modules_to_remove = analysis['to_remove'].copy()
    if include_optional:
        modules_to_remove.extend(analysis['optional'])

    if not modules_to_remove:
        print("\n✓ No hay módulos para eliminar")
        return

    # Ejecutar desinstalación
    uninstalled, errors = uninstall_modules(env, modules_to_remove, dry_run=dry_run)

    if not dry_run and uninstalled:
        print("\n🔄 Limpiando base de datos...")
        # Limpiar caché y actualizar
        env['ir.module.module'].update_list()

        print("\n✓ Proceso completado")
        print("\nPróximos pasos recomendados:")
        print("1. Reiniciar el servidor Odoo")
        print("2. Ejecutar: python odoo-bin -d <database> --update=all")
        print("3. Verificar funcionamiento del POS")


# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

if __name__ == '__main__' or 'env' in dir():
    # Si se ejecuta desde shell de Odoo, 'env' ya existe
    if 'env' in dir():
        print("\nEjecutando desde Odoo Shell...")
        print("\nOpciones disponibles:")
        print("  1. analyze_database(env) - Solo analizar")
        print("  2. run_minimization(env, dry_run=True) - Simular")
        print("  3. run_minimization(env, dry_run=False) - Ejecutar")
        print("\nEjecutando análisis inicial...")
        analyze_database(env)
    else:
        print("Este script debe ejecutarse desde el shell de Odoo:")
        print("  python odoo-bin shell -d <database>")
        print("  >>> exec(open('addons/pos_offline_sync/scripts/minimize_database.py').read())")
