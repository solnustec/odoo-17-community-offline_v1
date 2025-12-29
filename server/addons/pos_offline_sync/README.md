# POS Offline Sync - Módulo de Sincronización Offline para Odoo 17

## Descripción General

El módulo **pos_offline_sync** permite que los puntos de venta (POS) de Odoo 17 operen de manera independiente sin necesidad de conexión constante a Internet. Los registros generados se almacenan localmente y se sincronizan automáticamente con el servidor cloud cuando la conexión está disponible.

### Características Principales

- **Operación Offline Completa**: El POS puede funcionar sin conexión a Internet
- **Sincronización Bidireccional**: Envío y recepción de datos entre POS offline y cloud
- **Cola de Sincronización**: Gestión de registros pendientes con reintentos automáticos
- **Configuración por Sucursal**: Cada almacén puede tener su propia configuración
- **Sin Registros Contables**: Opción para omitir contabilidad en modo offline
- **Soporte para 200+ Sucursales**: Diseñado para escalabilidad empresarial

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SERVIDOR CLOUD                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  pos.order  │  │ res.partner │  │   product   │  ...             │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                    API REST (JSON)
                            │
┌───────────────────────────┴─────────────────────────────────────────┐
│                      POS OFFLINE (SUCURSAL)                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    pos.sync.manager                          │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │    PUSH     │  │    PULL     │  │   SERIALIZE │         │    │
│  │  │  (Upload)   │  │  (Download) │  │   (JSON)    │         │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                       │
│  ┌───────────────────────────┴───────────────────────────────────┐  │
│  │                     pos.sync.queue                             │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │  │
│  │  │ pending  │→ │processing│→ │  synced  │  │  error   │      │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│  ┌───────────────────────────┴───────────────────────────────────┐  │
│  │                     pos.sync.config                            │  │
│  │  • warehouse_id: Almacén de la sucursal                       │  │
│  │  • cloud_url: URL del servidor cloud                          │  │
│  │  • api_key: Autenticación                                     │  │
│  │  • sync_interval: Frecuencia de sincronización                │  │
│  │  • operation_mode: offline / hybrid / sync_on_demand          │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Instalación

### Requisitos Previos

- Odoo 17 Community Edition
- Módulos requeridos:
  - `point_of_sale`
  - `stock`
  - `pos_custom_check`

### Pasos de Instalación

1. **Copiar el módulo al directorio de addons**:
```bash
cp -r pos_offline_sync /path/to/odoo/addons/
```

2. **Actualizar la lista de módulos**:
```bash
./odoo-bin -c odoo.conf -u pos_offline_sync -d database_name --stop-after-init
```

3. **Instalar desde la interfaz de Odoo**:
   - Ir a Aplicaciones
   - Buscar "POS Offline Sync"
   - Hacer clic en "Instalar"

---

## Configuración

### 1. Configuración de Sucursal

Ir a **Punto de Venta → Configuración → Sincronización Offline → Configuración**

#### Campos Principales:

| Campo | Descripción |
|-------|-------------|
| **Nombre** | Identificador de la configuración |
| **Almacén/Sucursal** | Almacén asociado a este POS offline |
| **URL del Servidor Cloud** | URL del servidor Odoo principal (ej: `https://cloud.miempresa.com`) |
| **API Key** | Clave de autenticación para la sincronización |
| **Intervalo de Sincronización** | Frecuencia en minutos (por defecto: 5) |
| **Modo de Operación** | `offline`, `hybrid`, o `sync_on_demand` |

### 2. Modos de Operación

#### Solo Offline
```
operation_mode = 'offline'
```
- El POS opera completamente desconectado
- No se intenta sincronización automática
- Ideal para zonas sin conectividad

#### Híbrido (Recomendado)
```
operation_mode = 'hybrid'
```
- Sincronización automática cuando hay conexión
- Fallback a modo offline si no hay conexión
- Ideal para conexiones intermitentes

#### Sincronización Manual
```
operation_mode = 'sync_on_demand'
```
- Sincronización solo cuando el usuario lo solicita
- Útil para control total sobre cuándo sincronizar

### 3. Entidades Sincronizables

Configure qué datos sincronizar:

```python
sync_orders = True          # pos.order
sync_partners = True        # res.partner
sync_products = True        # product.product
sync_stock = True          # stock.quant
sync_loyalty = True        # loyalty.program, loyalty.rule, loyalty.reward
sync_employees = True      # hr.employee
sync_payment_methods = True # pos.payment.method
```

### 4. Restricciones Contables

Para evitar duplicados contables:

```python
skip_accounting = True           # No generar asientos contables
skip_invoice_generation = True   # No generar facturas automáticamente
```

---

## Configuración por Variables de Entorno (.env)

Puede configurar la sucursal mediante variables de entorno:

```bash
# .env
POS_OFFLINE_SYNC_ENABLED=true
POS_OFFLINE_WAREHOUSE_ID=5
POS_OFFLINE_CLOUD_URL=https://cloud.miempresa.com
POS_OFFLINE_API_KEY=your_secret_api_key
POS_OFFLINE_SYNC_INTERVAL=5
POS_OFFLINE_MODE=hybrid
```

### Lectura en odoo.conf:

```ini
[options]
; ... otras configuraciones ...

; POS Offline Sync
pos_offline_sync_enabled = True
pos_offline_warehouse_id = 5
pos_offline_cloud_url = https://cloud.miempresa.com
pos_offline_api_key = your_secret_api_key
```

---

## API Endpoints

### Health Check

```bash
POST /pos_offline_sync/ping
```

**Respuesta:**
```json
{
    "success": true,
    "message": "POS Offline Sync está operativo",
    "timestamp": "2024-12-09T10:30:00",
    "version": "17.0.1.0.0"
}
```

### Push (Subir Datos)

```bash
POST /pos_offline_sync/push
Content-Type: application/json
Authorization: Bearer YOUR_API_KEY

{
    "model": "pos.order",
    "warehouse_id": 1,
    "records": [
        {
            "queue_id": 123,
            "local_id": 456,
            "operation": "create",
            "data": {...}
        }
    ]
}
```

### Pull (Descargar Datos)

```bash
POST /pos_offline_sync/pull
Content-Type: application/json
Authorization: Bearer YOUR_API_KEY

{
    "warehouse_id": 1,
    "entities": ["product.product", "res.partner", "loyalty.program"],
    "last_sync": "2024-12-08T10:30:00"
}
```

### Obtener Stock

```bash
POST /pos_offline_sync/stock
Content-Type: application/json

{
    "warehouse_id": 1,
    "product_ids": [1, 2, 3]  // Opcional
}
```

### Obtener Productos

```bash
POST /pos_offline_sync/products
Content-Type: application/json

{
    "warehouse_id": 1,
    "last_sync": "2024-12-08T10:30:00",
    "limit": 1000,
    "offset": 0
}
```

---

## Flujo de Sincronización

### 1. Creación de Orden en POS Offline

```
[POS UI] → [pos.order.create()] → [pos.sync.queue.add_to_queue()]
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │ state: pending  │
                                  │ priority: 2     │
                                  │ data_json: {...}│
                                  └─────────────────┘
```

### 2. Sincronización Automática (Cron)

```
[ir.cron] → [pos.sync.manager.cron_sync_all()]
                       │
                       ▼
            ┌─────────────────────┐
            │ get_ready_for_sync()│
            └─────────────────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │ _push_to_cloud()    │──────────► [Cloud Server]
            └─────────────────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │ mark_as_synced()    │
            │ cloud_record_id: 789│
            └─────────────────────┘
```

### 3. Manejo de Errores

```
[Error de conexión]
        │
        ▼
┌─────────────────────┐
│ mark_as_error()     │
│ attempt_count: +1   │
│ next_retry_date:    │
│   2^attempt * 60s   │
└─────────────────────┘
        │
        ▼
    [Backoff exponencial]
    1min → 2min → 4min → 8min → ... → max 1h
```

---

## Optimizaciones y Buenas Prácticas

### 1. Configuración Óptima por Sucursal

```python
# Para sucursales con conexión intermitente
config = {
    'operation_mode': 'hybrid',
    'sync_interval': 5,          # 5 minutos
    'batch_size': 100,           # Lotes pequeños
    'retry_attempts': 5,         # Más reintentos
    'sync_timeout': 60,          # Timeout mayor
}

# Para sucursales con buena conexión
config = {
    'operation_mode': 'hybrid',
    'sync_interval': 1,          # 1 minuto
    'batch_size': 500,           # Lotes más grandes
    'retry_attempts': 3,
    'sync_timeout': 30,
}
```

### 2. Optimización de Stock

Cada sucursal offline solo debe tener **UN** almacén:

```python
# Correcto: Un almacén por sucursal offline
warehouse_sucursal_1 = stock.warehouse(name='Sucursal Centro')
sync_config_1 = pos.sync.config(warehouse_id=warehouse_sucursal_1.id)

# Incorrecto: Múltiples almacenes por sucursal
# Esto causa problemas de sincronización
```

### 3. Sincronización Selectiva de Productos

Configure qué productos sincronizar:

```python
# Solo sincronizar productos disponibles en POS
domain = [('available_in_pos', '=', True)]

# Filtrar por categoría si es necesario
domain.append(('categ_id', 'in', [1, 2, 3]))
```

### 4. Limpieza Automática

Los cron jobs limpian datos antiguos:

```xml
<!-- Limpieza de registros sincronizados (30 días) -->
<record id="cron_pos_sync_cleanup" model="ir.cron">
    <field name="interval_number">1</field>
    <field name="interval_type">days</field>
</record>

<!-- Limpieza de logs (90 días) -->
<record id="cron_pos_sync_log_cleanup" model="ir.cron">
    <field name="interval_number">1</field>
    <field name="interval_type">weeks</field>
</record>
```

### 5. Monitoreo de Sincronización

#### Verificar estado desde consola:

```python
# Obtener configuraciones con errores
configs_error = env['pos.sync.config'].search([
    ('sync_status', '=', 'error')
])

# Ver registros pendientes por almacén
for config in configs_error:
    pending = env['pos.sync.queue'].search_count([
        ('warehouse_id', '=', config.warehouse_id.id),
        ('state', 'in', ['pending', 'error'])
    ])
    print(f"{config.name}: {pending} pendientes")

# Estadísticas de los últimos 7 días
stats = env['pos.sync.log'].get_sync_stats(config_id, days=7)
print(f"Tasa de éxito: {stats['success_rate']}%")
```

### 6. Consideraciones de Rendimiento

| Parámetro | Valor Recomendado | Impacto |
|-----------|-------------------|---------|
| `batch_size` | 100-500 | Más pequeño = más estable, más lento |
| `sync_interval` | 5-15 min | Menor = más actualizaciones, más recursos |
| `sync_timeout` | 30-60 seg | Mayor = tolera conexiones lentas |
| `retry_attempts` | 3-5 | Más = mayor tolerancia a fallos |

---

## Configuración para 200 Sucursales

### Arquitectura Recomendada

```
┌─────────────────────────────────────────────────────────────────┐
│                      SERVIDOR CLOUD CENTRAL                      │
│  • Base de datos maestra                                        │
│  • Todas las configuraciones de sucursales                      │
│  • Consolidación de datos                                       │
│  • Generación de reportes                                       │
└─────────────────────────────────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
    ┌──────┴──────┐     ┌──────┴──────┐     ┌──────┴──────┐
    │ Sucursal 1  │     │ Sucursal 2  │     │ Sucursal N  │
    │ warehouse:1 │     │ warehouse:2 │     │ warehouse:N │
    │ POS offline │     │ POS offline │     │ POS offline │
    └─────────────┘     └─────────────┘     └─────────────┘
```

### Script de Configuración Masiva

```python
# Script para crear configuraciones de 200 sucursales
warehouses = env['stock.warehouse'].search([])

for wh in warehouses:
    existing = env['pos.sync.config'].search([
        ('warehouse_id', '=', wh.id)
    ])

    if not existing:
        env['pos.sync.config'].create({
            'name': f'Sync - {wh.name}',
            'warehouse_id': wh.id,
            'cloud_url': 'https://cloud.miempresa.com',
            'api_key': generate_api_key(),
            'operation_mode': 'hybrid',
            'sync_interval': 5,
            'sync_orders': True,
            'sync_partners': True,
            'sync_products': True,
            'sync_stock': True,
            'skip_accounting': True,
            'skip_invoice_generation': True,
        })
```

---

## Transferencias entre Sucursales

Las transferencias entre sucursales **NO** se manejan en modo offline. Deben realizarse a través del API cuando hay conexión:

```bash
POST /api/stock_picking/create
Content-Type: application/json

{
    "location_id": "warehouse_origen_external_id",
    "location_dest_id": "warehouse_destino_external_id",
    "scheduled_date": "2024-12-09 10:00:00",
    "move_lines": [
        {
            "product_template_id": "product_external_id",
            "product_uom_qty": 50.0
        }
    ],
    "state": "done"
}
```

---

## Troubleshooting

### Error: "No hay configuración de sincronización"

**Causa**: El almacén del POS no tiene configuración asociada.

**Solución**:
```python
# Crear configuración para el almacén
env['pos.sync.config'].create({
    'name': 'Mi Sucursal',
    'warehouse_id': warehouse_id,
    'operation_mode': 'hybrid',
    ...
})
```

### Error: "Error de conexión"

**Causa**: No se puede alcanzar el servidor cloud.

**Solución**:
1. Verificar URL del servidor cloud
2. Verificar conectividad de red
3. Verificar que el API key sea válido
4. Aumentar `sync_timeout` si la conexión es lenta

### Error: "Registro duplicado"

**Causa**: El registro ya existe en el cloud.

**Solución**:
1. El sistema busca registros existentes por `id_database_old`, `vat`, o `barcode`
2. Si encuentra coincidencia, actualiza en lugar de crear
3. Verificar que los identificadores únicos estén correctamente configurados

### Registros atascados en "processing"

**Causa**: El proceso de sincronización se interrumpió.

**Solución**:
```python
# Resetear registros atascados
stuck = env['pos.sync.queue'].search([
    ('state', '=', 'processing'),
    ('last_attempt_date', '<', datetime.now() - timedelta(hours=1))
])
stuck.reset_to_pending()
```

---

## Estructura del Módulo

```
pos_offline_sync/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   └── sync_controller.py       # API endpoints
├── models/
│   ├── __init__.py
│   ├── pos_sync_config.py       # Configuración por sucursal
│   ├── pos_sync_queue.py        # Cola de sincronización
│   ├── pos_sync_manager.py      # Gestor de sincronización
│   ├── pos_sync_log.py          # Logs de operaciones
│   ├── pos_order.py             # Extensión pos.order
│   └── pos_session.py           # Extensión pos.session
├── security/
│   └── ir.model.access.csv      # Permisos de acceso
├── views/
│   ├── pos_sync_config_views.xml
│   ├── pos_sync_queue_views.xml
│   ├── pos_sync_log_views.xml
│   └── pos_sync_menu.xml
├── data/
│   ├── config_data.xml          # Parámetros del sistema
│   └── cron.xml                 # Tareas programadas
└── static/
    └── description/
        └── icon.png
```

---

## Licencia

Este módulo está licenciado bajo LGPL-3.

---

## Soporte

Para soporte técnico, contactar a:
- **Empresa**: SolNusTec
- **Website**: https://www.solnustec.com

---

## Changelog

### Versión 17.0.1.0.0
- Versión inicial
- Sincronización bidireccional
- Cola de sincronización con reintentos
- Configuración por sucursal
- API REST completa
- Omisión de registros contables en modo offline
