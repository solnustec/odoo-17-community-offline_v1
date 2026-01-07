# -*- coding: utf-8 -*-
"""
Webhook Receiver Controller

Recibe webhooks de APIs externas y los almacena para que las sucursales
OFFLINE puedan consultarlos posteriormente.
"""
import json
import logging
import hmac
import hashlib
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WebhookReceiverController(http.Controller):

    def _validate_signature(self, api_code, raw_data, signature_header):
        """Valida la firma HMAC del webhook."""
        config = request.env['api.gateway.config'].sudo().search([
            ('code', '=', api_code),
            ('webhook_enabled', '=', True),
        ], limit=1)

        if not config or not config.webhook_secret:
            return False, 'Configuración de webhook no encontrada'

        # Extraer firma del header
        if not signature_header:
            return False, 'Header de firma no proporcionado'

        # Soportar diferentes formatos de firma
        if '=' in signature_header:
            received_signature = signature_header.split('=')[-1].strip()
        else:
            received_signature = signature_header.strip()

        # Calcular firma esperada
        computed_signature = hmac.new(
            config.webhook_secret.encode('utf-8'),
            msg=raw_data,
            digestmod=hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed_signature, received_signature):
            return False, 'Firma no válida'

        return True, None

    def _extract_transaction_id(self, api_code, data):
        """Extrae el ID de transacción según la API."""
        if api_code == 'ahorita':
            # Ahorita usa transactionId o metadata.uniqueDeepLinkId
            tid = data.get('transactionId')
            if not tid:
                metadata = data.get('metadata', {})
                tid = metadata.get('uniqueDeepLinkId')
            return tid

        elif api_code == 'deuna':
            return data.get('transactionId') or data.get('idTransacionReference')

        # Genérico
        return data.get('transactionId') or data.get('transaction_id') or data.get('id')

    def _extract_order_reference(self, api_code, data):
        """Extrae la referencia de orden si existe."""
        if api_code == 'ahorita':
            metadata = data.get('metadata', {})
            return metadata.get('orderReference') or metadata.get('messageId')

        return data.get('orderReference') or data.get('order_id')

    # ==================== WEBHOOK GENÉRICO ====================

    @http.route('/api_gateway/webhook/<string:api_code>', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def receive_webhook_generic(self, api_code, **kwargs):
        """
        Endpoint genérico para recibir webhooks de cualquier API configurada.

        URL: /api_gateway/webhook/{api_code}
        Ejemplo: /api_gateway/webhook/ahorita
        """
        try:
            raw_data = request.httprequest.data
            source_ip = request.httprequest.remote_addr

            # Parsear JSON
            try:
                data = json.loads(raw_data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                _logger.error(f'[Webhook {api_code}] Error parseando JSON: {e}')
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'JSON inválido'}),
                    headers=[('Content-Type', 'application/json')],
                    status=400
                )

            # Validar firma si está configurado
            signature_header = request.httprequest.headers.get('Signature') or \
                               request.httprequest.headers.get('X-Signature') or \
                               request.httprequest.headers.get('X-Hub-Signature-256')

            if signature_header:
                valid, error = self._validate_signature(api_code, raw_data, signature_header)
                if not valid:
                    _logger.warning(f'[Webhook {api_code}] Firma inválida: {error}')
                    return request.make_response(
                        json.dumps({'status': 'error', 'message': error}),
                        headers=[('Content-Type', 'application/json')],
                        status=401
                    )

            # Extraer datos
            transaction_id = self._extract_transaction_id(api_code, data)
            if not transaction_id:
                _logger.warning(f'[Webhook {api_code}] Sin transaction_id en: {data}')
                # Generar un ID basado en timestamp si no hay uno
                import time
                transaction_id = f"webhook_{int(time.time() * 1000)}"

            event_type = data.get('event') or data.get('eventType') or data.get('status') or 'unknown'
            order_reference = self._extract_order_reference(api_code, data)

            # Crear/actualizar webhook
            webhook = request.env['api.gateway.webhook'].sudo().create_webhook(
                api_code=api_code,
                transaction_id=transaction_id,
                event_type=event_type,
                payload=data,
                headers=dict(request.httprequest.headers),
                order_reference=order_reference,
                source_ip=source_ip,
            )

            # Log
            request.env['api.gateway.log'].sudo().log_request(
                api_code=api_code,
                method='POST',
                endpoint=f'/webhook/{api_code}',
                url=request.httprequest.url,
                headers=dict(request.httprequest.headers),
                body=data,
                response_status=200,
                response_headers={},
                response_body={'status': 'success'},
                response_time=0,
                source_ip=source_ip,
                transaction_type='webhook',
            )

            _logger.info(f'[Webhook {api_code}] Recibido: {transaction_id} - {event_type}')

            return request.make_response(
                json.dumps({
                    'status': 'success',
                    'webhook_id': webhook.id,
                    'transaction_id': transaction_id,
                }),
                headers=[('Content-Type', 'application/json')],
                status=200
            )

        except Exception as e:
            _logger.error(f'[Webhook {api_code}] Error: {str(e)}')
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(e)}),
                headers=[('Content-Type', 'application/json')],
                status=500
            )

    # ==================== WEBHOOK AHORITA (compatibilidad) ====================

    @http.route('/api_gateway/webhook/ahorita/receive', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def receive_ahorita_webhook(self, **kwargs):
        """Endpoint específico para Ahorita (compatibilidad con configuración existente)."""
        return self.receive_webhook_generic('ahorita', **kwargs)

    # ==================== WEBHOOK DEUNA (compatibilidad) ====================

    @http.route('/api_gateway/webhook/deuna/receive', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def receive_deuna_webhook(self, **kwargs):
        """Endpoint específico para Deuna (compatibilidad con configuración existente)."""
        return self.receive_webhook_generic('deuna', **kwargs)
