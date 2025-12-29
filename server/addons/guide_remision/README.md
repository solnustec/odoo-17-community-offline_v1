# Guide Remision - APIs de Transferencias

Este módulo proporciona APIs REST para la gestión de transferencias de stock entre sucursales.

## Modelos

### `json.pos.transfers`
Almacena las transferencias **completadas** (validadas con `button_validate`).

### `json.pos.transfers.edits`
Almacena los **borradores** de transferencias (creadas pero aún no validadas).

---

## APIs Disponibles

### 1. Obtener Borradores de Transferencias

**Endpoint:** `GET /api/tranferstobranch/<external_id>`

**Descripción:** Obtiene todos los borradores de transferencias no sincronizados para una bodega específica.

**Parámetros:**
- `external_id` (int): ID externo de la bodega origen

**Ejemplo de solicitud:**
```bash
curl -X GET "http://localhost:8069/api/tranferstobranch/123"
```

**Respuesta exitosa (200):**
```json
{
    "data": [
        {
            "id": 1,
            "json_data": {
                "transfer": {
                    "llave": "",
                    "iduser": "EMP001",
                    "idbodfrom": "123",
                    "idbodto": "456",
                    "serie": "001",
                    "secuencia": 0,
                    "tipo": 1,
                    "l_close": 0,
                    "l_recibido": 0,
                    "l_sync": 0,
                    "l_file": 0,
                    "l_void": 0,
                    "t_init": "2025-12-15",
                    "t_close": "",
                    "t_recibido": "",
                    "t_sync": "",
                    "t_void": null,
                    "t_file": null,
                    "l_sel": 0,
                    "total": "",
                    "nota": "Transferencia de prueba",
                    "responsable": "usuario@empresa.com",
                    "cdet": {
                        "fields": ["orden", "iditem", "cantidad", "precio", "idlote"],
                        "data": [
                            ["10", "PROD001", 5.0, 10.50, 0.0],
                            ["10", "PROD002", 3.0, 25.00, 0.0]
                        ]
                    },
                    "express": "0"
                },
                "transfer_products": [
                    {
                        "llave": 1,
                        "orden": "10",
                        "iditem": "PROD001",
                        "cantidad": 5.0,
                        "precio": 10.50,
                        "idlote": 0,
                        "disponible": 0,
                        "recibido": 0
                    },
                    {
                        "llave": 2,
                        "orden": "10",
                        "iditem": "PROD002",
                        "cantidad": 3.0,
                        "precio": 25.00,
                        "idlote": 0,
                        "disponible": 0,
                        "recibido": 0
                    }
                ]
            },
            "point_of_sale_series": "001",
            "sent": false,
            "db_key": "",
            "sync_date": null
        }
    ]
}
```

---

### 2. Sincronizar Borrador por ID

**Endpoint:** `PUT /api/transferstobranch_sync/<id>`

**Descripción:** Marca un borrador como sincronizado por su ID de Odoo. Actualiza `sent`, `sync_date` y `db_key`.

**Parámetros:**
- `id` (int): ID del registro en Odoo

**Body (JSON):**
```json
{
    "llave": "ABC123"
}
```

**Ejemplo de solicitud:**
```bash
curl -X PUT "http://localhost:8069/api/transferstobranch_sync/1" \
  -H "Content-Type: application/json" \
  -d '{"llave": "ABC123"}'
```

**Respuesta exitosa (200):**
```json
{
    "success": true,
    "message": "El campo 'json_data' se actualizó correctamente.",
    "updated_record_id": 1
}
```

**Respuesta error (404):**
```json
{
    "error": "No se encontró un registro asociado al POS ID 1."
}
```

---

### 3. Obtener Transferencias Completadas

**Endpoint:** `GET /api/transfers_done/<external_id>`

**Descripción:** Obtiene todas las transferencias completadas (validadas) no sincronizadas para una bodega específica.

**Parámetros:**
- `external_id` (int): ID externo de la bodega origen

**Ejemplo de solicitud:**
```bash
curl -X GET "http://localhost:8069/api/transfers_done/123"
```

**Respuesta exitosa (200):**
```json
{
    "data": [
        {
            "id": 1,
            "json_data": {
                "transfer": {
                    "llave": "ABC123",
                    "iduser": "EMP001",
                    "idbodfrom": "123",
                    "idbodto": "456",
                    "serie": "001",
                    "secuencia": 0,
                    "tipo": 1,
                    "l_close": 0,
                    "l_recibido": 0,
                    "l_sync": 0,
                    "l_file": 0,
                    "l_void": 0,
                    "t_init": "2025-12-15",
                    "t_close": "",
                    "t_recibido": "",
                    "t_sync": "",
                    "t_void": null,
                    "t_file": null,
                    "l_sel": 0,
                    "total": "",
                    "nota": "Transferencia completada",
                    "responsable": "usuario@empresa.com",
                    "cdet": {
                        "fields": ["orden", "iditem", "cantidad", "precio", "idlote"],
                        "data": [
                            ["10", "PROD001", 5.0, 10.50, 0.0]
                        ]
                    },
                    "express": "0"
                },
                "transfer_products": [
                    {
                        "llave": 1,
                        "orden": "10",
                        "iditem": "PROD001",
                        "cantidad": 5.0,
                        "precio": 10.50,
                        "idlote": 0,
                        "disponible": 0,
                        "recibido": 0
                    }
                ]
            },
            "point_of_sale_series": "001",
            "stock_picking_id": 45,
            "sent": false,
            "db_key": "ABC123",
            "employee": "Juan Pérez",
            "origin": "Bodega Central",
            "destin": "Sucursal Norte",
            "sync_date": null,
            "create_date": "2025-12-15T10:30:00"
        }
    ]
}
```

---

### 4. Sincronizar Transferencia Completada por db_key

**Endpoint:** `PUT /api/transfers_done_sync/<db_key>`

**Descripción:** Marca una transferencia completada como sincronizada buscando por su `db_key`.

**Parámetros:**
- `db_key` (string): Llave única de la transferencia en el sistema externo

**Body (JSON):**
```json
{
    "llave": "ABC123"
}
```

**Ejemplo de solicitud:**
```bash
curl -X PUT "http://localhost:8069/api/transfers_done_sync/ABC123" \
  -H "Content-Type: application/json" \
  -d '{"llave": "ABC123"}'
```

**Respuesta exitosa (200):**
```json
{
    "success": true,
    "message": "El borrador se sincronizó correctamente.",
    "updated_record_id": 1,
    "db_key": "ABC123"
}
```

**Respuesta error (404):**
```json
{
    "error": "No se encontró un registro con db_key: ABC123"
}
```

---

## Flujo de Sincronización

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. CREAR PICKING (Borrador)                                        │
│     └── Se crea registro en json.pos.transfers.edits               │
│         └── db_key = "" (vacío)                                    │
│         └── sent = false                                           │
├─────────────────────────────────────────────────────────────────────┤
│  2. SISTEMA EXTERNO consulta borradores                            │
│     └── GET /api/tranferstobranch/<external_id>                    │
│     └── Recibe lista de borradores no sincronizados                │
├─────────────────────────────────────────────────────────────────────┤
│  3. SISTEMA EXTERNO procesa y asigna llave                         │
│     └── PUT /api/transferstobranch_sync/<id>                       │
│     └── Actualiza: sent=true, db_key="ABC123", sync_date=now()     │
├─────────────────────────────────────────────────────────────────────┤
│  4. VALIDAR PICKING (button_validate)                              │
│     └── Busca borrador por stock_picking_id                        │
│     └── Obtiene db_key del borrador                                │
│     └── Crea registro en json.pos.transfers con db_key             │
├─────────────────────────────────────────────────────────────────────┤
│  5. SISTEMA EXTERNO consulta transferencias completadas            │
│     └── GET /api/transfers_done/<external_id>                      │
│     └── Recibe transferencias con db_key vinculado                 │
├─────────────────────────────────────────────────────────────────────┤
│  6. SISTEMA EXTERNO confirma sincronización                        │
│     └── PUT /api/transfers_done_sync/<db_key>                      │
│     └── Actualiza: sent=true, sync_date=now()                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Resumen de Endpoints

| Modelo | Acción | Endpoint | Método |
|--------|--------|----------|--------|
| `json.pos.transfers.edits` | Obtener borradores | `/api/tranferstobranch/<external_id>` | GET |
| `json.pos.transfers.edits` | Sincronizar por ID | `/api/transferstobranch_sync/<id>` | PUT |
| `json.pos.transfers` | Obtener completadas | `/api/transfers_done/<external_id>` | GET |
| `json.pos.transfers` | Sincronizar por db_key | `/api/transfers_done_sync/<db_key>` | PUT |

---

## Estructura de Datos JSON

### Campos del objeto `transfer`:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `llave` | string | Llave única del sistema externo |
| `iduser` | string | ID del empleado responsable |
| `idbodfrom` | string | ID externo de bodega origen |
| `idbodto` | string | ID externo de bodega destino |
| `serie` | string | Serie del punto de venta |
| `secuencia` | int | Número de secuencia |
| `tipo` | int | Tipo de transferencia (1=normal) |
| `l_close` | int | Flag de cierre |
| `l_recibido` | int | Flag de recibido |
| `l_sync` | int | Flag de sincronización |
| `t_init` | string | Fecha de inicio (YYYY-MM-DD) |
| `nota` | string | Notas de la transferencia |
| `responsable` | string | Email del responsable |
| `express` | string | Tipo express (0=normal, 1=express) |
| `cdet` | object | Detalle de productos compacto |

### Campos del objeto `transfer_products`:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `llave` | int | Número de línea |
| `orden` | string | Orden de la línea |
| `iditem` | string | ID externo del producto |
| `cantidad` | float | Cantidad transferida |
| `precio` | float | Precio unitario |
| `idlote` | int | ID del lote (0 si no aplica) |
| `disponible` | int | Cantidad disponible |
| `recibido` | int | Cantidad recibida |

---

## Códigos de Estado HTTP

| Código | Descripción |
|--------|-------------|
| 200 | Operación exitosa |
| 404 | Registro no encontrado |
| 500 | Error interno del servidor |
