from odoo import http
from odoo.http import request
import hmac
import hashlib
import json
import logging
from datetime import datetime
import time
import qrcode
import base64
from io import BytesIO

_logger = logging.getLogger(__name__)


class AhoritaPaymentController(http.Controller):

    @http.route('/ahorita/payment/request', type='json', auth='public', csrf=False)
    def request_payment_link(self, userId, amount, phone):
        try:
            transaction_id = f"generateByTransactionGW_{int(time.time() * 1000)}"
            message_id = f"PK Factura {int(time.time() * 1000)}"

            deeplink = request.env['payment.ahorita'].sudo().generateDeeplink(
                userId=userId,
                messageId=message_id,
                transactionId=transaction_id,
                deviceId="127.0.0.1",
                amount=amount
            )

            return {
                "deeplink": deeplink,
                "transactionId": transaction_id
            }
        except Exception as e:
            return {"error": str(e)}

    @http.route('/ahorita/payment/status', type='json', auth='public', methods=['POST'], csrf=False)
    def ahorita_payment_status(self, **kwargs):
        try:
            deeplink_id = kwargs.get('deeplink_id', '').strip()

            if not deeplink_id:
                return {'status': 'error', 'message': 'transaction_id no proporcionado'}

            record = request.env['ahorita.post'].sudo().search([
                ('deeplink', '=', deeplink_id)
            ], limit=1, order='create_date DESC')

            if not record:
                return {'status': 'error', 'message': 'Transacción no encontrada'}

            data = record.data or {}
            if isinstance(data, str):
                import json
                try:
                    data = json.loads(data)
                except Exception as e:
                    _logger.error("Error al parsear JSON de record.data: %s", str(e))
                    data = {}

            return {
                'status': record.status_payment or 'desconocido',
                'transactionId': record.transactionId,
                'transactionDate': data.get('transactionDate'),
                'amount': data.get('amount'),
                'currency': data.get('currency'),
                'sender': data.get('sender', {}),
                'receiver': data.get('receiver', {}),
                'metadata': data.get('metadata', {})
            }

        except Exception as e:
            _logger.error("Error en ahorita_payment_status: %s", str(e))
            return {'status': 'error', 'message': str(e)}

    @http.route('/ahorita/create_record', type='json', auth='public', methods=['POST'], csrf=False)
    def create_ahorita_record(self, **kwargs):
        order_id_name = kwargs.get('order_id')
        transaction_id = kwargs.get('transactionId')
        deeplink_id = kwargs.get('deeplink_id')

        try:
            record = request.env['ahorita.post'].sudo().create({
                'order_id_name': order_id_name,
                'transactionId': transaction_id,
                'deeplink': deeplink_id
            })
            return {"error": False, "record_id": record.id}
        except Exception as e:
            return {"error": True, "message": str(e)}


class AhoritaWebhookController(http.Controller):

    @http.route('/api/webhook/receive', type='json', auth='public', methods=['POST'], csrf=False)
    def receive_webhook(self, **kwargs):

        raw_data = request.httprequest.data

        try:
            try:
                data_json = json.loads(raw_data.decode('utf-8'))

            except Exception as e:
                _logger.error("Error al decodificar JSON: %s", str(e))
                _logger.info("Contenido problemático: %s", raw_data)
                return {
                    'status': 'error',
                    'message': 'JSON inválido',
                    'error_details': str(e)
                }, 400

            # Validar firma HMAC
            signature_header = request.httprequest.headers.get('Signature')
            if not signature_header:
                _logger.error("Encabezado 'Signature' no encontrado")
                return {
                    'status': 'error',
                    'message': 'Firma no proporcionada'
                }, 401

            received_signature = signature_header.split('sha256=')[-1].strip()
            secret_key = request.env['ir.config_parameter'].sudo().get_param('ahorita_webhook_secret')

            if not secret_key:
                _logger.error("Clave secreta no configurada")
                return {
                    'status': 'error',
                    'message': 'Configuración incompleta'
                }, 500

            computed_signature = hmac.new(
                secret_key.encode('utf-8'),
                msg=raw_data,
                digestmod=hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(computed_signature, received_signature):
                _logger.error("Firma HMAC no coincide")
                _logger.info("Esperado: %s | Recibido: %s", computed_signature, received_signature)
                return {
                    'status': 'error',
                    'message': 'Firma no válida'
                }, 401

            # Validar campos obligatorios
            required_fields = ['event', 'transactionDate', 'transactionId', 'amount',
                               'currency', 'sender', 'receiver']
            missing_fields = [f for f in required_fields if f not in data_json]
            if missing_fields:
                _logger.error("Campos obligatorios faltantes: %s", missing_fields)
                return {
                    'status': 'error',
                    'message': f'Campos faltantes: {", ".join(missing_fields)}'
                }, 400

            # Preparar datos para guardar
            try:
                safe_data = {
                    'event': str(data_json.get('event', 'unknown')),
                    'transactionId': str(data_json.get('transactionId', '')),
                    'amount': float(data_json.get('amount', 0)),
                    'currency': str(data_json.get('currency', '')),
                    'transactionDate': str(data_json.get('transactionDate', '')),
                    'sender': dict(data_json.get('sender', {})),
                    'receiver': dict(data_json.get('receiver', {})),
                    'metadata': dict(data_json.get('metadata', {}))
                }

            except Exception as e:
                _logger.error("Error al preparar datos: %s", str(e))
                return {
                    'status': 'error',
                    'message': 'Error en formato de datos'
                }, 400

            try:
                unique_deeplink_id = safe_data.get('metadata', {}).get('uniqueDeepLinkId', '')

                if not unique_deeplink_id:
                    _logger.error("uniqueDeepLinkId no encontrado en metadata")
                    return {
                        'status': 'error',
                        'message': 'El campo uniqueDeepLinkId es obligatorio para actualizar el registro.'
                    }, 400

                record = request.env['ahorita.post'].sudo().search([
                    ('deeplink', '=', unique_deeplink_id)
                ], limit=1)

                if record:
                    record.write({
                        'data': safe_data,
                        'status_payment': safe_data['event'],
                    })
                    action = 'updated'
                else:
                    record = request.env['ahorita.post'].sudo().create({
                        'transactionId': safe_data['transactionId'],
                        'data': safe_data,
                        'status_payment': safe_data['event'],
                        'deeplink': unique_deeplink_id,
                    })
                    action = 'created'

                return {
                    'status': 'success',
                    'action': action,
                    'id': record.id,
                    'payment_status': record.status_payment,
                    'data_type': str(type(record.data)),
                    'data_sample': dict(list(record.data.items())[:3]) if record.data else {}
                }

            except Exception as e:
                _logger.error("Error al crear registro: %s", str(e))
                return {
                    'status': 'error',
                    'message': 'Error al guardar datos',
                    'error_details': str(e)
                }, 500

        except Exception as e:
            _logger.error("Error general en webhook: %s", str(e))
            return {
                'status': 'error',
                'message': 'Error interno del servidor'
            }, 500
