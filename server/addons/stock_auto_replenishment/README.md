# Transferencias Automáticas de Reabastecimiento

## ¿Qué hace este módulo?

Genera **transferencias automáticas** cuando un producto necesita reabastecimiento, usando un sistema de **cola eficiente** que evita procesar 300k+ orderpoints cada 5 minutos.

**El problema:** Escanear todos los orderpoints en cada cron es ineficiente cuando hay cientos de miles de reglas.

**La solución:**
- Solo se encolan los orderpoints que realmente necesitan reabastecimiento
- Procesamiento batch con bloqueo optimista (FOR UPDATE SKIP LOCKED)
- Dedupe key para evitar duplicados en el mismo día
- Dos modos: Individual (1 producto = 1 transferencia) o Agrupado (estándar Odoo)
- Dashboard con estadísticas en tiempo real

---

## Flujo de Operación

```
replenishment_inventory          stock_auto_replenishment
        │                                  │
        ▼                                  │
 _update_orderpoints_batch() ──hook───►  Encola orderpoints
        │                              con trigger='auto' y
        ▼                              qty_to_order > 0
 orderpoints actualizados                  │
                                           ▼
                                    Cron cada 5 min
                                           │
                                           ▼
                                    Procesa cola batch
                                    (FOR UPDATE SKIP LOCKED)
                                           │
                                           ▼
                                    Crea transferencias
                                    (modo individual o agrupado)
```

---

## Instalación

1. Copiar la carpeta `stock_auto_replenishment` a tu directorio de addons
2. Actualizar la lista de aplicaciones en Odoo
3. Instalar el módulo

**Dependencias:**
- `interconnection_of_modules` (campos de almacén en pickings)
- `replenishment_inventory` (cálculo de orderpoints)

---

## Configuración

### 1. Activar la Funcionalidad

- Ir a **Inventario → Configuración → Ajustes**
- Buscar **"Reabastecimiento Automático"**
- Activar el módulo y seleccionar el modo:
  - **Individual:** 1 transferencia por producto (recomendado para trazabilidad)
  - **Agrupado:** Usa procurement.group estándar de Odoo

### 2. Configurar el Almacén Principal

El sistema necesita saber de dónde sacar los productos:

**Opción A (recomendado):**
- En tu bodega principal, activar **"Es Bodega Principal"**

**Opción B:**
- En cada sucursal, ir a pestaña **"Reabastecimiento Automático"**
- Seleccionar el **"Almacén Origen para Reabastecimiento"**

### 3. Configurar Reglas de Reordenamiento

En **Inventario → Configuración → Reglas de Reordenamiento**:
- Configurar producto, ubicación destino, cantidad mínima/máxima
- **Disparador: "Auto"** ← Importante

---

## Uso

### Dashboard
- Ir a **Inventario → Informes → Dashboard Reabastecimiento**
- Muestra estadísticas en tiempo real:
  - Total de transferencias (hoy, semana, mes)
  - Transferencias por estado (borrador, en espera, listo, realizado, cancelado)
  - Cola de procurements (pendiente, procesado, fallido)
  - Reglas de reordenamiento automáticas
  - **Estado de los Crons** (activo/inactivo, última ejecución, próxima ejecución)
- Click en cualquier tarjeta abre la lista filtrada

### Ver Cola de Procurements
- Ir a **Inventario → Informes → Cola de Procurements**
- Estados: Pendiente | Procesado | Fallido

### Ver Transferencias
- Ir a **Inventario → Operaciones → Transferencias**
- Filtros disponibles:
  - **Manuales** (activo por defecto) - Transferencias creadas manualmente
  - **Automáticas** - Transferencias generadas por el módulo
- Columnas: Almacén Origen, Almacén Destino, Estado, etc.

### Encolar una Transferencia Manualmente
- En la lista de reglas de reordenamiento (vista tree)
- Botón **"Encolar"** (visible cuando trigger=auto y qty_to_order > 0)
- El botón se oculta si ya existe un registro pendiente en la cola
- El botón "Ordenar una vez" se oculta cuando el modo Individual está activo

---

## Opciones

| Opción | Descripción | Default |
|--------|-------------|---------|
| Habilitado | Activa el módulo | No |
| Modo | Individual o Agrupado | Individual |
| Límite por batch | Máximo de items por ejecución | 100 |
| Verificar stock | Solo crear si hay stock disponible | Sí |
| Auto-confirmar | Confirmar y reservar automáticamente | Sí |
| Días para cancelar | Cancelar transferencias no validadas después de X días (0 = desactivado) | 5 |

---

## Modelo de Cola

El modelo `product.replenishment.procurement.queue` tiene:

| Campo | Descripción |
|-------|-------------|
| orderpoint_id | Regla de reordenamiento |
| qty_to_order_snapshot | Cantidad a ordenar al momento de encolar |
| dedupe_key | Clave única: `OP:{id}-Q:{qty}-D:{YYYYMMDD}` |
| state | pending, done, failed |
| picking_id | Transferencia creada (si aplica) |
| retry_count | Intentos de procesamiento |
| last_error | Último error (si falló) |

---

## Tareas Programadas (Crons)

| Cron | Intervalo | Descripción |
|------|-----------|-------------|
| Procesar Cola | 5 minutos | Procesa items pendientes y crea transferencias |
| Limpieza Cola | 1 día | Elimina registros procesados mayores a 7 días |

El estado de los crons se puede monitorear desde el Dashboard.

---

## FAQ

**¿Cada cuánto se ejecuta?** El procesador de cola cada 5 minutos, limpieza diaria a las 4:00 AM.

**¿Se pueden duplicar transferencias?** No. El dedupe_key evita encolar el mismo orderpoint con la misma cantidad en el mismo día.

**¿Qué pasa si falla?** El registro queda en estado "Fallido" con el error. No se reintenta automáticamente.

**¿Puedo forzar una transferencia?** Sí, con el botón "Encolar" en la lista de orderpoints.

**¿Se eliminan los registros viejos?** Sí, el cron de limpieza elimina registros procesados mayores a 7 días.

**¿Cómo sé si los crons están activos?** En el Dashboard se muestra el estado de cada cron (activo/inactivo).

**¿Dónde veo las transferencias automáticas?** En Inventario → Operaciones → Transferencias, usando el filtro "Automáticas".

**¿Qué pasa si no valido una transferencia?** Después de X días configurados (default 5), se cancela automáticamente. Esto evita transferencias obsoletas.

---

## Estructura de Módulos

```
stock (Odoo base)
    │
interconnection_of_modules
    │   └── Campos: origin_warehouse_id, dest_warehouse_id
    │   └── Vistas: Transferencias con almacenes
    │
replenishment_inventory
    │   └── Cálculo de orderpoints y qty_to_order
    │   └── Cola de eventos de ventas
    │
stock_auto_replenishment (este módulo)
        └── Cola de procurement
        └── Procesador batch
        └── Dashboard
        └── Filtros Manuales/Automáticas
```

---

**Autor:** SOLNUSTEC SA | **Versión:** 17.0.2.0.0 | **Licencia:** LGPL-3
