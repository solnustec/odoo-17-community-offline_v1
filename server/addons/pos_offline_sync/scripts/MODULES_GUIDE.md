# Guía de Módulos para POS Offline con Facturación Ecuador

## Resumen

Esta guía lista los módulos necesarios para ejecutar un POS offline ligero
con facturación electrónica de Ecuador.

## Módulos Esenciales (NO desinstalar)

### Core de Odoo
| Módulo | Descripción |
|--------|-------------|
| `base` | Núcleo de Odoo |
| `web` | Interfaz web |
| `bus` | Bus de eventos |
| `mail` | Sistema de correo/mensajería |
| `contacts` | Gestión de contactos |
| `product` | Gestión de productos |
| `uom` | Unidades de medida |
| `digest` | Resúmenes periódicos |
| `barcodes` | Códigos de barras |
| `web_editor` | Editor web |

### Point of Sale
| Módulo | Descripción |
|--------|-------------|
| `point_of_sale` | POS base |
| `pos_loyalty` | Programas de lealtad/promociones |
| `pos_sale` | Integración POS-Ventas |
| `pos_hr` | Empleados en POS |

### POS Custom (tus módulos)
| Módulo | Descripción |
|--------|-------------|
| `pos_offline_sync` | Sincronización offline principal |
| `pos_custom_check` | Pagos con cheque y digitales |
| `pos_connect_flask` | Storage JSON para POS |
| `pos_restrict_product_stock` | Control de stock en POS |
| `multi_barcode_for_products` | Múltiples códigos de barras |
| `pos_receipt_extend` | Recibos extendidos |
| `pos_custom_ticket_refund` | Tickets de reembolso |
| `pos_credit_note` | Notas de crédito POS |
| `custom_receipts_for_pos` | Recibos personalizados |

### Stock/Inventario
| Módulo | Descripción |
|--------|-------------|
| `stock` | Gestión de inventario |
| `stock_account` | Contabilidad de stock |

### Contabilidad Base
| Módulo | Descripción |
|--------|-------------|
| `account` | Contabilidad base |
| `account_edi` | Facturación electrónica |
| `account_payment` | Pagos |

### Localización Ecuador (CRÍTICOS)
| Módulo | Descripción |
|--------|-------------|
| `l10n_ec` | Localización Ecuador base |
| `l10n_ec_edi` | Facturación electrónica Ecuador |
| `l10n_ec_edi_pos` | Facturación electrónica POS Ecuador |
| `l10n_latam_base` | Base LATAM |
| `l10n_latam_invoice_document` | Documentos LATAM |
| `l10n_ec_invoice_identification` | Identificación en facturas |

### RRHH Mínimo
| Módulo | Descripción |
|--------|-------------|
| `hr` | Recursos humanos básico (para empleados POS) |

### Ventas Mínimo
| Módulo | Descripción |
|--------|-------------|
| `sale` | Ventas básico |

### UI/Tema
| Módulo | Descripción |
|--------|-------------|
| `muk_web_theme` | Tema MUK |
| `muk_web_appsbar` | Barra de apps |
| `muk_web_chatter` | Chatter mejorado |
| `muk_web_colors` | Colores |
| `muk_web_dialog` | Diálogos |

---

## Módulos a ELIMINAR

### Website / E-commerce
- `website` - No necesario para offline
- `website_sale` - Tienda online
- `website_sale_loyalty` - Lealtad web
- `custom_website_sale` - Personalización web
- `custom_website_loyalty` - Lealtad web custom

### RRHH / Nómina (no necesario para POS)
- `hr_payroll` - Nómina
- `hr_payroll_account` - Contabilidad nómina
- `hr_recruitment` - Reclutamiento
- `hr_holidays` - Vacaciones
- `hr_attendance` - Asistencia
- `hr_expense` - Gastos
- `ec_payroll` - Nómina Ecuador
- `custom_holidays` - Vacaciones custom
- `custom_attendance` - Asistencia custom
- `employee_shift_scheduling_app` - Turnos

### Helpdesk / Soporte
- `odoo_website_helpdesk` - Mesa de ayuda
- `odoo_website_helpdesk_dashboard` - Dashboard helpdesk

### Documentos / Conocimiento
- `document_page` - Páginas de documentos
- `document_knowledge` - Base de conocimiento
- `formio` - Formularios

### APIs / Integraciones externas
- `api_client_proassislife` - API externa
- `api_store` - API tienda
- `inventaryapi` - API inventario
- `firebase_push_notification` - Notificaciones push
- `chatbotapi` - Chatbot

### Storage externo
- `attachment_s3` - Almacenamiento S3
- `base_attachment_object_storage` - Storage objetos
- `auto_database_backup` - Backup automático

### Gamification / Otros
- `gamification` - Gamificación
- `gamification_custom` - Gamificación custom
- `biometrics_control_access` - Control biométrico

### Reportes avanzados (opcional eliminar)
- `account_reports` - Reportes contables
- `l10n_ec_reports` - Reportes Ecuador
- `l10n_ec_reports_ats` - ATS Ecuador

---

## Módulos Opcionales (Revisar caso por caso)

| Módulo | Descripción | Recomendación |
|--------|-------------|---------------|
| `guide_remision` | Guías de remisión | Mantener si haces despachos |
| `dashboard_pos` | Dashboard POS | Eliminar si no usas |
| `purchase` | Compras | Mantener si compras en offline |
| `pos_analytic_account` | Cuenta analítica | Eliminar si no usas analítica |
| `pos_inventory_regulation` | Regulación inventario | Revisar uso |
| `pos_payment_restrictions` | Restricciones pago | Revisar uso |
| `consolidated_pos` | POS consolidado | Revisar uso |

---

## Proceso de Minimización

### Paso 1: Backup
```bash
pg_dump -U odoo -h localhost odoo_offline > backup_before_minimize.sql
```

### Paso 2: Análisis (sin cambios)
```bash
cd /home/user/odoo-17-community
./addons/pos_offline_sync/scripts/run_minimize.sh odoo_offline
```

### Paso 3: Ejecutar minimización
```bash
./addons/pos_offline_sync/scripts/run_minimize.sh odoo_offline --execute
```

### Paso 4: Reiniciar y actualizar
```bash
# Reiniciar Odoo
systemctl restart odoo

# O manualmente:
python odoo-bin -d odoo_offline --update=all --stop-after-init
```

### Paso 5: Verificar
- Probar POS
- Verificar facturación
- Probar sincronización

---

## Estimación de Reducción

| Métrica | Antes | Después (estimado) |
|---------|-------|-------------------|
| Módulos instalados | ~100+ | ~40-50 |
| Uso RAM | 2-4 GB | 1-2 GB |
| Tiempo inicio | 30-60s | 15-30s |
| Espacio BD | 1-2 GB | 500 MB - 1 GB |

---

## Notas Importantes

1. **Backup obligatorio** antes de cualquier operación
2. **Probar en ambiente de prueba** antes de producción
3. **Verificar dependencias** - algunos módulos pueden tener dependencias no documentadas
4. **Mantener registro** de módulos eliminados por si necesitas reinstalarlos

## Soporte

Para problemas con la minimización, contactar a SolNusTec.
