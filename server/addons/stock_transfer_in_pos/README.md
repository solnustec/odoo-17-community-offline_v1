# Transferencia de Stock en POS

## Descripcion General

Este modulo permite realizar transferencias de stock entre almacenes directamente desde el Punto de Venta (POS), sin necesidad de salir de la sesion. Proporciona una interfaz completa para crear, gestionar y validar transferencias de inventario en tiempo real.

**Version:** 17.0.1.0.0
**Categoria:** Point of Sale
**Licencia:** AGPL-3
**Dependencias:** base, point_of_sale

---

## Caracteristicas Principales

| Caracteristica | Descripcion |
|----------------|-------------|
| Transferencias desde POS | Crear transferencias directamente desde la pantalla de productos |
| Gestion de Transferencias | Ver y administrar transferencias enviadas y recibidas |
| Validacion de Recepciones | Reconciliar cantidades enviadas vs recibidas |
| Notificaciones en Tiempo Real | Actualizaciones de stock via BUS broadcast |
| Verificacion por PIN | Seguridad mediante PIN de empleado |
| Impresion de Recibos | Generacion automatica de PDF de transferencia |
| Filtrado Avanzado | Filtros por almacen, estado y rango de fechas |
| Paginacion Infinita | Carga incremental de registros |
| Tipos de Transferencia | Normal y Express |

---

## Instalacion

1. Copiar el modulo en el directorio de addons de Odoo
2. Actualizar la lista de aplicaciones desde el menu de Apps
3. Buscar "Transferencia de Stock en POS" e instalar
4. Configurar el modulo desde Punto de Venta > Configuracion

---

## Configuracion

### Activar Transferencias de Stock

1. Ir a **Punto de Venta > Configuracion > Ajustes**
2. En la seccion **Transferencias de Stock**:
   - Activar **"Habilitar Transferencias de Stock"** para permitir transferencias desde POS
   - Opcionalmente activar **"Permitir ver transferencias automaticas"** para visualizar transferencias generadas automaticamente por el sistema

---

## Estructura del Modulo

```
stock_transfer_in_pos/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── pos_config.py          # Logica principal de transferencias
│   ├── res_config_settings.py # Configuracion del modulo
│   └── stock_picking.py       # Validacion y notificaciones
├── static/
│   └── src/
│       ├── js/
│       │   ├── stock_transfer.js         # Boton de transferencia
│       │   ├── transfer_create_popup.js  # Popup de creacion
│       │   ├── transfer_ref_popup.js     # Popup de referencia
│       │   ├── transfers_modal.js        # Modal de gestion
│       │   ├── transfer_list_view.js     # Menu en navbar
│       │   └── record_selector_extend.js # Selector de almacen
│       └── xml/
│           ├── stock_transfer_button.xml
│           ├── transfer_create_popup.xml
│           ├── transfer_ref_popup.xml
│           ├── tranfers_modal.xml
│           ├── tranfers_list_view.xml
│           └── record_selector_extends.xml
└── views/
    └── res_config_settings_views.xml
```

---

## Uso del Modulo

### 1. Crear una Transferencia

1. Abrir el POS y agregar productos al pedido
2. Hacer clic en el boton **"Transferencias"** en la pantalla de productos
3. En el popup de creacion:
   - **Almacen Origen**: Se establece automaticamente desde la configuracion
   - **Almacen Destino**: Seleccionar el almacen de destino
   - **Tipo de Transferencia**: Normal (0) o Express (1)
   - **Nota**: Agregar comentarios opcionales
4. Ingresar PIN de empleado si es requerido
5. Hacer clic en **"Crear"**
6. Se muestra el numero de referencia y opcion de imprimir

### 2. Gestionar Transferencias

Acceder desde el menu **hamburguesa > Transferencias** en el POS:

#### Pestana: Transferencias Propias (Enviadas)
- Lista de transferencias creadas desde este almacen
- Filtros: Destino, Estado, Rango de fechas
- Acciones: Ver detalles, Editar (si esta en borrador)

#### Pestana: Transferencias Externas (Recibidas)
- Lista de transferencias destinadas a este almacen
- Filtros: Origen, Estado, Rango de fechas
- Acciones: Ver detalles, Validar (si esta pendiente)

#### Pestana: Productos por Recibir
- Lista detallada de productos pendientes de recepcion
- Filtros: Producto, Rango de fechas
- Muestra: Cantidad esperada vs recibida
- Accion: Validar transferencia completa

### 3. Validar una Transferencia

1. Ir a la pestana **"Transferencias Externas"**
2. Hacer clic en **"Validar"** en la transferencia deseada
3. En el modal de validacion:
   - Revisar cantidades esperadas
   - Actualizar cantidades recibidas si hay diferencias
   - Agregar notas/observaciones
4. Hacer clic en **"Validar"** para confirmar la recepcion

---

## Modelos de Datos

### pos.config (Extendido)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `stock_transfer` | Boolean | Habilita transferencias desde POS |
| `show_auto_transfers` | Boolean | Muestra transferencias automaticas |

**Metodos principales:**

| Metodo | Descripcion |
|--------|-------------|
| `get_stock_transfer_list()` | Obtiene tipos de picking, ubicaciones y almacen |
| `create_transfer()` | Crea una transferencia de stock |
| `_get_stock_updates_for_products()` | Calcula actualizaciones de stock |
| `_notify_stock_update()` | Envia notificacion BUS de actualizacion |

### stock.picking (Extendido)

| Metodo | Descripcion |
|--------|-------------|
| `button_validate()` | Override para enviar notificaciones al validar |
| `_notify_pos_stock_validated()` | Notifica validacion al POS |
| `_get_validated_stock_updates()` | Calcula niveles finales de stock |
| `get_transfer_config()` | Obtiene configuracion de transferencias |

---

## Componentes Frontend

### Componentes OWL

| Componente | Descripcion |
|------------|-------------|
| `StockTransferButton` | Boton en pantalla de productos para iniciar transferencia |
| `CreateTransferPopup` | Popup para crear nueva transferencia |
| `TransferRefPopup` | Muestra referencia e imprime recibo |
| `TransferModal` | Modal principal de gestion de transferencias |
| `TransferDetailModal` | Vista detallada de una transferencia |
| `TransferValidationModal` | Modal para validar recepciones |
| `RecordSelectorReadonly` | Selector de almacen con modo solo lectura |

### Integracion con POS

- **Pantalla de Productos**: Boton "Transferencias" condicional
- **Navbar**: Menu "Transferencias" en el menu hamburguesa
- **Pedidos**: Lee productos del pedido actual
- **Stock Local**: Actualiza cache de stock en POS
- **Notificaciones**: Sistema de popups y alertas

---

## Flujo de Trabajo

```
┌─────────────────────────────────────────────────────────────────┐
│                    FLUJO DE TRANSFERENCIA                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. INICIO                                                      │
│     └─> Usuario agrega productos al pedido                      │
│     └─> Clic en "Transferencias"                                │
│                                                                 │
│  2. CREACION                                                    │
│     └─> Seleccionar almacen destino                             │
│     └─> Elegir tipo (Normal/Express)                            │
│     └─> Verificar PIN                                           │
│     └─> Crear transferencia                                     │
│                                                                 │
│  3. PROCESAMIENTO BACKEND                                       │
│     └─> Crear stock.picking con movimientos                     │
│     └─> Confirmar y asignar (reservar stock)                    │
│     └─> Enviar notificacion BUS                                 │
│                                                                 │
│  4. CONFIRMACION                                                │
│     └─> Mostrar referencia                                      │
│     └─> Imprimir recibo (PDF)                                   │
│     └─> Limpiar lineas del pedido                               │
│     └─> Actualizar stock local                                  │
│                                                                 │
│  5. RECEPCION (Almacen Destino)                                 │
│     └─> Ver en "Transferencias Externas"                        │
│     └─> Validar cantidades recibidas                            │
│     └─> Confirmar recepcion                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Estados de Transferencia

| Estado | Codigo | Descripcion |
|--------|--------|-------------|
| Borrador | `draft` | Transferencia creada, no confirmada |
| En Espera | `waiting` | Esperando disponibilidad de stock |
| Confirmado | `confirmed` | Confirmada, pendiente de asignacion |
| Asignado | `assigned` | Stock reservado, lista para procesar |
| Completado | `done` | Transferencia finalizada |
| Cancelado | `cancel` | Transferencia cancelada |

---

## Notificaciones en Tiempo Real

El modulo utiliza el sistema de BUS de Odoo para notificaciones:

- **POS_STOCK_UPDATE**: Actualiza niveles de stock en todos los POS
- **Canal**: `pos_notification`
- **Eventos**:
  - Creacion de transferencia (reserva de stock)
  - Validacion de transferencia (movimiento completado)

---

## Seguridad

- **Verificacion por PIN**: Los empleados deben ingresar su PIN para crear transferencias
- **Filtrado por Compania**: Las transferencias se filtran por compania del usuario
- **Permisos Heredados**: Utiliza permisos de `point_of_sale` y `stock`
- **Modo sudo()**: Creacion de transferencias con privilegios elevados

---

## Personalizacion

### Agregar Nuevos Tipos de Transferencia

En `transfer_create_popup.js`, modificar el selector de tipo:

```javascript
// Agregar opcion en el template XML
<option value="2">Urgente</option>
```

### Modificar Campos de Filtrado

En `transfers_modal.js`, agregar nuevos filtros en el estado:

```javascript
filters: {
    sent: {
        destination: null,
        state: null,
        dateFrom: null,
        dateTo: null,
        // Agregar nuevo filtro
        priority: null
    }
}
```

---

## Solucion de Problemas

### El boton de Transferencias no aparece

1. Verificar que la opcion este habilitada en Configuracion > Punto de Venta
2. Refrescar la sesion del POS
3. Verificar que el usuario tenga permisos de POS

### Error al crear transferencia

1. Verificar que hay productos en el pedido
2. Confirmar que los productos son de tipo "almacenable"
3. Verificar que el PIN del empleado es correcto

### Las notificaciones no llegan

1. Verificar que el servicio de BUS esta activo
2. Comprobar la conexion a internet
3. Refrescar la pagina del POS

### No se pueden validar transferencias

1. Verificar que la transferencia esta en estado "Asignado" o "Borrador"
2. Confirmar permisos del usuario para validar stock.picking
3. Verificar que hay stock disponible en origen

---

## Dependencias Tecnicas

### Python
- `odoo.models`
- `odoo.fields`
- `odoo.api`
- `odoo.tools`

### JavaScript/OWL
- `@odoo/owl`
- `@point_of_sale/app/store/pos_store`
- `@point_of_sale/app/popup/abstract_awaitable_popup`
- `@point_of_sale/app/generic_components/record_selector/record_selector`

### Modelos Odoo Utilizados
- `pos.config`
- `pos.session`
- `stock.picking`
- `stock.picking.type`
- `stock.move`
- `stock.location`
- `stock.warehouse`
- `stock.quant`
- `product.product`
- `res.users`
- `res.company`

---

## Changelog

### Version 17.0.1.0.0
- Release inicial
- Creacion de transferencias desde POS
- Gestion de transferencias enviadas y recibidas
- Validacion de recepciones
- Notificaciones en tiempo real
- Impresion de recibos
- Filtrado y paginacion avanzada
- Soporte para tipos Normal y Express

---

## Creditos

**Autor:** Cybrosys Techno Solutions
**Mantenimiento:** Equipo de Desarrollo
**Licencia:** AGPL-3

---

## Soporte

Para reportar bugs o solicitar mejoras, contactar al equipo de desarrollo o crear un issue en el repositorio del proyecto.
