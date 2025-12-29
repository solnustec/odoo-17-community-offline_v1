# Arquitectura del Sistema de Integración WhatsApp - Odoo 17

**Versión:** 1.0
**Fecha de Auditoría:** 2025-12-15
**Autor:** Auditoría Técnica Automatizada

---

## 1. Visión General del Sistema

Este sistema implementa una integración completa de **WhatsApp Business API** como canal de ventas para Odoo 17 Community. Permite:

- **Chatbot transaccional** para compras vía WhatsApp
- **Cotizaciones asistidas** por asesores
- **Gestión de pagos** (Tarjeta/Nuvei, Transferencia, Efectivo, Deuna, Ahorita)
- **Integración POS → Sales** para generar órdenes desde punto de venta
- **Métricas y trazabilidad** de interacciones

### Arquitectura de Alto Nivel (Diagrama Textual)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND / INTERFACES                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  [WhatsApp Business]    [Odoo POS]    [Odoo Backend]    [Payment Providers] │
│         │                    │              │                   │            │
│         ▼                    ▼              ▼                   ▼            │
│    Meta Webhook         JS Buttons      Chat UI           Webhooks          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAPA DE CONTROLADORES                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  /whatsapp_meta/response/message   (Meta Webhook - Mensajes entrantes)      │
│  /api/whatsapp_instance            (Configuración instancia)                 │
│  /simulate/message                  (Simulador App Móvil)                    │
│  /api/store/order/mark_paid/chatbot (Marcar orden como pagada)              │
│  /send_whatsapp_message             (Envío con Link Pay)                     │
│  /webhook/nuvei                     (Nuvei/Paymentez webhook)                │
│  /api/nuvei/status/<id>             (Estado transacción Nuvei)               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CAPA DE LÓGICA DE NEGOCIO                             │
├──────────────────────────┬──────────────────────────────────────────────────┤
│     FLUJOS CHATBOT       │              SERVICIOS                            │
│  ┌────────────────────┐  │  ┌─────────────────────────────────────────────┐ │
│  │ ConversationFlow   │  │  │ MetaAPi         (Envío mensajes WhatsApp)   │ │
│  │ BuyProductFlow     │  │  │ SaveOdoo        (Persistencia métricas)     │ │
│  │ InvoiceFlow        │  │  │ UserSession     (Gestión sesiones chatbot)  │ │
│  │ AsesorFlow         │  │  │ GetDelivery     (Cálculo envíos)            │ │
│  │ BranchFlow         │  │  │ GetBranch       (Sucursales/Geocoding)      │ │
│  │ DutyPharmacyFlow   │  │  │ Paymentez       (Integración Nuvei)         │ │
│  │ LinkPayAddFlow     │  │  └─────────────────────────────────────────────┘ │
│  └────────────────────┘  │                                                   │
└──────────────────────────┴──────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAPA DE MODELOS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  PRAGTECH_WHATSAPP_BASE:                                                     │
│  ├─ whatsapp.instance        (Configuración proveedor WhatsApp)              │
│  ├─ whatsapp.templates       (Templates de mensajes)                         │
│  ├─ whatsapp.messages        (Historial de mensajes)                         │
│  ├─ whatsapp.chatbot         (Sesiones y estados de conversación)            │
│  ├─ whatsapp.contact         (Contactos con nombre personalizado)            │
│  ├─ whatsapp.quick_reply     (Respuestas rápidas)                            │
│  ├─ res.partner.chatbot      (Partners de chatbot - NO hereda res.partner)   │
│  ├─ nuvei.transaction        (Transacciones de pago)                         │
│  └─ sale.order (heredado)    (Campos chatbot en órdenes)                     │
│                                                                              │
│  ADEVX_POS_SALES_ORDER:                                                      │
│  ├─ pos.config (heredado)    (Configuración SO desde POS)                    │
│  ├─ sale.order (heredado)    (Métodos create/write_from_pos_ui)              │
│  └─ sale.order.line (heredado) (Campo note y reward_product_id)              │
│                                                                              │
│  CHATBOT_MESSAGE:                                                            │
│  ├─ chatbot_message.city        (Métricas farmacia turno/24h)                │
│  ├─ chatbot_message.location    (Métricas ubicación usuario)                 │
│  ├─ chatbot_message.product     (Métricas productos buscados)                │
│  ├─ chatbot_message.interaction (Métricas interacciones menú)                │
│  └─ chatbot_message.delivery    (Métricas/logs de envío)                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Módulos del Sistema

### 2.1 pragtech_whatsapp_base

**Propósito:** Módulo principal de integración WhatsApp con Meta Business API.

**Versión:** 17.0.0.0.9
**Dependencias declaradas:** `base_setup`, `sale`, `web`, `base`, `point_of_sale`, `pos_sale`
**Dependencias reales (no declaradas):** `chatbot_message`

#### Responsabilidades:
1. Gestión de instancias WhatsApp (Meta, 1msg, Gupshup)
2. Recepción y envío de mensajes vía Meta Graph API
3. Máquina de estados del chatbot (flujos conversacionales)
4. Extensión de `sale.order` con campos para chatbot
5. Integración de pagos (Nuvei/Paymentez, Deuna, Ahorita)
6. Interfaz de chat estilo WhatsApp en Odoo backend
7. Gestión de templates de mensajes
8. Cron de inactividad (cancela órdenes abandonadas)

#### Estructura de Archivos:
```
pragtech_whatsapp_base/
├── models/
│   ├── whatsapp_instance.py       # Configuración de instancias
│   ├── whatsapp_templates.py      # Templates de mensajes
│   ├── whatsapp_messages.py       # Historial de mensajes
│   ├── whatsapp_chatbot.py        # Sesiones de chatbot
│   ├── whatsapp_quick_reply.py    # Respuestas rápidas
│   ├── res_partner.py             # res.partner.chatbot (modelo propio)
│   ├── sale_order.py              # Extensión sale.order
│   ├── response_webhook_chatbot.py # nuvei.transaction
│   └── ...
├── controllers/
│   ├── main.py                    # Webhook Meta principal
│   ├── webhook_paymentez.py       # Webhook Nuvei/Paymentez
│   ├── chatbot_appmovil.py        # Simulador app móvil
│   └── ...
├── templates/                      # LÓGICA DE FLUJOS (no templates XML)
│   ├── conversation_flow.py       # Flujo principal
│   ├── buyProduct_flow.py         # Flujo de compra
│   ├── invoice_flow.py            # Flujo de facturación/pago
│   ├── asesor_flow.py             # Flujo cotización asesor
│   ├── meta_api.py                # Cliente API Meta
│   ├── saveOdoo.py                # Guardado de métricas
│   └── ...
├── utils/
│   └── user_session.py            # Gestión de sesiones
└── static/src/                    # Assets frontend
```

### 2.2 adevx_pos_sales_order

**Propósito:** Integración bidireccional POS ↔ Sales Order.

**Versión:** No especificada
**Dependencias declaradas:** `sale_stock`, `pos_sale`
**Dependencias reales (no declaradas):** `pragtech_whatsapp_base` (usa `send_message_whatsapp`)

#### Responsabilidades:
1. Crear `sale.order` desde interfaz POS
2. Actualizar `sale.order` existentes desde POS
3. Auto-confirmación, auto-entrega, auto-facturación
4. Captura de firma digital
5. Envío de notificación WhatsApp post-creación

#### Estructura de Archivos:
```
adevx_pos_sales_order/
├── models/
│   ├── pos_config.py              # Configuración POS
│   ├── sale_order.py              # Métodos create/write_from_pos_ui
│   └── sale_order_line.py         # Campo note y reward_product_id
├── static/src/
│   ├── js/
│   │   ├── CreateSaleOrderButton.js
│   │   ├── UpdateSaleOrderButton.js
│   │   ├── SaleOrderPopup.js
│   │   ├── Order.js               # Patches al modelo Order
│   │   └── sale_order_management_screen.js
│   └── xml/
│       ├── CreateSaleOrderButton.xml
│       ├── UpdateSaleOrderButton.xml
│       └── SaleOrderPopup.xml
└── views/
    ├── pos_config.xml
    └── sale_order.xml
```

### 2.3 chatbot_message

**Propósito:** Almacenamiento de métricas e interacciones del chatbot.

**Versión:** 0.1
**Dependencias declaradas:** `base`

#### Responsabilidades:
1. Registrar interacciones del usuario con el menú
2. Almacenar búsquedas de productos
3. Guardar consultas de ubicación/farmacia
4. Registrar información de envíos/delivery

#### Estructura de Archivos:
```
chatbot_message/
├── models/
│   └── models.py                  # 5 modelos de métricas
├── controllers/
│   └── controllers.py             # ⚠️ CONTIENE MODELOS (error arquitectónico)
├── security/
│   └── ir.model.access.csv
└── views/
    ├── chatbot_products.xml
    ├── chatbot_location.xml
    ├── chatbot_city.xml
    ├── chatbot_menu.xml
    ├── chatbot_delivery_price.xml
    └── website_chatbot.xml
```

---

## 3. Flujo Completo de Datos

### 3.1 Flujo: Mensaje WhatsApp → Sale Order

```
1. RECEPCIÓN DEL MENSAJE
   ┌─────────────────────────────────────────────────────────────┐
   │ Meta envía POST a /whatsapp_meta/response/message          │
   │   ├─ Verificación de webhook (GET con hub.verify_token)    │
   │   └─ Payload con mensaje entrante                          │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
2. PROCESAMIENTO INICIAL (controller/main.py)
   ┌─────────────────────────────────────────────────────────────┐
   │ WhatsappBase._handle_session(message_dict)                  │
   │   ├─ Crear/obtener sesión whatsapp.chatbot                  │
   │   ├─ Crear res.partner.chatbot si no existe                 │
   │   └─ Actualizar last_activity                               │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
3. CREACIÓN DE MENSAJE
   ┌─────────────────────────────────────────────────────────────┐
   │ whatsapp.messages.create(message_dict)                      │
   │   ├─ Almacenar en BD                                        │
   │   ├─ Notificar via bus.bus (tiempo real)                    │
   │   └─ Manejar adjuntos (ir.attachment)                       │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
4. ENRUTAMIENTO AL FLUJO CORRECTO
   ┌─────────────────────────────────────────────────────────────┐
   │ WhatsappBase._handle_chatbot(message)                       │
   │   ├─ Verificar privacy_polic aceptada                       │
   │   ├─ Obtener estado actual de sesión                        │
   │   └─ Enrutar a handler según estado:                        │
   │       • "menu_principal" → enviar_mensaje_lista()           │
   │       • "promociones" → BuyProductFlow.start_flow()         │
   │       • "buscar_producto" → process_product_search()        │
   │       • "seleccionar_producto" → process_product_selection()│
   │       • "ingresar_cantidad" → process_quantity_input()      │
   │       • "tipo_envio" → botones_tipo_envio()                 │
   │       • "tipo_pago" → manejar_pago()                        │
   │       • "confirmar_pago" → handle_pay_method()              │
   │       • etc.                                                 │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
5. FLUJO DE COMPRA (BuyProductFlow)
   ┌─────────────────────────────────────────────────────────────┐
   │ a) start_flow() → Solicitar búsqueda de producto            │
   │ b) process_product_search() → Buscar en product.template    │
   │    └─ Usar AI search si disponible, fallback a dominio      │
   │ c) process_product_selection() → Usuario elige producto     │
   │    └─ Crear sale.order si no existe                         │
   │    └─ Crear sale.order.line                                 │
   │ d) process_quantity_input() → Validar stock y cantidad      │
   │    └─ Actualizar línea de orden                             │
   │    └─ Aplicar promociones/descuentos                        │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
6. FLUJO DE FACTURACIÓN/PAGO (InvoiceFlow)
   ┌─────────────────────────────────────────────────────────────┐
   │ a) manejar_envio() → Selección tipo envío                   │
   │ b) manejar_pago() → Selección método de pago                │
   │ c) solicitar_ced_ruc() → Captura datos facturación          │
   │ d) manejar_orden() → Crear/actualizar res.partner           │
   │ e) enviar_resumen_orden() → Mostrar resumen al usuario      │
   │ f) handle_pay() → Procesar según método:                    │
   │    ├─ Tarjeta → Paymentez/Nuvei (link de pago)              │
   │    ├─ Transferencia → Mostrar datos bancarios               │
   │    ├─ Efectivo → Mensaje de confirmación                    │
   │    ├─ Deuna → Generar deeplink                              │
   │    └─ Ahorita → Generar deeplink                            │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
7. CONFIRMACIÓN DE PAGO
   ┌─────────────────────────────────────────────────────────────┐
   │ handle_pay_method() → Validar comprobante                   │
   │   ├─ Descargar archivo desde Meta Graph API                 │
   │   ├─ Adjuntar a sale.order                                  │
   │   ├─ Verificar estado con proveedor (si aplica)             │
   │   └─ sale_order.action_confirm()                            │
   └─────────────────────────────────────────────────────────────┘
```

### 3.2 Flujo: POS → Sale Order → WhatsApp

```
1. INTERFAZ POS
   ┌─────────────────────────────────────────────────────────────┐
   │ Usuario hace clic en botón "Enviar al WhatsApp"             │
   │   └─ CreateSaleOrderButton.click()                          │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
2. POPUP DE CONFIRMACIÓN
   ┌─────────────────────────────────────────────────────────────┐
   │ SaleOrderPopup                                              │
   │   ├─ Captura nota de orden                                  │
   │   ├─ Captura celular cliente (+593)                         │
   │   ├─ Captura pago parcial (opcional)                        │
   │   └─ Captura firma digital (opcional)                       │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
3. CREACIÓN DE SALE ORDER
   ┌─────────────────────────────────────────────────────────────┐
   │ RPC: sale.order.create_from_pos_ui(values, flags)           │
   │   ├─ Crear sale.order con líneas                            │
   │   ├─ _auto_confirm_from_pos_ui() si flags activos:          │
   │   │   ├─ action_confirm() → Confirmar orden                 │
   │   │   ├─ picking.action_assign() → Reservar stock           │
   │   │   ├─ picking.button_validate() → Validar entrega        │
   │   │   └─ sale.advance.payment.inv → Crear factura           │
   │   └─ Retornar {name, id}                                    │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
4. ENVÍO NOTIFICACIÓN WHATSAPP
   ┌─────────────────────────────────────────────────────────────┐
   │ RPC: sale.order.send_message_whatsapp(id, number)           │
   │   └─ Definido en pragtech_whatsapp_base/models/sale_order.py│
   └─────────────────────────────────────────────────────────────┘
```

---

## 4. Dependencias entre Módulos

### 4.1 Diagrama de Dependencias

```
                    ┌─────────────────────┐
                    │    ODOO CORE        │
                    │  base, sale, pos,   │
                    │  pos_sale, web      │
                    └──────────┬──────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
            ▼                  ▼                  ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│ chatbot_message   │ │pragtech_whatsapp  │ │adevx_pos_sales    │
│                   │ │     _base         │ │     _order        │
│ (Métricas)        │ │ (Core WhatsApp)   │ │ (POS→Sales)       │
└───────────────────┘ └───────────────────┘ └───────────────────┘
         ▲                     │                      │
         │                     │                      │
         └─────────────────────┤                      │
           USA (no declarada)  │                      │
                               │                      │
                               └──────────────────────┘
                                 USA (no declarada)

LEYENDA:
─────── Dependencia declarada en __manifest__.py
─ ─ ─ ─ Dependencia real no declarada (PROBLEMA)
```

### 4.2 Dependencias No Declaradas (Crítico)

| Módulo Origen | Módulo Destino | Uso |
|---------------|----------------|-----|
| `pragtech_whatsapp_base` | `chatbot_message` | `chatbot_message.city.create()`, `chatbot_message.delivery.create()`, etc. |
| `adevx_pos_sales_order` | `pragtech_whatsapp_base` | `sale.order.send_message_whatsapp()` |

**Impacto:** Si se instala `adevx_pos_sales_order` sin `pragtech_whatsapp_base`, el botón "Enviar al WhatsApp" fallará con `AttributeError`.

---

## 5. Estados del Chatbot (Máquina de Estados)

El campo `state` en `whatsapp.chatbot` controla el flujo conversacional:

```
                                    ┌─────────────────┐
                                    │     START       │
                                    │ (nuevo mensaje) │
                                    └────────┬────────┘
                                             │
                              ┌──────────────┴──────────────┐
                              │ ¿privacy_polic aceptada?    │
                              └──────────────┬──────────────┘
                                    NO │           │ YES
                                       ▼           │
                              ┌─────────────────┐  │
                              │ confirmar_      │  │
                              │ politicas       │──┘
                              └─────────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │       menu_principal        │
                              │  (enviar_mensaje_lista)     │
                              └──────────────┬──────────────┘
                                             │
            ┌────────────────┬───────────────┼───────────────┬────────────────┐
            │                │               │               │                │
            ▼                ▼               ▼               ▼                ▼
    ┌───────────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────┐ ┌───────────────┐
    │cotizar-receta │ │promociones│ │sucursal-  │ │farmacia-turno │ │trabaja-con-   │
    │(AsesorFlow)   │ │(Compra)   │ │cercana    │ │               │ │nosotros       │
    └───────┬───────┘ └─────┬─────┘ └───────────┘ └───────────────┘ └───────────────┘
            │               │
            │               ▼
            │       ┌───────────────┐
            │       │buscar_producto│
            │       └───────┬───────┘
            │               │
            │               ▼
            │       ┌───────────────────┐
            │       │seleccionar_producto│
            │       └───────┬───────────┘
            │               │
            │               ▼
            │       ┌───────────────┐
            │       │ingresar_      │
            │       │cantidad       │
            │       └───────┬───────┘
            │               │
            │               ▼
            │       ┌───────────────┐
            │       │menu_secundario│◄────────────────────┐
            │       │(botones)      │                     │
            │       └───────┬───────┘                     │
            │               │                             │
            └───────────────┼─────────────────────────────┤
                            │                             │
                            ▼                             │
                    ┌───────────────┐              ┌──────┴──────┐
                    │ tipo_envio    │              │editar_orden │
                    └───────┬───────┘              └─────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ tipo_pago     │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────────────┐
                    │solicitar_cedula_ruc   │
                    └───────┬───────────────┘
                            │
               ┌────────────┴────────────┐
               │ ¿Partner existe?        │
               └────────────┬────────────┘
                     NO │         │ YES
                        ▼         │
               ┌───────────────┐  │
               │solicitar_     │  │
               │nombres        │──┘
               └───────┬───────┘
                       │
                       ▼
               ┌───────────────┐
               │solicitar_email│
               └───────┬───────┘
                       │
                       ▼
               ┌─────────────────────────┐
               │manejar_orden            │
               │(crear partner si nuevo) │
               └───────┬─────────────────┘
                       │
          ┌────────────┴────────────┐
          │ ¿tipo_envio=Domicilio?  │
          └────────────┬────────────┘
               YES │         │ NO
                   ▼         │
          ┌────────────────┐ │
          │solicitar_      │ │
          │ubicacion_envio │ │
          └───────┬────────┘ │
                  │          │
                  ▼          │
          ┌────────────────┐ │
          │manejar_precio_ │ │
          │provincia       │─┘
          └───────┬────────┘
                  │
                  ▼
          ┌─────────────────────┐
          │confirmar_orden_     │
          │factura              │
          └───────┬─────────────┘
                  │
                  ▼
          ┌───────────────┐
          │confirmar_pago │
          └───────┬───────┘
                  │
     ┌────────────┴────────────────────────────┐
     │ Método de pago                          │
     └────────────┬────────────────────────────┘
                  │
    ┌─────────────┼─────────────┬─────────────┐
    │             │             │             │
    ▼             ▼             ▼             ▼
┌────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│Tarjeta │  │Transf.   │  │Efectivo  │  │Deuna/    │
│(Nuvei) │  │          │  │          │  │Ahorita   │
└───┬────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
    │            │             │             │
    └────────────┴─────────────┴─────────────┘
                        │
                        ▼
              ┌───────────────────┐
              │ salir/cerrar_chat │
              └───────────────────┘
```

---

## 6. Puntos de Extensión

### 6.1 Agregar Nuevo Flujo de Chatbot

1. Crear clase en `pragtech_whatsapp_base/templates/nuevo_flow.py`
2. Importar en `templates/__init__.py`
3. Agregar opción al menú en `MetaAPi.enviar_mensaje_lista()`
4. Agregar handler en `ConversationFlow.manejar_respuesta_interactiva()`
5. Definir estados necesarios

### 6.2 Agregar Nuevo Método de Pago

1. Agregar opción en `MetaAPi.botones_tipo_pago()`
2. Agregar mapping en `ConversationFlow.pagos_map`
3. Crear método `procesar_pago_nuevo()` en `InvoiceFlow`
4. Agregar lógica de verificación en `handle_pay_method()`

### 6.3 Agregar Nueva Métrica

1. Crear modelo en `chatbot_message/models/models.py`
2. Agregar permisos en `security/ir.model.access.csv`
3. Crear vista en `views/`
4. Agregar menú en `views/website_chatbot.xml`
5. Llamar `SaveOdoo.save_xxx()` desde flujo correspondiente

---

## 7. Reglas Clave de Negocio

### 7.1 Validaciones

| Regla | Ubicación | Descripción |
|-------|-----------|-------------|
| Cédula/RUC | `InvoiceFlow.manejar_cedula_ruc()` | Debe ser 10 (cédula) o 13 (RUC) dígitos |
| Email | `InvoiceFlow.validar_email()` | Regex básico con @ y . |
| Teléfono Ecuador | `SaleOrderPopup.action_confirm()` | 9 dígitos + prefijo 593 = 12 total |
| Stock disponible | `BuyProductFlow.process_quantity_input()` | qty_on_hand - qty_reserved > 0 |
| Privacidad | `WhatsappBase._handle_chatbot()` | Debe aceptar políticas antes de usar |

### 7.2 Cálculo de Envío (Loja ciudad)

```python
# Ubicación: InvoiceFlow.manejar_precio_provincia()
ORIGEN_LAT, ORIGEN_LON = -4.000426, -79.20384
distancia_km = GetDelivery.calculate_distance([ORIGEN, destino])

if distancia_metros <= 3000:
    precio_envio = 1.75  # Costo mínimo
else:
    precio_envio = 1.75
    km_adicionales = (distancia_metros - 3000) // 1000
    precio_envio += km_adicionales * 0.40  # $0.40/km adicional
    metros_sobrantes = (distancia_metros - 3000) % 1000
    precio_envio += calcular_costo_por_fracciones(metros_sobrantes)
```

### 7.3 Inactividad (Cron)

```python
# Ubicación: whatsapp.chatbot._cron_check_inactivity()
# Ejecuta cada 1 minuto

if minutos_inactivo >= 60 and minutos_inactivo < 120:
    # Enviar mensaje de inactividad
    # Cancelar órdenes relacionadas
    # Cancelar pickings
    # Cancelar facturas

if minutos_inactivo >= 60:
    session.state = 'cerrar_chat'
```

---

## 8. Suposiciones Técnicas Importantes

### 8.1 Hardcoded Values

| Valor | Ubicación | Descripción |
|-------|-----------|-------------|
| `warehouse_id = 386` | `BuyProductFlow.get_product_quantity()` | Almacén fijo para búsqueda de stock |
| `website_id = 1` | `BuyProductFlow.process_product_selection()` | Website fijo para órdenes |
| `country_id = 63` | `InvoiceFlow.manejar_orden()` | Ecuador |
| `America/Guayaquil` | Múltiples archivos | Timezone hardcodeada |
| `partner_vat = '1101152001121'` | `BuyProductFlow` | Cliente temporal "Chatbot Prueba" |

### 8.2 Almacenamiento de Estado

El campo `whatsapp.chatbot.orden` almacena un **JSON serializado** con:

```json
{
  "sale_order_id": 123,
  "selected_line_id": 456,
  "selected_product": {"id": 789, "name": "...", "price": 10.0},
  "temp_product_list": {"productos": [...]},
  "tipo_envio": "Domicilio",
  "tipo_pago": "Tarjeta",
  "documento": "1234567890",
  "email": "cliente@email.com",
  "nombres_completo": "Juan Pérez",
  "direccion_factura": "...",
  "direccion_texto_gps": {...},
  "link_direccion_gps": "https://maps.google.com/...",
  "precio_envio": 3.50,
  "distancia_km": 5.2
}
```

**Riesgo:** Propenso a errores de parseo JSON y pérdida de datos si se corrompe.

---

## 9. Seguridad

### 9.1 Endpoints Públicos (auth='public')

| Endpoint | Propósito | Riesgo |
|----------|-----------|--------|
| `/whatsapp_meta/response/message` | Webhook Meta | Bajo (verificación por token) |
| `/simulate/message` | Simulador | **ALTO** (sin autenticación) |
| `/api/store/order/mark_paid/chatbot` | Marcar pagado | **ALTO** (sin autenticación) |
| `/send_whatsapp_message` | Enviar mensaje | **MEDIO** |
| `/webhook/nuvei` | Webhook Nuvei | Bajo (datos de pago) |
| `/api/nuvei/status/<id>` | Estado transacción | **MEDIO** (información expuesta) |

### 9.2 Permisos de Modelos

Todos los modelos usan `base.group_user` con CRUD completo. No hay restricciones por compañía ni reglas de dominio (record rules).

### 9.3 Uso de sudo()

El código hace uso extensivo de `sudo()` para bypass de permisos, especialmente en:
- Creación de `res.partner`
- Creación de `sale.order`
- Acceso a `whatsapp.chatbot`
- Modificación de pickings/invoices

---

## 10. Configuración Requerida

### 10.1 Parámetros del Sistema (ir.config_parameter)

| Clave | Descripción |
|-------|-------------|
| `web.base.url` | URL base de Odoo |
| `pragtech_whatsapp_messenger.whatsapp_phone_number` | Número de teléfono Meta |
| `pragtech_whatsapp_messenger.whatsapp_meta_token` | Token API Meta |
| `pragtech_whatsapp_messenger.whatsapp_meta_webhook_token` | Token verificación webhook |
| `whatsapp.token` | Token para descarga de archivos |
| `numero_chatbot` | Número del chatbot (fallback) |

### 10.2 Instancia WhatsApp Requerida

Debe existir un registro `whatsapp.instance` con:
- `status = 'enable'`
- `provider = 'meta'`
- `default_instance = True`
- Campos Meta configurados

---

## 11. Problemas Arquitectónicos Identificados

### CRÍTICOS (P0)

| ID | Problema | Impacto | Ubicación |
|----|----------|---------|-----------|
| P0-1 | Dependencias no declaradas en `__manifest__.py` | Errores de instalación, `AttributeError` en runtime | `pragtech_whatsapp_base`, `adevx_pos_sales_order` |
| P0-2 | Endpoints públicos sin autenticación | Vulnerabilidad de seguridad | `/simulate/message`, `/api/store/order/mark_paid/chatbot` |
| P0-3 | Warehouse ID hardcodeado (386) | Falla en otros entornos | `buyProduct_flow.py:174` |
| P0-4 | JSON serializado para estado | Pérdida de datos, errores de parseo | `whatsapp.chatbot.orden` |

### ALTOS (P1)

| ID | Problema | Impacto | Ubicación |
|----|----------|---------|-----------|
| P1-1 | Modelos definidos en controllers | Violación de arquitectura Odoo | `chatbot_message/controllers/controllers.py` |
| P1-2 | Bug timezone (-5h redundante) | Fechas incorrectas | `chatbot_message/models/models.py` |
| P1-3 | Módulo pragtech hace demasiadas cosas | Difícil mantenimiento | Todo el módulo |
| P1-4 | Sin validación de webhook Meta | Mensajes falsos procesados | `controller/main.py` |

### MEDIOS (P2)

| ID | Problema | Impacto | Ubicación |
|----|----------|---------|-----------|
| P2-1 | `res.partner.chatbot` no hereda `res.partner` | Duplicación de datos, clientes no integrados | `res_partner.py` |
| P2-2 | `time.sleep()` en flujos | Bloqueo de workers | `invoice_flow.py` |
| P2-3 | Sin índices en campos frecuentes | Performance en consultas | Varios modelos |
| P2-4 | Logs con `print()` en lugar de `_logger` | Logs no estructurados | Múltiples archivos |

---

## 12. Recomendaciones de Mejora

Ver documento separado: `IMPROVEMENT_PROPOSALS.md`

---

## Apéndice A: Glosario

| Término | Definición |
|---------|------------|
| **ChatId** | Identificador único de conversación WhatsApp (número@c.us) |
| **Deeplink** | URL de pago móvil (Deuna/Ahorita) |
| **Flow** | Clase que maneja un flujo conversacional específico |
| **Meta Graph API** | API de Facebook/Meta para WhatsApp Business |
| **Nuvei/Paymentez** | Proveedor de pagos con tarjeta |
| **Session** | Registro `whatsapp.chatbot` que mantiene estado de conversación |

---

## Apéndice B: Archivos Clave

| Archivo | Propósito | LOC aprox. |
|---------|-----------|------------|
| `pragtech_whatsapp_base/controller/main.py` | Webhook principal | 500 |
| `pragtech_whatsapp_base/templates/conversation_flow.py` | Router de flujos | 355 |
| `pragtech_whatsapp_base/templates/buyProduct_flow.py` | Flujo de compra | 465 |
| `pragtech_whatsapp_base/templates/invoice_flow.py` | Flujo de pago | 1,657 |
| `pragtech_whatsapp_base/templates/meta_api.py` | Cliente Meta API | 937 |
| `pragtech_whatsapp_base/models/whatsapp_messages.py` | Modelo mensajes | 400+ |
| `adevx_pos_sales_order/static/src/js/CreateSaleOrderButton.js` | Botón POS | 150 |

---

*Documento generado automáticamente como parte de auditoría técnica.*
