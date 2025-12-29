# Propuestas de Mejora - Integración WhatsApp Odoo 17

**Fecha:** 2025-12-15
**Basado en:** Auditoría técnica de `pragtech_whatsapp_base`, `adevx_pos_sales_order`, `chatbot_message`

---

## Resumen Ejecutivo

Este documento presenta las mejoras técnicas recomendadas, priorizadas por criticidad e impacto. Las propuestas están diseñadas para:

1. Corregir problemas de seguridad
2. Eliminar errores de arquitectura
3. Mejorar mantenibilidad y escalabilidad
4. Reducir deuda técnica

---

## Prioridad CRÍTICA (P0) - Implementar Inmediatamente

### P0-1: Declarar Dependencias Faltantes en __manifest__.py

**Problema:** Los módulos usan código de otros módulos sin declarar la dependencia, causando errores de instalación y runtime.

**Solución:**

```python
# pragtech_whatsapp_base/__manifest__.py
'depends': [
    'base_setup', 'sale', 'web', 'base',
    'point_of_sale', 'pos_sale',
    'chatbot_message',  # AGREGAR - usa chatbot_message.* modelos
],

# adevx_pos_sales_order/__manifest__.py
'depends': [
    'sale_stock', 'pos_sale',
    'pragtech_whatsapp_base',  # AGREGAR - usa send_message_whatsapp()
],
```

**Alternativa (si no se quiere dependencia dura):**

```python
# adevx_pos_sales_order/static/src/js/CreateSaleOrderButton.js
// Línea 116: Hacer el envío de WhatsApp opcional
try {
    await this.orm.call("sale.order", "send_message_whatsapp", [result.id, result.id, fullEcuPhone]);
} catch (e) {
    console.warn("WhatsApp integration not available:", e);
}
```

---

### P0-2: Asegurar Endpoints Públicos Críticos

**Problema:** Endpoints sin autenticación permiten manipular órdenes y simular mensajes.

**Solución para `/simulate/message`:**

```python
# pragtech_whatsapp_base/controller/chatbot_appmovil.py
from odoo import http
from odoo.http import request

class SimulateMessageController(http.Controller):

    @http.route('/simulate/message', type='json', auth='user', csrf=True)  # CAMBIAR auth='user'
    def simulate_message(self, **kwargs):
        # Verificar que el usuario tiene permisos
        if not request.env.user.has_group('pragtech_whatsapp_base.group_whatsApp_see_all_messages'):
            return {'error': 'Acceso denegado'}
        # ... resto del código
```

**Solución para `/api/store/order/mark_paid/chatbot`:**

```python
# pragtech_whatsapp_base/controller/order_update.py
import hmac
import hashlib

class OrderUpdate(http.Controller):

    @http.route('/api/store/order/mark_paid/chatbot', type='http', auth='public',
                methods=['POST'], csrf=False)
    def mark_paid(self, **kwargs):
        # Verificar firma HMAC
        signature = request.httprequest.headers.get('X-Signature')
        secret = request.env['ir.config_parameter'].sudo().get_param('chatbot.api.secret')

        if not self._verify_signature(request.httprequest.data, signature, secret):
            return Response('Unauthorized', status=401)

        # ... resto del código

    def _verify_signature(self, payload, signature, secret):
        if not signature or not secret:
            return False
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
```

---

### P0-3: Eliminar Warehouse ID Hardcodeado

**Problema:** `warehouse_id = 386` hardcodeado causa fallas en otros entornos.

**Solución:**

```python
# pragtech_whatsapp_base/templates/buyProduct_flow.py

@classmethod
def get_product_quantity(cls, search_term, warehouse_id=None):
    """Método principal para buscar productos con stock."""
    try:
        # Obtener warehouse desde configuración si no se proporciona
        if not warehouse_id:
            warehouse_id = cls._get_default_warehouse_id()

        terms = cls.parse_search_input(search_term)
        if not terms:
            return []
        domain = cls.build_search_domain(terms)
        products = request.env['product.template'].sudo().search(domain, limit=30)
        result = cls.filter_products_server_side(products, warehouse_id, search_term)
        return result
    except Exception as e:
        _logger.exception("Error en búsqueda de productos")
        return []

@classmethod
def _get_default_warehouse_id(cls):
    """Obtiene el warehouse por defecto desde configuración."""
    config_param = request.env['ir.config_parameter'].sudo()
    warehouse_id = config_param.get_param('chatbot.default_warehouse_id')

    if warehouse_id:
        return int(warehouse_id)

    # Fallback: primer warehouse de la compañía
    company = request.env.company
    warehouse = request.env['stock.warehouse'].sudo().search([
        ('company_id', '=', company.id)
    ], limit=1)

    return warehouse.id if warehouse else False
```

**Agregar parámetro de configuración:**

```xml
<!-- pragtech_whatsapp_base/data/config_data.xml -->
<record id="chatbot_default_warehouse_id" model="ir.config_parameter">
    <field name="key">chatbot.default_warehouse_id</field>
    <field name="value">1</field>
</record>
```

---

### P0-4: Migrar Estado JSON a Campos Relacionales

**Problema:** El campo `orden` en `whatsapp.chatbot` guarda JSON serializado, propenso a errores.

**Solución - Fase 1 (Campos auxiliares):**

```python
# pragtech_whatsapp_base/models/whatsapp_chatbot.py

class WhatsappChatbot(models.Model):
    _name = 'whatsapp.chatbot'

    # Campos existentes...
    orden = fields.Text()  # Mantener temporalmente para compatibilidad

    # NUEVOS CAMPOS RELACIONALES
    current_sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden Actual',
        ondelete='set null',
        index=True
    )
    current_line_id = fields.Many2one(
        'sale.order.line',
        string='Línea Seleccionada',
        ondelete='set null'
    )
    tipo_envio = fields.Selection([
        ('domicilio', 'Domicilio'),
        ('retiro_local', 'Retiro en Local')
    ], string='Tipo de Envío')
    tipo_pago = fields.Selection([
        ('tarjeta', 'Tarjeta'),
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('deuna', 'Deuna!'),
        ('ahorita', 'Ahorita!')
    ], string='Tipo de Pago')
    documento_factura = fields.Char('Documento', size=13)
    email_factura = fields.Char('Email')
    nombres_factura = fields.Char('Nombres')
    direccion_gps_lat = fields.Float('Latitud', digits=(10, 8))
    direccion_gps_lng = fields.Float('Longitud', digits=(10, 8))
    direccion_gps_link = fields.Char('Link GPS')
    precio_envio_calculado = fields.Float('Precio Envío')
    distancia_km = fields.Float('Distancia (km)')

    # Productos temporales para selección
    temp_product_ids = fields.Many2many(
        'product.template',
        'chatbot_temp_products_rel',
        'chatbot_id',
        'product_id',
        string='Productos Temporales'
    )

    def get_orden_data(self):
        """Método de transición: lee de campos o de JSON."""
        if self.current_sale_order_id:
            return {
                'sale_order_id': self.current_sale_order_id.id,
                'selected_line_id': self.current_line_id.id if self.current_line_id else None,
                'tipo_envio': self.tipo_envio,
                'tipo_pago': self.tipo_pago,
                'documento': self.documento_factura,
                'email': self.email_factura,
                # ... etc
            }
        # Fallback a JSON antiguo
        try:
            return json.loads(self.orden or '{}')
        except:
            return {}

    def set_orden_data(self, data):
        """Método de transición: escribe a campos y JSON."""
        vals = {}
        if 'sale_order_id' in data:
            vals['current_sale_order_id'] = data['sale_order_id']
        if 'selected_line_id' in data:
            vals['current_line_id'] = data['selected_line_id']
        if 'tipo_envio' in data:
            vals['tipo_envio'] = data['tipo_envio'].lower().replace(' ', '_') if data['tipo_envio'] else False
        # ... mapear resto de campos

        # También actualizar JSON para compatibilidad
        vals['orden'] = json.dumps(data)

        self.write(vals)
```

---

## Prioridad ALTA (P1) - Implementar en Sprint Actual

### P1-1: Mover Modelos Fuera de Controllers

**Problema:** `chatbot_message/controllers/controllers.py` contiene definiciones de modelos.

**Solución:**

```bash
# 1. Eliminar las definiciones de modelos de controllers.py
# 2. Dejar controllers.py vacío o con un placeholder:
```

```python
# chatbot_message/controllers/controllers.py
# -*- coding: utf-8 -*-
"""
Este archivo está vacío intencionalmente.
Los modelos están definidos en models/models.py
"""
```

**Nota:** Las definiciones en `controllers.py` son duplicados inconsistentes de `models.py`. Verificar que no hay diferencias funcionales y eliminar.

---

### P1-2: Corregir Bug de Timezone

**Problema:** En `chatbot_message/models/models.py`, se resta 5 horas después de convertir a timezone, resultando en fechas incorrectas.

**Código actual (incorrecto):**
```python
def create(self, vals):
    user_tz = pytz.timezone('America/Guayaquil')
    local_time = datetime.now(user_tz)
    local_date_minus_5 = (local_time - timedelta(hours=5)).date()  # BUG
    vals['create_date'] = local_date_minus_5
```

**Solución:**
```python
# chatbot_message/models/models.py
from datetime import datetime
import pytz

class UserCity(models.Model):
    _name = 'chatbot_message.city'

    # Cambiar create_date a Datetime para usar el comportamiento estándar de Odoo
    # O si necesita ser Date:

    @api.model_create_multi
    def create(self, vals_list):
        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)

        for vals in vals_list:
            # La fecha ya está en la zona horaria correcta
            vals['create_date'] = now_local.date()  # SIN restar 5 horas
            vals['create_time'] = now_local.strftime('%H:%M:%S')

        return super().create(vals_list)
```

---

### P1-3: Separar Responsabilidades de pragtech_whatsapp_base

**Problema:** El módulo hace demasiadas cosas, dificultando mantenimiento.

**Propuesta de Refactorización:**

```
ANTES (pragtech_whatsapp_base):
├── WhatsApp Instance Management
├── WhatsApp Messages
├── Chatbot State Machine
├── Conversation Flows
├── Payment Integration (Nuvei, Deuna, Ahorita)
├── Sale Order Extensions
├── Geocoding/Delivery
└── Metrics Collection

DESPUÉS (módulos separados):

1. pragtech_whatsapp_base (reducido)
   ├── WhatsApp Instance Management
   ├── WhatsApp Messages
   ├── WhatsApp Templates
   └── Meta API Client

2. pragtech_whatsapp_chatbot (nuevo)
   ├── Chatbot State Machine
   ├── Conversation Flows
   ├── Session Management
   └── User Messages Config

3. pragtech_whatsapp_sale (nuevo)
   ├── Sale Order Extensions
   ├── POS Integration Bridge
   └── Order Summary via WhatsApp

4. pragtech_whatsapp_payment (nuevo)
   ├── Nuvei/Paymentez Integration
   ├── Deuna Integration
   ├── Ahorita Integration
   └── Payment Webhooks

5. pragtech_whatsapp_delivery (nuevo)
   ├── Geocoding Services
   ├── Delivery Price Calculation
   └── Shipping Methods Integration
```

**Dependencias propuestas:**
```
pragtech_whatsapp_base
    ↑
pragtech_whatsapp_chatbot ←── pragtech_whatsapp_sale
    ↑                              ↑
pragtech_whatsapp_payment    pragtech_whatsapp_delivery
```

**Implementación gradual:**
1. Fase 1: Extraer `pragtech_whatsapp_payment` (más aislado)
2. Fase 2: Extraer `pragtech_whatsapp_delivery`
3. Fase 3: Separar `pragtech_whatsapp_chatbot` y `pragtech_whatsapp_sale`

---

### P1-4: Agregar Validación de Webhook Meta

**Problema:** Los mensajes del webhook no se validan contra la firma de Meta.

**Solución:**

```python
# pragtech_whatsapp_base/controller/main.py
import hmac
import hashlib

class WhatsappBase(http.Controller):

    @http.route('/whatsapp_meta/response/message', type='http', auth='public',
                methods=['GET', 'POST'], csrf=False)
    def whatsapp_response(self, **kwargs):
        if request.httprequest.method == 'GET':
            return self._verify_webhook(kwargs)

        # Validar firma para POST
        if not self._validate_meta_signature():
            _logger.warning("Firma de Meta inválida - posible mensaje falso")
            return Response('Invalid signature', status=403)

        return self._process_webhook()

    def _validate_meta_signature(self):
        """Valida la firma X-Hub-Signature-256 de Meta."""
        signature_header = request.httprequest.headers.get('X-Hub-Signature-256', '')

        if not signature_header.startswith('sha256='):
            return False

        signature = signature_header[7:]  # Quitar 'sha256='

        app_secret = request.env['ir.config_parameter'].sudo().get_param(
            'pragtech_whatsapp_messenger.whatsapp_app_secret'
        )

        if not app_secret:
            _logger.warning("whatsapp_app_secret no configurado - saltando validación")
            return True  # Permitir en desarrollo

        payload = request.httprequest.data
        expected_signature = hmac.new(
            app_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)
```

---

## Prioridad MEDIA (P2) - Planificar para Próximos Sprints

### P2-1: Integrar res.partner.chatbot con res.partner

**Problema:** Se creó un modelo separado en lugar de extender `res.partner`.

**Solución:**

```python
# Opción A: Migrar a res.partner con campo is_chatbot_contact

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_chatbot_contact = fields.Boolean('Es contacto de Chatbot', default=False)
    chatId = fields.Char('WhatsApp Chat ID', index=True)
    whatsapp_message_ids = fields.One2many(
        'whatsapp.messages', 'partner_id', string='Mensajes WhatsApp'
    )

# Migración de datos existentes
def migrate_chatbot_partners(env):
    chatbot_partners = env['res.partner.chatbot'].search([])
    for cp in chatbot_partners:
        existing = env['res.partner'].search([
            ('mobile', '=', cp.mobile)
        ], limit=1)

        if existing:
            existing.write({
                'is_chatbot_contact': True,
                'chatId': cp.chatId,
            })
        else:
            env['res.partner'].create({
                'name': cp.name,
                'mobile': cp.mobile,
                'chatId': cp.chatId,
                'is_chatbot_contact': True,
            })
```

---

### P2-2: Eliminar time.sleep() de Flujos

**Problema:** `time.sleep()` bloquea workers de Odoo.

**Solución - Usar colas o delayed jobs:**

```python
# Opción 1: Usar queue_job (OCA)
from odoo.addons.queue_job.job import job

@job
def send_delayed_message(env, numero, mensaje, delay_seconds):
    """Envía mensaje con delay usando queue_job."""
    env['whatsapp.messages'].send_whatsapp_message(numero, mensaje)

# En invoice_flow.py
def procesar_pago_transferencia(cls, numero):
    mensaje_transferencia = request.env['whatsapp_messages_user'].sudo().get_message('datos_transferencia')
    MetaAPi.enviar_mensaje_texto(numero, mensaje_transferencia)

    # En lugar de time.sleep(3):
    mensaje_comprobante = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_pago')
    send_delayed_message.delay(request.env, numero, mensaje_comprobante, delay_seconds=3)
```

```python
# Opción 2: Usar ir.cron programado (más simple)
def procesar_pago_transferencia(cls, numero):
    mensaje_transferencia = request.env['whatsapp_messages_user'].sudo().get_message('datos_transferencia')
    MetaAPi.enviar_mensaje_texto(numero, mensaje_transferencia)

    # Programar mensaje para 3 segundos después
    mensaje_comprobante = request.env['whatsapp_messages_user'].sudo().get_message('comprobante_pago')
    request.env['whatsapp.scheduled.message'].sudo().create({
        'numero': numero,
        'mensaje': mensaje_comprobante,
        'send_at': fields.Datetime.now() + timedelta(seconds=3),
    })
```

---

### P2-3: Agregar Índices para Performance

**Solución:**

```python
# pragtech_whatsapp_base/models/whatsapp_messages.py
class WhatsappMessages(models.Model):
    _name = 'whatsapp.messages'

    chatId = fields.Char(readonly=True, index=True)  # Ya tiene index
    time = fields.Datetime(readonly=True, index=True)  # AGREGAR index
    partner_id = fields.Many2one('res.partner.chatbot', index=True)  # AGREGAR index
    state = fields.Selection([...], index=True)  # AGREGAR index

    # Índice compuesto para búsquedas frecuentes
    _sql_constraints = []

    def init(self):
        # Crear índice compuesto
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS whatsapp_messages_chat_time_idx
            ON whatsapp_messages (chatId, time DESC)
        """)

# pragtech_whatsapp_base/models/whatsapp_chatbot.py
class WhatsappChatbot(models.Model):
    _name = 'whatsapp.chatbot'

    number = fields.Char(required=True, index=True)  # Ya tiene implícito
    state = fields.Char(required=True, index=True)  # AGREGAR index
    last_activity = fields.Datetime(index=True)  # AGREGAR index
```

---

### P2-4: Reemplazar print() con _logger

**Solución - Script de migración:**

```bash
# Ejecutar en terminal
cd /home/user/odoo-17-community/addons

# Buscar todos los print statements
grep -rn "print(" pragtech_whatsapp_base/ --include="*.py" | grep -v "_logger"

# Reemplazar automáticamente (con cuidado):
find pragtech_whatsapp_base -name "*.py" -exec sed -i \
    's/print(f"/\_logger.info(f"/g' {} \;
```

**Patrón a seguir:**

```python
# ANTES
print(f"Error al guardar en Odoo: {e}")

# DESPUÉS
_logger.error("Error al guardar en Odoo: %s", e)

# ANTES
print(f"Mensaje enviado a {numero}")

# DESPUÉS
_logger.info("Mensaje enviado a %s", numero)
```

---

## Prioridad BAJA (P3) - Nice to Have

### P3-1: Internacionalización (i18n)

Mover mensajes hardcodeados a archivos `.po`:

```python
# ANTES
mensaje = "Por favor, ingresa un número válido."

# DESPUÉS
from odoo import _
mensaje = _("Por favor, ingresa un número válido.")
```

### P3-2: Agregar Tests Unitarios

```python
# pragtech_whatsapp_base/tests/test_conversation_flow.py
from odoo.tests.common import TransactionCase

class TestConversationFlow(TransactionCase):

    def setUp(self):
        super().setUp()
        self.chatbot = self.env['whatsapp.chatbot'].create({
            'number': '593999999999',
            'state': 'menu_principal',
            'privacy_polic': True,
        })

    def test_menu_navigation(self):
        """Test que la navegación del menú funciona correctamente."""
        # Simular selección de opción
        # Verificar cambio de estado
        pass

    def test_product_search(self):
        """Test búsqueda de productos."""
        pass

    def test_order_creation(self):
        """Test creación de orden desde chatbot."""
        pass
```

### P3-3: Documentar API con OpenAPI/Swagger

Agregar documentación automática para endpoints públicos.

---

## Plan de Implementación Sugerido

### Sprint 1 (Crítico - 2 semanas)
- [ ] P0-1: Declarar dependencias
- [ ] P0-2: Asegurar endpoints
- [ ] P0-3: Eliminar warehouse hardcodeado
- [ ] P1-4: Validación webhook Meta

### Sprint 2 (Alto - 2 semanas)
- [ ] P1-1: Mover modelos de controllers
- [ ] P1-2: Corregir bug timezone
- [ ] P0-4 (Fase 1): Campos relacionales en chatbot

### Sprint 3 (Medio - 2 semanas)
- [ ] P2-3: Agregar índices
- [ ] P2-4: Migrar print a _logger
- [ ] P2-2: Eliminar time.sleep()

### Sprint 4+ (Refactorización mayor)
- [ ] P1-3: Separar módulos (por fases)
- [ ] P2-1: Integrar res.partner.chatbot
- [ ] P0-4 (Fase 2): Migración completa de JSON

---

## Métricas de Éxito

| Métrica | Antes | Objetivo |
|---------|-------|----------|
| Dependencias no declaradas | 2 | 0 |
| Endpoints sin auth | 3+ | 0 |
| Valores hardcodeados críticos | 3+ | 0 |
| Archivos con print() | 10+ | 0 |
| Cobertura de tests | 0% | >60% |
| Modelos en controllers | 1 | 0 |

---

## Riesgos de No Implementar

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Instalación falla en nuevo entorno | Alta | Alto | P0-1, P0-3 |
| Vulnerabilidad de seguridad | Media | Crítico | P0-2, P1-4 |
| Pérdida de datos de sesión | Media | Alto | P0-4 |
| Degradación de performance | Alta | Medio | P2-2, P2-3 |
| Dificultad de onboarding | Alta | Medio | P1-3, P3-2 |

---

*Documento de propuestas generado como parte de auditoría técnica.*
