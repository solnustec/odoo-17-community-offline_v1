# Reglas de Abastecimiento para Gestión de Inventario

## Descripción General

Módulo de Odoo 17 que permite configurar y ejecutar **reglas automáticas de reabastecimiento** para calcular los niveles óptimos de inventario (máximos, mínimos y puntos de reorden) basándose en el historial de ventas y/o transferencias.

**Autor:** SOLNUSTEC SA
**Versión:** 0.1
**Categoría:** Inventory

## Dependencias

- `base`
- `stock`
- `point_of_sale`
- `sales_report`

---

## Estructura del Módulo

```
replenishment_inventory/
├── __init__.py
├── __manifest__.py
├── README.md
├── data/
│   └── ir_cron_queue_processor.xml   # Crons para procesamiento
├── models/
│   ├── __init__.py
│   ├── stock_rule_replenishment.py   # Motor de reglas (principal)
│   ├── stock_warehouse_orderpoint.py # Extensión de puntos de pedido
│   ├── stock_warehouse.py            # Configuración de almacén
│   │
│   │   # Arquitectura de 4 Capas (Alto Volumen)
│   ├── product_replenishment_queue.py     # Cola de eventos
│   ├── product_replenishment_dead_letter.py # Dead letter queue
│   ├── product_sales_stats_daily.py       # Stats diarios agregados
│   ├── product_sales_stats_rolling.py     # Stats rolling precalculados
│   ├── product_sale_event_log.py          # Log particionado
│   ├── queue_processor.py                 # Procesador de cola
│   └── data_migration.py                  # Utilidades de migración
├── security/
│   └── ir.model.access.csv
└── views/
    ├── replenishment_monitoring_views.xml  # Vistas de monitoreo
    └── stock_warehouse_orderpoint.xml
```

---

## Arquitectura de 4 Capas

El módulo implementa una arquitectura de 4 capas optimizada para **alto volumen (2M+ registros)**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CAPA 1: INGESTA                                  │
│  product.warehouse.sale.summary.create()                            │
│  └── Inserción dual: tabla original + cola de eventos              │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CAPA 2: COLA                                     │
│  product.replenishment.queue                                        │
│  └── DELETE...RETURNING (sin locks, atómico)                       │
│  └── Backpressure automático                                        │
└─────────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
┌──────────────────────────────┐  ┌────────────────────────────────────┐
│        Dead Letter           │  │      CAPA 3: AGREGACIÓN            │
│  (eventos fallidos)          │  │  product.sales.stats.daily         │
│  └── Reintentos manuales     │  │  └── UPSERT incremental            │
└──────────────────────────────┘  └────────────────────────────────────┘
                                                │
                                                ▼
                                  ┌────────────────────────────────────┐
                                  │      CAPA 4: PRECÁLCULO            │
                                  │  product.sales.stats.rolling       │
                                  │  └── Stats 30/60/90 días           │
                                  │  └── Consulta O(1) por orderpoints │
                                  └────────────────────────────────────┘
                                                │
                                                ▼
                                  ┌────────────────────────────────────┐
                                  │      CÁLCULO MAX/MIN               │
                                  │  stock.rule.replenishment          │
                                  │  └── Usa rolling_stats (O(1))      │
                                  │  └── Evalúa reglas Python          │
                                  └────────────────────────────────────┘
                                                │
                                                ▼
                                  ┌────────────────────────────────────┐
                                  │      ORDERPOINTS                   │
                                  │  stock.warehouse.orderpoint        │
                                  │  └── product_max_qty (MAX)         │
                                  │  └── product_min_qty (MIN)         │
                                  │  └── point_reorder                 │
                                  └────────────────────────────────────┘
                                                │
                                                ▼
                                  ┌────────────────────────────────────┐
                                  │      LOG PARTICIONADO              │
                                  │  product.sale.event.log            │
                                  │  └── Particionado por día          │
                                  │  └── Auditoría y análisis          │
                                  └────────────────────────────────────┘
```

---

## Flujo Completo: De la Venta al Reabastecimiento

### Fase 1: Ingesta (Síncrono)

Cuando se registra una venta o transferencia:

```python
# Nueva venta desde POS, API o importación
env['product.warehouse.sale.summary'].create({
    'date': '2025-01-15',
    'product_id': 123,
    'warehouse_id': 1,
    'quantity_sold': 10.0,
    'record_type': 'sale',
})
```

**Internamente:**
1. Se guarda el registro original
2. Se encola automáticamente en `product.replenishment.queue`

El usuario recibe respuesta inmediata. El procesamiento pesado es asíncrono.

---

### Fase 2: Procesamiento de Cola (Cron cada 1 minuto)

```python
# El cron ejecuta:
Processor = env['replenishment.queue.processor']
result = Processor.process_queue(batch_size=1000)
```

**El procesador hace TODO en un solo flujo:**
1. Consume eventos con `DELETE...RETURNING` (sin locks)
2. Actualiza `product.sales.stats.daily` (UPSERT)
3. Recalcula `product.sales.stats.rolling` (30/60/90 días)
4. **Calcula MAX/MIN usando reglas de `stock.rule.replenishment`**
5. **Actualiza/crea orderpoints automáticamente**
6. Registra en `product.sale.event.log` (particionado)
7. Si falla, envía a `product.replenishment.dead.letter`

**Resultado del procesamiento:**
```python
{
    'batch_id': 'a1b2c3d4',
    'events_processed': 1500,
    'daily_stats_updated': 800,
    'rolling_stats_updated': 2400,  # 800 × 3 tipos (sale, transfer, combined)
    'orderpoints_updated': 750,
    'orderpoints_created': 50,
    'time_elapsed': 12.5
}
```

---

### Fase 3: Consulta desde Orderpoints (O(1))

```python
# Obtener estadísticas precalculadas
orderpoint = env['stock.warehouse.orderpoint'].browse(1)
stats = orderpoint.get_replenishment_stats(days=30)
# Retorna: {mean, stddev, cv, total_qty, days_with_sales}

# Calcular punto de reorden
rop = orderpoint.calculate_reorder_point(
    lead_time_days=7,
    service_level_z=1.65,  # 95% nivel servicio
    days=30
)

# Calcular cantidad máxima
max_qty = orderpoint.calculate_max_qty(
    lead_time_days=7,
    review_period_days=7,
    service_level_z=1.65,
    days=30
)
```

---

## Guía de Uso

### 1. Actualizar el Módulo

```bash
./odoo-bin -c odoo.conf -u replenishment_inventory --stop-after-init
```

### 2. Desactivar Cron Anterior (IMPORTANTE)

Para bases de datos existentes, desactivar el cron viejo:

**Opción A - Desde UI:**
1. Ir a **Configuración > Técnico > Automatización > Acciones Planificadas**
2. Buscar "Reabastecimiento: Procesamiento Alto Volumen"
3. Desmarcar "Activo"

**Opción B - Desde shell:**
```python
cron = env.ref('replenishment_inventory.ir_cron_process_replenishment_high_volume')
cron.active = False
env.cr.commit()
```

### 3. Migrar Datos Históricos (OPCIONAL)

> **Nota:** Este paso es OPCIONAL. Si no lo ejecutas, el sistema empezará
> a acumular estadísticas a partir de los nuevos eventos que lleguen.
> Solo es necesario si quieres estadísticas históricas desde el día 1.

```python
# En shell de Odoo (OPCIONAL)
./odoo-bin shell -c odoo.conf

env['replenishment.data.migration'].migrate_to_new_architecture(
    days_back=90,
    batch_size=5000
)
env.cr.commit()
```

### 4. Verificar el Sistema

```python
# Script de verificación
print("=== VERIFICACIÓN ===")

# Cola de eventos
Queue = env['product.replenishment.queue']
stats = Queue.get_queue_stats()
print(f"Cola: {stats['total_count']} eventos pendientes")

# Dead letter
DeadLetter = env['product.replenishment.dead.letter']
pending = DeadLetter.search_count([('state', '=', 'pending')])
print(f"Fallidos: {pending}")

# Rolling stats
RollingStats = env['product.sales.stats.rolling']
total = RollingStats.search_count([])
print(f"Rolling stats: {total} registros")

# Backpressure
bp = Queue.check_backpressure()
print(f"Backpressure: {'ALERTA' if bp['has_backpressure'] else 'OK'}")
```

---

## Monitoreo

### Acceso a Vistas

Ir a: **Inventario > Gestión de Almacén > Monitoreo Reabastecimiento**

| Menú | Descripción |
|------|-------------|
| Cola de Eventos | Eventos pendientes de procesar |
| Eventos Fallidos | Dead letter queue |
| Stats Diarios | Agregados por día |
| Stats Rolling | Estadísticas 30/60/90 días |

### Crons Automáticos

| Cron | Intervalo | Descripción |
|------|-----------|-------------|
| **Queue Processor** | 1 minuto | Procesa cola → Stats → **MAX/MIN** → Orderpoints |
| Partition Management | 1 día | Gestiona particiones del log |
| Data Cleanup | 1 día | Elimina datos > 90 días |

**El cron principal es `Reabastecimiento: Procesador de Cola (4-Capas)`** que hace todo:
- Consume eventos de la cola
- Actualiza estadísticas diarias y rolling
- **Calcula MAX/MIN usando las reglas configuradas**
- Crea/actualiza orderpoints

Para ver estado: **Configuración > Técnico > Automatización > Acciones Planificadas**

---

## Modelos Principales

### `product.replenishment.queue` - Cola de Eventos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `product_id` | Many2one | Producto |
| `warehouse_id` | Many2one | Almacén |
| `quantity` | Float | Cantidad del evento |
| `event_date` | Date | Fecha del evento |
| `record_type` | Selection | 'sale' o 'transfer' |
| `retry_count` | Integer | Intentos de procesamiento |

**Métodos:**
```python
Queue.consume_batch(batch_size=1000)  # Consumo atómico
Queue.enqueue_event(...)              # Encolar evento
Queue.check_backpressure()            # Detectar sobrecarga
```

---

### `product.sales.stats.rolling` - Stats Precalculados

| Campo | Descripción |
|-------|-------------|
| `mean_30d/60d/90d` | Media diaria por período |
| `stddev_30d/60d/90d` | Desviación estándar |
| `cv_30d/60d/90d` | Coeficiente de variación |
| `total_qty_30d/60d/90d` | Total del período |
| `days_with_sales_30d/60d/90d` | Días con ventas |

**Métodos:**
```python
RollingStats.get_stats(product_id, warehouse_id, record_type, days)
RollingStats.update_rolling_stats(product_id, warehouse_id, record_type)
```

---

### `stock.warehouse.orderpoint` (Extensión)

| Campo | Descripción |
|-------|-------------|
| `rolling_mean_30d` | Media diaria (computed) |
| `rolling_stddev_30d` | Desviación estándar (computed) |
| `rolling_cv_30d` | Coeficiente de variación (computed) |

**Métodos:**
```python
orderpoint.get_replenishment_stats(days=30)
orderpoint.calculate_reorder_point(lead_time_days, service_level_z, days)
orderpoint.calculate_max_qty(lead_time_days, review_period_days, service_level_z, days)
```

---

## Configuración

### Almacén

Ir a **Inventario > Configuración > Almacenes** y activar:
- ☑ Reabastecimiento basado en Ventas
- ☑ Reabastecimiento basado en Transferencias

### Variables de Entorno (Opcional)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ODOO_REPLENISHMENT_BATCH_SIZE` | 500 | Tamaño de lotes |
| `ODOO_REPLENISHMENT_CACHE_TTL` | 300 | TTL caché (segundos) |
| `ODOO_REPLENISHMENT_TIMEOUT` | 240 | Timeout procesamiento |

---

## Sistema de Particionado (Event Log)

El módulo implementa **particionado nativo de PostgreSQL** para la tabla de log de eventos (`product.sale.event.log`), optimizando el rendimiento y facilitando el mantenimiento en bases de datos de alto volumen.

### ¿Dónde se aplica en la Arquitectura de 4 Capas?

El particionado se aplica en el **Log de Auditoría** que se escribe al final del procesamiento de cada batch:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CAPA 2: COLA (queue_processor.py)                │
│                    _process_batch()                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Consume eventos de la cola (DELETE...RETURNING)                │
│  2. Valida producto/warehouse existen                               │
│  3. UPSERT en product.sales.stats.daily ──────────► Capa 3         │
│  4. Actualiza product.sales.stats.rolling ────────► Capa 4         │
│  5. Calcula MAX/MIN con reglas                                      │
│  6. Crea/actualiza orderpoints                                      │
│                                                                     │
│  7. ══════════════════════════════════════════════════════════     │
│     ║  EventLog.log_events(log_events, batch_id)  ║◄── AQUÍ       │
│     ║  Registra en tabla PARTICIONADA             ║                 │
│     ══════════════════════════════════════════════════════════     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Código en `queue_processor.py` (líneas 229-247):**

```python
# 5. Registrar en event log (PARTICIONADO)
try:
    log_events = []
    for event in valid_events:
        log_events.append({
            'product_id': event['product_id'],
            'warehouse_id': event['warehouse_id'],
            'quantity': event.get('quantity', 0),
            'event_date': event.get('event_date'),
            'record_type': event.get('record_type', 'sale'),
            ...
        })
    EventLog.log_events(log_events, batch_id=batch_id)  # ← INSERT en tabla particionada
except Exception as e:
    _logger.warning("Error registrando eventos en log: %s", e)
```

### ¿Por qué se usa particionado aquí?

| Razón | Explicación |
|-------|-------------|
| **Alto volumen de INSERTs** | Cada batch puede insertar miles de registros de auditoría |
| **Consultas por rango de fechas** | Los análisis/reportes siempre filtran por fecha |
| **Limpieza eficiente** | Eliminar datos antiguos = DROP partición (instantáneo) |
| **No afecta al flujo principal** | Si falla el log, el procesamiento continúa |

### ¿Qué es el Particionado?

El particionado divide una tabla grande en partes más pequeñas llamadas **particiones**. Cada partición contiene un subconjunto de datos basado en un criterio (en este caso, por fecha).

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TABLA PADRE (VIRTUAL)                            │
│                product_sale_event_log                               │
│                PARTITION BY RANGE (event_date)                      │
└─────────────────────────────────────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│   Partición       │ │   Partición       │ │   Partición       │
│   20251225        │ │   20251226        │ │   20251227        │
│   (25 dic 2025)   │ │   (26 dic 2025)   │ │   (27 dic 2025)   │
│   ~50,000 rows    │ │   ~48,000 rows    │ │   ~52,000 rows    │
└───────────────────┘ └───────────────────┘ └───────────────────┘
```

### Ventajas del Particionado

| Ventaja | Descripción |
|---------|-------------|
| **Consultas Rápidas** | PostgreSQL solo escanea las particiones relevantes (partition pruning) |
| **Mantenimiento Simple** | Eliminar datos antiguos = DROP de la partición (instantáneo) |
| **INSERTs Eficientes** | Cada INSERT va directo a su partición sin escanear toda la tabla |
| **Backups Selectivos** | Puedes respaldar solo las particiones que necesitas |
| **Índices Pequeños** | Cada partición tiene sus propios índices más pequeños |

### Funcionamiento Automático

El sistema gestiona las particiones automáticamente:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CRON: Gestión de Particiones                     │
│                    (Ejecuta diariamente)                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. CREAR particiones futuras (próximos 7 días)                    │
│     └── Garantiza que siempre haya espacio para nuevos eventos     │
│                                                                     │
│  2. ELIMINAR particiones antiguas (> 90 días)                      │
│     └── DROP TABLE instantáneo vs DELETE row-by-row               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Estructura de Particiones

Cada partición se nombra con el patrón: `product_sale_event_log_YYYYMMDD`

```
product_sale_event_log              (tabla padre - virtual)
├── product_sale_event_log_20251220 (20 dic → 21 dic)
├── product_sale_event_log_20251221 (21 dic → 22 dic)
├── product_sale_event_log_20251222 (22 dic → 23 dic)
├── ...
├── product_sale_event_log_20251227 (27 dic → 28 dic)
└── product_sale_event_log_20251228 (28 dic → 29 dic)
```

### Consultas Optimizadas

Cuando consultas con filtro de fecha, PostgreSQL **solo escanea las particiones necesarias**:

```sql
-- Esta consulta SOLO escanea product_sale_event_log_20251226
SELECT * FROM product_sale_event_log
WHERE event_date = '2025-12-26';

-- Esta consulta escanea 3 particiones (24, 25, 26 dic)
SELECT * FROM product_sale_event_log
WHERE event_date BETWEEN '2025-12-24' AND '2025-12-26';
```

### Comandos de Administración

```python
# En shell de Odoo
EventLog = env['product.sale.event.log']

# Ver estadísticas de particiones
stats = EventLog.get_partition_stats()
for p in stats:
    print(f"{p['partition_name']}: {p['size']}")

# Crear partición para una fecha específica
EventLog._create_partition_for_date(date(2025, 12, 30))

# Eliminar particiones antiguas (> 90 días)
deleted = EventLog.cleanup_old_partitions(days=90)
print(f"Particiones eliminadas: {deleted}")

# Forzar gestión de particiones (crear futuras, eliminar antiguas)
EventLog.cron_manage_partitions()
```

### Ejemplo: Limpieza de Datos

**Sin particionado** (lento, bloquea la tabla):
```sql
-- LENTO: Escanea y elimina millones de filas una por una
DELETE FROM product_sale_event_log
WHERE event_date < '2025-09-27';
-- Tiempo: ~30 minutos para 10M filas
```

**Con particionado** (instantáneo):
```sql
-- RÁPIDO: Elimina la partición completa
DROP TABLE product_sale_event_log_20250926;
-- Tiempo: < 1 segundo
```

### Verificar Estado del Particionado

```python
# En shell de Odoo
EventLog = env['product.sale.event.log']

# ¿La tabla está particionada?
is_partitioned = EventLog._is_table_partitioned()
print(f"Particionado activo: {is_partitioned}")

# Ver todas las particiones
env.cr.execute("""
    SELECT c.relname, pg_size_pretty(pg_relation_size(c.oid))
    FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhrelid
    JOIN pg_class p ON p.oid = i.inhparent
    WHERE p.relname = 'product_sale_event_log'
    ORDER BY c.relname
""")
for name, size in env.cr.fetchall():
    print(f"{name}: {size}")
```

### Consideraciones Importantes

1. **Primera Instalación**: La tabla se crea particionada automáticamente
2. **Migración**: Si la tabla ya existe sin particionar, se convierte automáticamente
3. **Particiones Futuras**: El cron crea particiones para los próximos 7 días
4. **Retención**: Por defecto se eliminan particiones > 90 días
5. **Índices**: Se heredan automáticamente a cada nueva partición

---

## Ventajas de la Arquitectura

1. **Sin Locks**: DELETE...RETURNING es atómico
2. **Escalable**: Múltiples workers en paralelo
3. **Tolerante a fallos**: Dead letter queue
4. **Consultas O(1)**: Rolling stats precalculados
5. **Auditoría**: Log particionado por día
6. **Backpressure**: Detección automática de sobrecarga

---

## Licencia

Propietario - SOLNUSTEC SA
