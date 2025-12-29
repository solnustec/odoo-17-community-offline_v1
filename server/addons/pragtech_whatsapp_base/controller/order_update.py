import pytz
import hmac
import hashlib
import logging
from odoo import http
from odoo.http import request, Response
import json
from datetime import datetime

_logger = logging.getLogger(__name__)


class OrderUpdate(http.Controller):

    def _validate_signature(self, payload, signature):
        """Valida la firma HMAC del payload."""
        secret = request.env['ir.config_parameter'].sudo().get_param(
            'chatbot.api.secret', ''
        )

        if not secret:
            # Si no hay secreto configurado, verificar si estamos en modo desarrollo
            allow_unsigned = request.env['ir.config_parameter'].sudo().get_param(
                'chatbot.api.allow_unsigned', 'False'
            )
            if allow_unsigned.lower() == 'true':
                _logger.warning("API de orden pagada usada sin firma (modo desarrollo)")
                return True
            _logger.error("chatbot.api.secret no configurado y modo desarrollo desactivado")
            return False

        if not signature:
            return False

        # Calcular firma esperada
        if isinstance(payload, str):
            payload = payload.encode('utf-8')

        expected = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    @http.route('/api/store/order/mark_paid/chatbot', type='http', auth='public',
                methods=['POST'], csrf=False, cors="*")
    def mark_order_paid_chatbot(self, **kwargs):
        # Validar firma HMAC
        signature = request.httprequest.headers.get('X-Signature', '')
        if not self._validate_signature(request.httprequest.data, signature):
            _logger.warning("Intento de acceso no autorizado a mark_paid endpoint")
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "Firma inválida o no proporcionada"
                }),
                status=401,
                content_type='application/json'
            )

        data = json.loads(request.httprequest.data.decode('utf-8'))
        order_id = data.get('order_id')
        amount = float(data.get('amount', 0.0))
        payment_data = data.get('payment_data', {})

        order = request.env['sale.order'].sudo().browse(order_id)
        order.action_confirm()
        partner_id = order.partner_invoice_id.id
        partner = request.env['res.partner'].sudo().browse(partner_id)
        partner.sudo().write({
            'country_id': 63,  # Ecuador
        })

        # Generar factura
        invoice_id = order._create_invoices()

        # Crear factura en modo borrador
        sri_payment_method = request.env[
            'l10n_ec.sri.payment'].sudo().search(
            [('code', '=', 20)], limit=1).id

        # Configurar zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        # Obtener la fecha actual en Ecuador
        invoice_date = datetime.now(ecuador_tz).date()
        update_vals = {
            'invoice_date': invoice_date,  # Fecha contable
            'l10n_ec_sri_payment_id': sri_payment_method,
        }
        invoice_id.sudo().write(update_vals)

        invoice_id.action_post()  # Validar la factura

        payment_provider_id = request.env['payment.provider'].sudo().search(
            [('name', '=', 'Paymentez')], limit=1)

        payment_method_id = request.env['payment.method'].sudo().search(
            [('code', '=', 'card'), ('active', '=', True)],
            limit=1).id

        payment_method_line = request.env[
            'account.payment.method.line'].sudo().search([
            ('journal_id', '=', payment_provider_id.journal_id.id),
            ('name', '=', 'Paymentez'),
        ], limit=1)

        payment_register = request.env[
            'account.payment.register'].with_context(
            active_model='account.move',
            active_ids=[invoice_id.id]
        ).sudo().create({
            'amount': amount,
            'payment_date': invoice_date,
            'journal_id': payment_provider_id.journal_id.id,
            'payment_method_line_id': payment_method_line.id,  # Método de pago
            'partner_id': order.partner_id.id,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'communication': invoice_id.name,  # Referencia de la factura
        })
        # Crear y validar el pago
        payment = payment_register._create_payments()

        # Crear transacción de pago
        request.env['payment.transaction'].sudo().create(
            {
                'amount': amount,
                'currency_id': order.currency_id.id,
                'payment_id': payment.id,
                'partner_id': order.partner_id.id,
                'payment_method_id': payment_method_id,
                'reference': order.name,
                'sale_order_ids': [(6, 0, [order.id])],
                'provider_id': payment_provider_id.id,
                "payment_json_data": json.dumps(payment_data),
                'state': 'done',
            })

        # Generar el access_token si no existe
        if not order.access_token:
            order._portal_ensure_token()

        # Construir la URL del PDF de la orden
        base_url = request.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', 'http://localhost:8069')
        pdf_url = f"{base_url}/my/orders/{order.id}?access_token={order.access_token}&report_type=pdf"
        # loyalty_program = request.env['loyalty.program'].sudo().search([],limit=1)
        # Opcional: Generar el PDF en base64 como respaldo
        # points = 0

        # if loyalty_program and hasattr(loyalty_program, 'compute_points'):
        #     points = loyalty_program.compute_points(order.amount_total)
        #     order.partner_id.loyalty_points += points

        try:
            jwt_data = getattr(request, '_jwt_data', {})
            user_id = jwt_data.get('user_id')
            request.env['user.notification'].sudo().create({
                'name': 'Orden Completada',
                'user_id': user_id,
                'message': f"Tu orden {order.name} ha sido pagada.",
            })
            request.env['user.notification'].sudo().create({
                'name': 'Puntos de Recompensa',
                'user_id': user_id,
                'message': f"Se te han asignado  puntos de recompensa.",
            })
            # enviar notificacion Firebase

            device = request.env['push.device'].find_by_user(user_id)
            request.env['firebase.service'].send_push_notification(
                registration_token=device.register_id,
                title="Orden Completada",
                body="Felicitaciones, Tu orden ha sido completada"
            )

        except Exception as e:
            print(e)
            pass

        return Response(
            json.dumps({
                "status": "success",
                "message": "Order pagada y puntos de recompensa asignados",
                "data": [
                    {
                        'order_id': order.id,
                        'points_awarded': 1,
                        'pdf_url': pdf_url
                    }
                ]
            }),
            status=200,
            content_type='application/json'
        )