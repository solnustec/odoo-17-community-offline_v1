# Analisis de Rotacion de Productos - Odoo 17

Sistema de alto rendimiento para identificar productos con stock que han dejado de rotar en las bodegas.

---

## Tabla de Contenidos

1. [Descripcion General](#descripcion-general)
2. [Valor Centinela 9999 (Nunca)](#valor-centinela-9999-nunca)
3. [Fuentes de Datos](#fuentes-de-datos)
4. [Arquitectura del Sistema](#arquitectura-del-sistema)
5. [Estructura de la Tabla](#estructura-de-la-tabla)
6. [Proceso del Cron Diario](#proceso-del-cron-diario)
7. [Proceso del Cron Semanal](#proceso-del-cron-semanal)
8. [Indices PostgreSQL](#indices-postgresql)
9. [Vistas Disponibles](#vistas-disponibles)
10. [Instalacion y Uso](#instalacion-y-uso)
11. [Sistema de Notificaciones (Actividades)](#sistema-de-notificaciones-actividades)
12. [Redistribucion de Productos](#redistribucion-de-productos)
13. [Riesgos y Limitaciones](#riesgos-y-limitaciones)

---

## Descripcion General

### Problema que Resuelve

Detectar productos que:
- **Tienen stock en bodega pero no se venden**
- **No tienen transferencias** (entradas/salidas)
- **Llevan muchos dias sin ningun movimiento**
- **NUNCA han tenido actividad** (caso mas critico)

### Escala Soportada

| Metrica | Capacidad |
|---------|-----------|
| Productos | 15,000+ |
| Bodegas | 200-300 |
| Tiempo de ejecucion | < 60 segundos |
| Tamanio de tabla | 20,000 - 35,000 filas |

---

## Valor Centinela 9999 (Nunca)

### Semantica del Valor 9999

Cuando un producto **NUNCA** ha tenido cierta actividad, usamos el valor `9999`:

| Campo | Valor 9999 Significa |
|-------|----------------------|
| `days_without_sale = 9999` | El producto **NUNCA** se ha vendido |
| `days_without_transfer = 9999` | El producto **NUNCA** se ha transferido |
| `days_without_rotation = 9999` | El producto **NUNCA** ha tenido ningun movimiento |

**Importante**: El valor `0` significa que el producto tuvo actividad **HOY** (maxima rotacion).

### Por Que Usamos 9999?

```sql
-- Con 9999 como centinela:
-- 1. El valor 0 = actividad hoy (maxima rotacion)
-- 2. ORDER BY days DESC pone los "nunca" (9999) primero (mas criticos)
-- 3. Filtros simples y claros

SELECT * FROM product_rotation_daily WHERE days_without_sale = 9999;  -- Nunca vendidos
```

### Logica de los Flags Booleanos

Los flags se activan cuando:
- El producto **NUNCA** tuvo esa actividad (dias = 9999), **O**
- Han pasado **30+ dias** desde la ultima actividad

```sql
flag_no_sales = (days_without_sale = 9999 OR days_without_sale >= 30)
flag_no_transfers = (days_without_transfer = 9999 OR days_without_transfer >= 30)
flag_no_rotation = (days_without_rotation = 9999 OR days_without_rotation >= 30)
```

### Ejemplos de Consultas

```sql
-- Productos que NUNCA se han vendido (caso mas critico)
SELECT * FROM product_rotation_daily WHERE days_without_sale = 9999;

-- Productos sin venta en 30+ dias (INCLUYE los que nunca se vendieron)
SELECT * FROM product_rotation_daily
WHERE days_without_sale = 9999 OR days_without_sale >= 30;
-- Equivalente a: WHERE flag_no_sales = TRUE

-- Productos sin venta en 30+ dias (EXCLUYE los que nunca se vendieron)
SELECT * FROM product_rotation_daily
WHERE days_without_sale >= 30 AND days_without_sale != 9999;

-- Ordenar por criticidad (9999 = nunca, aparece primero con ORDER BY DESC)
SELECT * FROM product_rotation_daily
ORDER BY days_without_rotation DESC;
```

### Tabla de Interpretacion

| days_without_sale | days_without_transfer | days_without_rotation | Interpretacion |
|-------------------|----------------------|----------------------|----------------|
| 9999 | 9999 | 9999 | **NUNCA** ha tenido ningun movimiento |
| 9999 | 15 | 15 | Se recibio hace 15 dias, **NUNCA** se ha vendido |
| 30 | 30 | 30 | Sin actividad en 30 dias |
| 5 | 9999 | 5 | Se vendio hace 5 dias, **NUNCA** tuvo transferencia |
| 60 | 10 | 10 | Ultima venta hace 60 dias, transferencia hace 10 |
| 0 | 0 | 0 | Actividad **HOY** (maxima rotacion) |

---

## Fuentes de Datos

### Ventas: `product_warehouse_sale_summary`

Las ventas se obtienen de la tabla pre-agregada (modulo `sales_report`):

```
product_warehouse_sale_summary
├── date           --> Fecha de la venta
├── product_id     --> Producto vendido
├── warehouse_id   --> Bodega donde se vendio
├── quantity_sold  --> Cantidad vendida
└── amount_total   --> Monto total
```

**Ventaja**: Tabla pre-agregada = consultas rapidas sin recorrer millones de movimientos.

### Transferencias: `stock.move`

Las transferencias se obtienen de `stock.move` (no hay tabla pre-agregada):

```sql
-- Tipos de movimientos considerados como "transferencia"
WHERE sm.state = 'done' AND (
    -- Transferencia interna entre ubicaciones
    (sl_src.usage = 'internal' AND sl_dest.usage = 'internal')
    -- Recepcion de proveedor
    OR (sl_src.usage = 'supplier' AND sl_dest.usage = 'internal')
    -- Devolucion de cliente
    OR (sl_src.usage = 'customer' AND sl_dest.usage = 'internal')
    -- Ajuste de inventario (entrada o salida)
    OR (sl_src.usage = 'inventory' AND sl_dest.usage = 'internal')
    OR (sl_src.usage = 'internal' AND sl_dest.usage = 'inventory')
)
```

### Stock: `stock.quant`

El stock actual se obtiene de `stock.quant`:

```sql
SELECT product_id, warehouse_id, SUM(quantity) as stock_on_hand
FROM stock_quant sq
JOIN stock_location sl ON sq.location_id = sl.id
JOIN stock_warehouse sw ON sl.warehouse_id = sw.id
WHERE sl.usage = 'internal' AND sq.quantity > 0
GROUP BY product_id, warehouse_id
```

---

## Arquitectura del Sistema

### Diagrama de Flujo

```
┌─────────────────────────────────┐
│ product_warehouse_sale_summary  │  <-- Ventas (pre-agregada)
└─────────────────────────────────┘
              │
              v
┌─────────────────────────────────┐     ┌──────────────────────────┐
│         CRON DIARIO             │ --> │ product_rotation_daily   │
│    (3:00 AM, incremental)       │     │   (snapshot unico)       │
└─────────────────────────────────┘     └──────────────────────────┘
              ^
              │
┌─────────────────────────────────┐
│          stock.move             │  <-- Transferencias
└─────────────────────────────────┘
              ^
              │
┌─────────────────────────────────┐
│          stock.quant            │  <-- Stock actual
└─────────────────────────────────┘
```

### Principios de Diseno

| Principio | Descripcion |
|-----------|-------------|
| **Sin historicos** | La tabla solo guarda el estado actual |
| **Incremental** | Nunca recalcula todo, solo actualiza lo necesario |
| **Sin triggers** | Toda la logica esta en el cron de Odoo |
| **Operaciones masivas** | SQL bulk con CTEs, sin loops ORM |
| **Indices optimizados** | Consultas rapidas sin full table scans |
| **Compania unica** | Procesa solo la compania principal |

---

## Estructura de la Tabla

### Tabla: `product_rotation_daily`

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `product_id` | Many2one | Producto analizado |
| `warehouse_id` | Many2one | Bodega donde esta el stock |
| `company_id` | Many2one | Compania principal |
| `stock_on_hand` | Float | Cantidad actual en stock |
| `last_sale_date` | Date | Fecha de ultima venta (NULL si nunca) |
| `last_transfer_date` | Date | Fecha de ultima transferencia (NULL si nunca) |
| `last_rotation_date` | Date | Fecha de ultimo movimiento (NULL si nunca) |
| `days_without_sale` | Integer | Dias sin venta (**9999 = NUNCA**, **0 = hoy**) |
| `days_without_transfer` | Integer | Dias sin transferencia (**9999 = NUNCA**, **0 = hoy**) |
| `days_without_rotation` | Integer | Dias sin movimiento (**9999 = NUNCA**, **0 = hoy**) |
| `flag_no_sales` | Boolean | TRUE si dias=9999 O dias>=30 |
| `flag_no_transfers` | Boolean | TRUE si dias=9999 O dias>=30 |
| `flag_no_rotation` | Boolean | TRUE si dias=9999 O dias>=30 |
| `updated_at` | Datetime | Ultima actualizacion por el cron |

### Restriccion Unica

```sql
UNIQUE(product_id, warehouse_id)
```

Solo puede existir **un registro por producto y bodega**.

---

## Proceso del Cron Diario

### Configuracion

- **Nombre**: "Rotacion de Productos: Actualizacion Diaria"
- **Frecuencia**: Diaria
- **Hora**: 3:00 AM
- **Metodo**: `_cron_update_rotation_daily()`

### Flujo del Proceso

```
INICIO
    │
    v
[1] Obtener compania principal (ID mas bajo)
    │
    v
[2] Eliminar registros de productos sin stock
    │   DELETE FROM product_rotation_daily
    │   WHERE producto ya no tiene stock > 0
    │
    v
[3] Ejecutar consulta SQL con CTEs
    │
    ├──> CTE 1: current_stock
    │    - Productos con stock > 0 por bodega
    │    - Fuente: stock.quant + stock.warehouse
    │
    ├──> CTE 2: last_sales
    │    - Ultima fecha de venta por producto/bodega
    │    - Fuente: product_warehouse_sale_summary
    │
    ├──> CTE 3: last_transfers
    │    - Ultima fecha de transferencia por producto/bodega
    │    - Fuente: stock.move (solo state='done')
    │
    ├──> CTE 4: rotation_data
    │    - Combina todo y calcula dias
    │    - Si fecha IS NULL -> dias = 9999 (NUNCA)
    │    - Si fecha existe -> dias = HOY - fecha (0 = hoy)
    │
    └──> CTE 5: final_data
         - Calcula flags booleanos
         - dias=9999 OR dias>=30 -> flag=TRUE
    │
    v
[4] UPSERT (INSERT ... ON CONFLICT UPDATE)
    │   - Inserta productos nuevos
    │   - Actualiza productos existentes
    │
    v
[5] Commit y log de resultados
    │
    v
FIN
```

### Calculo de `days_without_rotation`

```sql
-- Logica especial para calcular dias sin rotacion
CASE
    -- Si ambos son 9999 (nunca), el resultado es 9999
    WHEN days_without_sale = 9999 AND days_without_transfer = 9999 THEN 9999
    -- Si solo ventas es 9999, usar transferencias
    WHEN days_without_sale = 9999 THEN days_without_transfer
    -- Si solo transferencias es 9999, usar ventas
    WHEN days_without_transfer = 9999 THEN days_without_sale
    -- Si ambos tienen valor real, usar el minimo
    ELSE LEAST(days_without_sale, days_without_transfer)
END AS days_without_rotation
```

### Comportamiento con Registros Existentes

El cron **NO borra ni recrea** todos los registros. Usa un patron incremental:

| Situacion | Accion | Explicacion |
|-----------|--------|-------------|
| Producto **nuevo** con stock | **INSERT** | Se crea registro nuevo |
| Producto **existente** con stock | **UPDATE** | Se actualizan dias, fechas y flags |
| Producto **existente** sin stock | **DELETE** | Se elimina (ya no tiene inventario) |

```sql
-- Paso 1: Eliminar productos que perdieron todo su stock
DELETE FROM product_rotation_daily
WHERE NOT EXISTS (SELECT 1 FROM stock_quant WHERE quantity > 0 ...);

-- Paso 2: UPSERT - Insert o Update segun exista
INSERT INTO product_rotation_daily (...)
SELECT ... FROM (datos calculados)
ON CONFLICT (product_id, warehouse_id) DO UPDATE SET
    days_without_sale = EXCLUDED.days_without_sale,
    days_without_transfer = EXCLUDED.days_without_transfer,
    ...
```

**Beneficios del enfoque incremental:**
- No hay downtime (la tabla siempre tiene datos)
- Menor uso de recursos (solo toca registros afectados)
- Preserva IDs de registros (util para referencias externas)

---

## Proceso del Cron Semanal

### Configuracion

- **Nombre**: "Rotacion de Productos: Limpieza Semanal"
- **Frecuencia**: Semanal (Domingos)
- **Hora**: 4:00 AM
- **Metodo**: `_cron_weekly_cleanup()`

### Acciones

```sql
-- 1. Eliminar registros de productos inactivos/eliminados
DELETE FROM product_rotation_daily prd
WHERE NOT EXISTS (
    SELECT 1 FROM product_product pp
    WHERE pp.id = prd.product_id AND pp.active = TRUE
);

-- 2. Eliminar registros de bodegas inactivas/eliminadas
DELETE FROM product_rotation_daily prd
WHERE NOT EXISTS (
    SELECT 1 FROM stock_warehouse sw
    WHERE sw.id = prd.warehouse_id AND sw.active = TRUE
);

-- 3. Optimizar tabla para el planificador de consultas
ANALYZE product_rotation_daily;
```

---

## Indices PostgreSQL

### Indices Creados Automaticamente

```sql
-- 1. Filtrado por flags (uso mas comun)
CREATE INDEX idx_rotation_flags_composite
ON product_rotation_daily (company_id, flag_no_rotation, flag_no_sales, flag_no_transfers)
WHERE flag_no_rotation = TRUE OR flag_no_sales = TRUE OR flag_no_transfers = TRUE;

-- 2. Productos con stock (filtro muy frecuente)
CREATE INDEX idx_rotation_with_stock
ON product_rotation_daily (company_id, warehouse_id)
WHERE stock_on_hand > 0;

-- 3. Ordenamiento por dias sin rotacion
CREATE INDEX idx_rotation_warehouse_days
ON product_rotation_daily (warehouse_id, days_without_rotation DESC);

-- 4. Productos que NUNCA han tenido actividad
CREATE INDEX idx_rotation_never
ON product_rotation_daily (company_id, warehouse_id)
WHERE days_without_rotation = 9999;

-- 5. Monitoreo de actualizaciones del cron
CREATE INDEX idx_rotation_updated
ON product_rotation_daily (updated_at DESC);
```

---

## Vistas Disponibles

### Vista de Lista (Tree)

**Colores por Estado**:
| Color | Condicion | Significado |
|-------|-----------|-------------|
| **Rojo** | `flag_no_rotation = TRUE` | Sin rotacion (critico) |
| **Amarillo** | `flag_no_sales = TRUE` | Sin ventas |
| **Azul** | `flag_no_transfers = TRUE` | Sin transferencias |
| **Normal** | Ninguna flag activa | Producto activo |

### Vista Kanban

- Agrupado por bodega
- Tarjetas con color segun estado
- Muestra **"Nunca"** cuando `days = 9999`
- Badges: "Sin Rotacion", "Sin Ventas", "Sin Transf.", "Activo"

### Filtros de Busqueda

| Filtro | Dominio | Descripcion |
|--------|---------|-------------|
| Sin Rotacion | `flag_no_rotation = TRUE` | Productos sin rotacion o nunca movidos |
| Sin Ventas | `flag_no_sales = TRUE` | Productos sin ventas o nunca vendidos |
| Nunca Vendido | `days_without_sale = 9999` | Productos que **NUNCA** se vendieron |
| Nunca Movido | `days_without_rotation = 9999` | Productos que **NUNCA** tuvieron movimiento |
| 30+ Dias | `days >= 30 AND days != 9999` | Excluye "nunca" |
| Criticos | `flag_no_rotation AND stock > 0` | Stock + Sin rotacion |

### Menu de Acceso

```
Inventario
    └── Analisis de Rotacion
            ├── Rotacion de Productos  (vista principal)
            ├── Sin Rotacion           (productos sin rotacion)
            └── Productos Criticos     (stock + sin rotacion)
```

---

## Instalacion y Uso

### Dependencias

- `base`
- `mail` (para actividades)
- `stock`
- `sale_stock`
- `sales_report` (para `product_warehouse_sale_summary`)

### Primera Ejecucion

```python
# Desde el shell de Odoo
self.env['product.rotation.daily']._cron_update_rotation_daily()
self.env.cr.commit()
```

### Recalculo Completo (Solo si es necesario)

```python
# ADVERTENCIA: Trunca la tabla y recalcula todo
self.env['product.rotation.daily'].action_force_full_recalculation()
```

---

## Sistema de Notificaciones (Actividades)

### Descripcion

El modulo crea **actividades de Odoo** (`mail.activity`) para notificar a los revisores cuando hay productos criticos sin rotacion.

### Grupo de Revisores

Se crea el grupo **"Revisor de Rotacion"** en:
```
Configuracion > Usuarios > Grupos > Rotacion de Productos
```

| Grupo | Descripcion |
|-------|-------------|
| **Revisor de Rotacion** | Recibe actividades diarias sobre productos sin rotacion |
| **Administrador de Rotacion** | Acceso completo + configuracion del modulo |

### Flujo de Actividades

```
┌─────────────────────────────────────────────────────────────┐
│                    CRON DIARIO (3:00 AM)                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
                   ┌──────────────────────┐
                   │ Hay productos        │
                   │ criticos?            │
                   │ (sin rotacion+stock) │
                   └──────────────────────┘
                      │              │
                     SI             NO
                      │              │
                      v              v
         ┌────────────────────┐    (fin)
         │ Obtener usuarios   │
         │ del grupo revisor  │
         └────────────────────┘
                      │
                      v
         ┌────────────────────┐
         │ Crear/actualizar   │
         │ actividad para     │
         │ cada revisor       │
         └────────────────────┘
                      │
                      v
         ┌────────────────────┐
         │ Actividad aparece  │
         │ en bandeja del     │
         │ usuario            │
         └────────────────────┘
```

### Contenido de la Actividad

Se crea **UNA actividad por revisor** con la lista de los 15 productos mas criticos:

- **Resumen**: "Revisar X productos sin rotacion"
- **Nota**: Tabla con los 15 productos mas criticos:

```
┌───┬───────┬────────────────────┬─────────┬─────────┬───────┐
│ # │ Dias  │ Producto           │ Ref     │ Bodega  │ Stock │
├───┼───────┼────────────────────┼─────────┼─────────┼───────┤
│ 1 │ NUNCA │ Tornillo M8x20     │ TOR-M8  │ Central │   150 │
│ 2 │ NUNCA │ Arandela 10mm      │ ARA-10  │ Norte   │    80 │
│ 3 │ 120d  │ Cable HDMI 2m      │ CAB-HD  │ Central │    25 │
│ 4 │ 95d   │ Adaptador USB-C    │ ADP-USC │ Sur     │    12 │
│ ...                                                        │
└───┴───────┴────────────────────┴─────────┴─────────┴───────┘
... y X productos mas
```

- **Fecha limite**: Hoy (revision urgente)
- **Tipo**: "Revision de Rotacion" (icono de cajas)

### Configurar Usuarios Revisores

1. Ir a **Configuracion > Usuarios y Companias > Usuarios**
2. Seleccionar el usuario
3. En la pestania **"Acceso"**, buscar **"Rotacion de Productos"**
4. Activar **"Revisor de Rotacion"**

El usuario comenzara a recibir actividades en su bandeja cuando el cron detecte productos criticos.

---

## Redistribucion de Productos

### Descripcion

Cuando un producto tiene stock pero no tiene rotacion (`flag_no_rotation = TRUE`), el sistema sugiere **bodegas donde redistribuir** el producto para que pueda venderse.

### Logica de Sugerencia de Bodegas

El sistema busca bodegas donde el **mismo producto SI tiene rotacion activa** y las ordena por **volumen de ventas**:

```
┌────────────────────────────────────────────────────────────────┐
│                   CALCULO DE BODEGAS SUGERIDAS                  │
├────────────────────────────────────────────────────────────────┤
│  1. Buscar otras bodegas donde el producto:                     │
│     - flag_no_rotation = FALSE (tiene rotacion activa)          │
│     - stock_on_hand > 0 (hay stock disponible)                  │
│                                                                 │
│  2. Obtener ventas de los ultimos 30 dias para cada bodega:     │
│     - Fuente primaria: product.sales.stats (O(1) si existe)     │
│     - Fallback: product_warehouse_sale_summary                  │
│                                                                 │
│  3. Ordenar por volumen de ventas (DESC), luego por rotacion:   │
│     - Mayor ventas_30d = prioridad mas alta                     │
│     - En caso de empate, menor days_without_rotation            │
│                                                                 │
│  4. Limitar a 5 bodegas sugeridas                               │
│                                                                 │
│  5. Si no hay bodegas con rotacion activa:                      │
│     - Fallback a "Bodega Matilde" (bodega central por defecto)  │
│     - Tambien se obtienen ventas y stock para esta bodega       │
└────────────────────────────────────────────────────────────────┘
```

### Fuente de Datos de Ventas

El metodo `_get_sales_last_30_days()` obtiene las ventas de los ultimos 30 dias:

```python
# Prioridad 1: product.sales.stats (modelo precalculado, O(1))
stat = SalesStats.search([
    ('product_id', '=', product_id),
    ('warehouse_id', '=', warehouse_id),
    ('period_days', '=', 30),
])
if stat:
    return stat.mean_qty * 30  # Media diaria * dias

# Prioridad 2: product_warehouse_sale_summary (fallback)
SELECT SUM(quantity_sold)
FROM product_warehouse_sale_summary
WHERE product_id = %s AND warehouse_id = %s AND date >= (TODAY - 30)
```

### Calculo Perezoso (Lazy Calculation)

Las bodegas sugeridas **NO se calculan durante el cron**. Solo se calculan cuando el usuario abre el formulario de un producto sin rotacion.

**Razon**: Calcular sugerencias para 35,000 registros seria costoso e innecesario. Solo se necesitan cuando el usuario va a tomar accion.

```python
# El campo es computed, se ejecuta solo al acceder al formulario
suggested_warehouse_ids = fields.Many2many(
    'stock.warehouse',
    compute='_compute_suggested_warehouses',  # Lazy calculation
)
```

### Vista del Formulario

Cuando un producto tiene `flag_no_rotation = TRUE`:

```
┌──────────────────────────────────────────────────────────────────────┐
│  [Transferir Producto]                                               │ ← Boton en header
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  REDISTRIBUCION SUGERIDA                                             │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │ Bodegas con Rotacion Activa: [Central] [Norte] [Sur]             ││ ← Tags
│  │                                                                  ││
│  │ ┌──────────────────────────────────────────────────────────────┐ ││
│  │ │ BODEGA      │ STOCK │ VENTAS 30D │ ROTACION │ ACCION         │ ││
│  │ ├─────────────┼───────┼────────────┼──────────┼────────────────┤ ││
│  │ │ Central     │   150 │    320     │ 2d       │ [→ Transferir] │ ││
│  │ │ Norte       │    80 │    185     │ 5d       │ [→ Transferir] │ ││
│  │ │ Sur         │    25 │     45     │ 12d      │ [→ Transferir] │ ││
│  │ └─────────────┴───────┴────────────┴──────────┴────────────────┘ ││
│  │                                                                  ││
│  │ Las bodegas se ordenan por volumen de ventas (30 dias),          ││
│  │ priorizando las de mayor demanda.                                ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Nota**: La columna "Ventas 30d" muestra el volumen de ventas del producto en esa bodega durante los ultimos 30 dias. Las bodegas con mayor volumen de ventas aparecen primero.

### Wizard de Transferencia

Al hacer clic en "Transferir Producto" se abre un wizard:

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRANSFERIR PRODUCTO                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PRODUCTO                         ORIGEN                        │
│  ┌────────────────────┐          ┌────────────────────┐        │
│  │ Cable HDMI 2m      │          │ Bodega Norte       │        │
│  │ Stock: 50 unidades │          │                    │        │
│  └────────────────────┘          └────────────────────┘        │
│                                                                 │
│  DESTINO Y CANTIDAD                                             │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ Bodega Destino: [Central ▼]                                ││
│  │ Sugeridas: [Central] [Sur] [Matilde]                       ││
│  │                                                            ││
│  │ [✓] Transferir Todo                                        ││
│  │ Cantidad: 50.00                                            ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  NOTAS                                                          │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ (Notas adicionales para la transferencia...)               ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  [Crear Transferencia]                             [Cancelar]   │
└─────────────────────────────────────────────────────────────────┘
```

### Flujo Completo de Transferencia

```
Usuario abre formulario de producto sin rotacion
                │
                v
    ┌───────────────────────┐
    │ Se calculan bodegas   │  ← Lazy calculation
    │ sugeridas (max 5)     │
    └───────────────────────┘
                │
                v
    ┌───────────────────────┐
    │ Click en "Transferir  │
    │ Producto"             │
    └───────────────────────┘
                │
                v
    ┌───────────────────────┐
    │ Se abre wizard con:   │
    │ - Producto readonly   │
    │ - Bodega origen       │
    │ - Stock disponible    │
    │ - Bodegas sugeridas   │
    └───────────────────────┘
                │
                v
    ┌───────────────────────┐
    │ Usuario selecciona:   │
    │ - Bodega destino      │
    │ - Cantidad            │
    └───────────────────────┘
                │
                v
    ┌───────────────────────┐
    │ Click "Crear          │
    │ Transferencia"        │
    └───────────────────────┘
                │
                v
    ┌───────────────────────┐
    │ Sistema crea:         │
    │ - stock.picking       │
    │ - stock.move          │
    │ (estado: borrador)    │
    └───────────────────────┘
                │
                v
    ┌───────────────────────┐
    │ Se abre el picking    │
    │ para confirmar        │
    └───────────────────────┘
```

### Indice Adicional para Bodegas Sugeridas

```sql
-- Indice para buscar productos con rotacion activa (usado en sugerencias)
CREATE INDEX IF NOT EXISTS idx_rotation_active_products
ON product_rotation_daily (product_id, warehouse_id)
WHERE flag_no_rotation = FALSE AND stock_on_hand > 0;
```

---

## Riesgos y Limitaciones

### Casos Limite a Considerar

| Caso | Comportamiento | Recomendacion |
|------|----------------|---------------|
| **Productos tipo Kit/Paquete** | No se detectan ventas directas del kit, solo de componentes | Documentar y excluir si es necesario |
| **Movimientos cancelados** | Se ignoran (`state != 'done'`) | Correcto, no afecta |
| **Devoluciones de cliente** | Se cuentan como transferencia, no como venta | Es el comportamiento esperado |
| **Stock negativo** | Se ignora (`quantity > 0`) | Productos con stock negativo no aparecen |
| **Ubicaciones especiales** | Solo `usage = 'internal'` | Ubicaciones virtuales se ignoran |

### Limitaciones Conocidas

1. **Stock Real vs Disponible**
   - El sistema usa `stock.quant.quantity` (stock real)
   - No considera reservas ni stock disponible
   - Productos reservados pero no despachados aparecen con stock

2. **Multi-Compania**
   - Solo procesa la compania principal (ID mas bajo)
   - Si tienes multiples companias con bodegas separadas, revisar configuracion

3. **Productos sin Stock**
   - Se eliminan de la tabla cuando `quantity <= 0`
   - No hay historico de productos que tuvieron stock y ya no tienen

4. **Ventas desde `product_warehouse_sale_summary`**
   - Depende de que esta tabla este actualizada
   - Si el modulo `sales_report` falla, las ventas no se detectan

### Restricciones SQL que Podrian Faltar

```sql
-- Considerar agregar si hay problemas de integridad:
ALTER TABLE product_rotation_daily
ADD CONSTRAINT fk_product FOREIGN KEY (product_id)
    REFERENCES product_product(id) ON DELETE CASCADE;

ALTER TABLE product_rotation_daily
ADD CONSTRAINT fk_warehouse FOREIGN KEY (warehouse_id)
    REFERENCES stock_warehouse(id) ON DELETE CASCADE;

-- Restriccion CHECK para valores validos
ALTER TABLE product_rotation_daily
ADD CONSTRAINT chk_days_positive
    CHECK (days_without_sale >= 0 AND days_without_transfer >= 0 AND days_without_rotation >= 0);
```

### Indices Adicionales Recomendados

Si experimentas lentitud en consultas especificas:

```sql
-- Para filtrar por producto especifico
CREATE INDEX idx_rotation_product
ON product_rotation_daily (product_id);

-- Para reportes que ordenan por stock
CREATE INDEX idx_rotation_stock
ON product_rotation_daily (stock_on_hand DESC)
WHERE stock_on_hand > 0;
```

### Monitoreo Recomendado

```sql
-- Verificar que el cron se ejecuto hoy
SELECT COUNT(*), MAX(updated_at), MIN(updated_at)
FROM product_rotation_daily
WHERE updated_at >= CURRENT_DATE;

-- Verificar distribucion de estados
SELECT
    flag_no_rotation,
    flag_no_sales,
    flag_no_transfers,
    COUNT(*) as total
FROM product_rotation_daily
GROUP BY flag_no_rotation, flag_no_sales, flag_no_transfers;

-- Productos que NUNCA han rotado (los mas criticos)
SELECT COUNT(*)
FROM product_rotation_daily
WHERE days_without_rotation = 9999;
```

---

## Resumen Tecnico

```
┌──────────────────────────────────────────────────────────────────┐
│                      VALOR CENTINELA 9999                        │
├──────────────────────────────────────────────────────────────────┤
│  9999 = "NUNCA" (el producto nunca tuvo esa actividad)           │
│  0 = Actividad HOY (maxima rotacion)                             │
│  > 0 = Dias reales desde la ultima actividad                     │
│                                                                  │
│  Usado en: days_without_sale, days_without_transfer,             │
│            days_without_rotation                                 │
├──────────────────────────────────────────────────────────────────┤
│                      FLAGS BOOLEANOS                             │
├──────────────────────────────────────────────────────────────────┤
│  flag_no_sales     = TRUE si dias=9999 (nunca) O dias>=30        │
│  flag_no_transfers = TRUE si dias=9999 (nunca) O dias>=30        │
│  flag_no_rotation  = TRUE si dias=9999 (nunca) O dias>=30        │
├──────────────────────────────────────────────────────────────────┤
│                      FUENTES DE DATOS                            │
├──────────────────────────────────────────────────────────────────┤
│  VENTAS:         product_warehouse_sale_summary (pre-agregada)   │
│  TRANSFERENCIAS: stock.move (state='done')                       │
│  STOCK:          stock.quant (quantity > 0)                      │
├──────────────────────────────────────────────────────────────────┤
│                      CRONS                                       │
├──────────────────────────────────────────────────────────────────┤
│  Diario (3:00 AM): Actualizacion incremental                     │
│  Semanal (Dom 4:00 AM): Limpieza de registros huerfanos          │
└──────────────────────────────────────────────────────────────────┘
```
