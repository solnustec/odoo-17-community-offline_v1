from odoo.http import request
from ..templates.meta_api import MetaAPi
import json
import requests
import logging
from datetime import timedelta, datetime
import pytz
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class WhatsappChatbot(models.Model):
    _name = "whatsapp.chatbot"
    _description = 'Whatsapp Instance'

    number = fields.Char(string="Whatsapp Number", required=True)
    state = fields.Char(string="Whatsapp State", required=True)
    orden = fields.Char(string="Whatsapp Orden")
    last_activity = fields.Datetime(string="Last Activity", default=fields.Datetime.now)
    privacy_polic = fields.Boolean(string="Privacy Policy Accepted", default=False)
    inactivity_notified = fields.Boolean(
        string="Inactivity Notified",
        default=False,
        help="Flag para evitar envío múltiple de mensajes de inactividad"
    )


    PAYMENT_COLORS = {
        'cotizar-receta': '#dc3545',
        'confirmar_pago': '#28a745',
    }

    pinned = fields.Boolean(string="Fijado", default=False, index=True)
    pin_sequence = fields.Integer(string="Orden de fijado", default=10)

    @api.model
    def toggle_pin(self, chat_id):
        record = self.search([('number', '=', chat_id)], limit=1)
        if record:
            record.sudo().write({'pinned': not record.pinned})
            return {'chatId': record.number, 'pinned': record.pinned}
        return False

    @api.model
    def set_custom_name(self, chat_id, display_name):
        display_name = (display_name or "").strip()
        rec = self.env["whatsapp.contact"].sudo().search([("chat_id", "=", chat_id)], limit=1)
        if rec:
            rec.sudo().write({"custom_name": display_name})
        else:
            rec = self.env["whatsapp.contact"].sudo().create({"chat_id": chat_id, "custom_name": display_name})
        return {"chatId": chat_id, "displayName": rec.custom_name}

    def _get_local_now(self):
        """Obtiene la hora local actual (America/Guayaquil) como datetime naive"""
        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)
        return now_local.replace(tzinfo=None)

    def create(self, vals):
        vals['last_activity'] = self._get_local_now()
        vals['inactivity_notified'] = False
        return super().create(vals)

    def write(self, vals):
        # Si hay cambio de estado a un estado activo (no cerrado),
        # resetear el flag de notificación de inactividad
        closed_states = ['salir', 'salir_conversacion', 'cerrar_chat','canceled']
        if 'state' in vals and vals['state'] not in closed_states:
            vals['inactivity_notified'] = False

        if 'last_activity' not in vals:
            vals['last_activity'] = self._get_local_now()
        else:
            la = vals['last_activity']
            if isinstance(la, str):
                la = fields.Datetime.from_string(la)
            elif isinstance(la, datetime) and la.tzinfo:
                # Convertir a hora local si tiene timezone
                user_tz = pytz.timezone('America/Guayaquil')
                la = la.astimezone(user_tz).replace(tzinfo=None)
            vals['last_activity'] = la
        return super().write(vals)

    def _get_local_time(self):
        user_tz = pytz.timezone('America/Guayaquil')
        now_utc_aware = datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local_aware = now_utc_aware.astimezone(user_tz)
        _ = now_local_aware.strftime('%Y-%m-%d %H:%M:%S')
        return now_utc_aware.replace(tzinfo=None)

    @classmethod
    def update_orden_pay_paymentez(cls, transaction_data):
        try:
            transaction_id = transaction_data.get('id')
            dev_reference = transaction_data.get('dev_reference')
            status = transaction_data.get('status')
            amount = float(transaction_data.get('amount', 0.0))

            sale_order = request.env['sale.order'].sudo().search([
                ('transaction_id', '=', transaction_id),
                ('dev_reference', '=', dev_reference)], limit=1)

            if not sale_order:
                _logger.error(
                    f"No se encontró orden con transaction_id={transaction_id} y dev_reference={dev_reference}")
                return False

            if status == '1':
                payload = {
                    'order_id': sale_order.id,
                    'amount': amount,
                }

                base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                api_url = f"{base_url}/api/store/order/mark_paid"
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f"Bearer {request.env['ir.config_parameter'].sudo().get_param('app_mobile_api_secret_key')}",
                }

                response = requests.post(api_url, json=payload, headers=headers)

                response_data = response.json()
                result = response_data.get('result', {})

                if response.status_code == 200 and result.get('success'):
                    so = request.env['sale.order'].sudo().browse(sale_order.id)
                    if so.exists() and so.state in ('draft', 'sent'):
                        so.action_confirm()
                else:
                    _logger.warning(f"⚠️ Fallo al marcar como pagada: {result}")
                    return False
            elif status == '2':
                _logger.info(f"El pago fue cancelado para la orden {sale_order.name}.")
            else:
                _logger.warning(f"Estado de transacción desconocido: {status} para la orden {sale_order.name}")

            return True

        except Exception as e:
            _logger.exception(f"Error al actualizar orden por pago de tarjeta: {str(e)}")
            return False

    @api.model
    def get_chat_state(self, chat_id):
        record = self.sudo().search([('number', '=', chat_id)], limit=1)
        if record:
            return {'chatId': record.number, 'state': record.state}
        return {'chatId': chat_id, 'state': ''}

    @api.model
    def get_orders_by_chat_id(self, chat_id):
        records = self.sudo().search([('number', '=', chat_id)])
        orders = []
        for record in records:
            try:
                orden_data = json.loads(record.orden)
                tipo_pago = orden_data.get('tipo_pago', '').lower()
                sale_order_id = orden_data.get('sale_order_id')
                sale_order = None
                if sale_order_id:
                    sale_order = self.env['sale.order'].sudo().browse(sale_order_id)

                if sale_order and sale_order.exists():
                    order_state = sale_order.state.lower()
                else:
                    order_state = record.state.lower()

                if order_state == 'cotizar-receta':
                    color_pago = self.PAYMENT_COLORS.get('cotizar-receta', '#dc3545')
                else:
                    color_pago = self.PAYMENT_COLORS.get(tipo_pago, '#6c757d')

                if sale_order and sale_order.exists():
                    order_items = []
                    for line in sale_order.order_line:
                        order_items.append({
                            'id': line.product_id.id,
                            'name': line.product_id.name,
                            'quantity': line.product_uom_qty,
                            'price': line.price_unit,
                            'subtotal': line.price_subtotal
                        })

                    orders.append({
                        'id': record.id,
                        'chatId': record.number,
                        'state': sale_order.state,
                        'items': order_items,
                        'tipo_envio': orden_data.get('tipo_envio', ''),
                        'tipo_pago': orden_data.get('tipo_pago', ''),
                        'color_pago': color_pago,
                        'nombres_completo': sale_order.partner_id.name,
                        'number': sale_order.x_numero_chatbot,
                        'direccion_url': sale_order.ubication_url,
                        'documento': sale_order.partner_id.vat or '',
                        'email': sale_order.partner_id.email or '',
                        'direccion_factura': sale_order.partner_id.street or '',
                        'total': sale_order.amount_total,
                        'subtotal': sale_order.amount_untaxed,
                        'tax': sale_order.amount_tax,
                        'sale_order_id': sale_order_id,
                        'sale_order_name': sale_order.name
                    })
                    continue

                orders.append({
                    'id': record.id,
                    'chatId': record.number,
                    'state': record.state,
                    'items': orden_data.get('items', []),
                    'tipo_envio': orden_data.get('tipo_envio', ''),
                    'tipo_pago': orden_data.get('tipo_pago', ''),
                    'color_pago': color_pago,
                    'nombres_completo': orden_data.get('nombres_completo', ''),
                    'documento': orden_data.get('documento', ''),
                    'email': orden_data.get('email', ''),
                    'direccion_factura': orden_data.get('direccion_factura', ''),
                    'total': sum(item.get('subtotal', 0) for item in orden_data.get('items', []))
                })
            except json.JSONDecodeError:
                continue
        return orders

    @api.model
    def _cron_check_inactivity(self):
        """
        Cron job para verificar inactividad de sesiones de chatbot.
        - Cancela órdenes en estado 'to invoice' tras 40 minutos de inactividad
        - Cierra sesiones inactivas por más de 60 minutos
        - Cancela órdenes asociadas si no han sido facturadas
        - Envía mensaje de despedida (solo una vez)
        """
        try:
            user_tz = pytz.timezone('America/Guayaquil')
            now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
            now_local = now_utc.astimezone(user_tz)

            sessions = self.sudo().search([
                ('state', 'not in', ['salir', 'salir_conversacion', 'cerrar_chat', 'finalizar']),
            ])

            # Guardar IDs para evitar "object unbound" durante iteración
            session_ids = sessions.ids

            for session_id in session_ids:
                try:
                    # Obtener sesión fresca en cada iteración
                    session = self.sudo().browse(session_id)
                    if not session.exists():
                        continue

                    if not session.last_activity:
                        continue

                    tiempo_transcurrido = now_local.replace(tzinfo=None) - session.last_activity

                    # Obtener datos de la orden asociada
                    order_data = json.loads(session.orden) if session.orden else {}
                    sale_order_id = order_data.get("sale_order_id", 0)
                    sale_order = None

                    if sale_order_id:
                        sale_order = self.env['sale.order'].sudo().browse(sale_order_id)
                        if not sale_order.exists():
                            sale_order = None

                    # ===== CASO ESPECIAL: Órdenes 'to invoice' - 40 minutos =====
                    if sale_order and sale_order.invoice_status == 'to invoice':
                        if tiempo_transcurrido >= timedelta(minutes=40):
                            self._cancel_sale_order_safely(sale_order, session)

                            mensaje = (
                                "Tu orden ha sido cancelada por inactividad. "
                                "Si deseas continuar, por favor inicia una nueva conversación."
                            )
                            MetaAPi.enviar_mensaje_texto(session.number, mensaje, env=self.env)

                            session.sudo().write({
                                'state': 'cerrar_chat',
                                'orden': '',
                                'inactivity_notified': True,
                                'last_activity': now_local.replace(tzinfo=None)
                            })
                        continue

                    # ===== FLUJO NORMAL: 60+ minutos de inactividad =====
                    if tiempo_transcurrido < timedelta(minutes=60):
                        continue

                    # Cancelar orden si existe y está en ventana 60-120 min
                    if tiempo_transcurrido <= timedelta(minutes=120):
                        if sale_order and sale_order.invoice_status != 'invoiced':
                            self._cancel_sale_order_safely(sale_order, session)

                        # Enviar mensaje SOLO si no fue notificada antes
                        if not session.inactivity_notified:
                            mensaje = (
                                "Notamos que no has tenido actividad en los últimos "
                                "60 minutos, así que el chat se ha cerrado automáticamente. "
                                "¡Gracias por visitarnos! 👋"
                            )
                            MetaAPi.enviar_mensaje_texto(session.number, mensaje, env=self.env)

                    # SIEMPRE cerrar la sesión
                    session.sudo().write({
                        'state': 'cerrar_chat',
                        'orden': '',
                        'inactivity_notified': True,
                        'last_activity': now_local.replace(tzinfo=None)
                    })

                except Exception as e:
                    _logger.error(f"Error al procesar la sesión {session_id}: {str(e)}")

        except Exception as e:
            _logger.error(f"Error general en cron_check_inactivity: {str(e)}")


    def _cancel_sale_order_safely(self, sale_order, session):
        """
        Cancela una orden de venta de forma segura, manejando todos los estados posibles.

        Maneja correctamente:
        - Órdenes en estado 'draft' o 'sent': cancela directamente
        - Órdenes en estado 'sale' con invoice_status='to invoice':
          primero revierte a draft, luego cancela
        - Pickings y facturas asociadas
        """
        try:

            # 1. Cancelar pickings (entregas) pendientes
            for picking in sale_order.picking_ids:
                if picking.state not in ('cancel', 'done'):
                    try:
                        picking.action_cancel()
                    except Exception as e:
                        _logger.warning(f"No se pudo cancelar picking {picking.name}: {str(e)}")

            # 2. Cancelar facturas en borrador
            for invoice in sale_order.invoice_ids:
                if invoice.state == 'draft':
                    try:
                        invoice.button_cancel()
                    except Exception as e:
                        _logger.warning(f"No se pudo cancelar factura {invoice.name}: {str(e)}")

            # 3. Si la orden está confirmada (sale) y tiene estado 'to invoice',
            #    necesitamos revertirla a borrador primero
            if sale_order.state == 'sale':
                # Verificar si tiene el método _action_cancel (Odoo 17)
                if hasattr(sale_order, '_action_cancel'):
                    sale_order._action_cancel()
                else:
                    # Intentar con action_cancel normal
                    # Si falla porque está en 'sale', intentar volver a draft
                    try:
                        sale_order.action_cancel()
                    except Exception as cancel_error:
                        _logger.warning(f"action_cancel falló, intentando volver a draft: {str(cancel_error)}")
                        # Forzar el cambio a draft para poder cancelar
                        if hasattr(sale_order, 'action_draft'):
                            sale_order.action_draft()
                            sale_order.action_cancel()
                        else:
                            # Forzar el estado directamente (último recurso)
                            sale_order.write({'state': 'draft'})
                            sale_order.action_cancel()
            elif sale_order.state in ('draft', 'sent'):
                sale_order.action_cancel()

            # 4. Actualizar invoice_status si la orden fue cancelada
            sale_order._compute_invoice_status()
            if sale_order.state == 'cancel':
                sale_order.write({'invoice_status': 'no'})
                session.sudo().write({"state": "canceled"})

        except Exception as e:
            _logger.error(f"Error al cancelar la orden {sale_order.name}: {str(e)}")

class WhatsappContact(models.Model):
    _name = "whatsapp.contact"
    _description = "WhatsApp Contact"
    _rec_name = "custom_name"

    chat_id = fields.Char(required=True, index=True)
    custom_name = fields.Char()

    _sql_constraints = [
        ("chat_id_unique", "unique(chat_id)", "Ya existe un contacto con este chat_id."),
    ]








