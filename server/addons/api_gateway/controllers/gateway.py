# -*- coding: utf-8 -*-
"""
API Gateway Controller

Proxy que permite a las sucursales OFFLINE hacer requests a APIs externas
a través del servidor PRINCIPAL.

Endpoints:
- /api_gateway/proxy - Proxy genérico
- /api_gateway/ahorita/* - Proxy específico para Ahorita
- /api_gateway/deuna/* - Proxy específico para Deuna
- /api_gateway/webhooks/pending - Consultar webhooks pendientes
"""
import json
import logging
import time
import requests
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ApiGatewayController(http.Controller):

    def _validate_request(self, api_code, data):
        """Valida que el request sea válido y autorizado."""
        # Buscar configuración de la API
        config = request.env['api.gateway.config'].sudo().search([
            ('code', '=', api_code),
            ('active', '=', True),
        ], limit=1)

        if not config:
            return None, None, {'error': f'API "{api_code}" no configurada o inactiva'}

        # Validar API key del OFFLINE si es requerida
        branch = None
        if config.require_api_key:
            offline_key = data.get('api_key') or data.get('offline_api_key')
            if not offline_key:
                return None, None, {'error': 'API key del OFFLINE requerida'}

            # Validar la key contra las sucursales registradas
            branch = request.env['api.gateway.branch'].sudo().validate_api_key(offline_key)
            if not branch:
                return None, None, {'error': 'API key inválida o sucursal inactiva'}

            # Verificar si la sucursal tiene acceso a esta API
            if config.allowed_branch_ids and branch not in config.allowed_branch_ids:
                return None, None, {'error': 'Sucursal no autorizada para esta API'}

            # Actualizar info de conexión
            branch.update_connection_info(request.httprequest.remote_addr)

        return config, branch, None

    def _make_external_request(self, config, method, endpoint, payload=None, headers=None):
        """Hace el request a la API externa."""
        url = f"{config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        # Combinar headers de configuración con headers personalizados
        final_headers = config.get_headers()
        if headers:
            final_headers.update(headers)

        start_time = time.time()
        error_message = None
        response = None

        try:
            if method.upper() == 'GET':
                response = requests.get(
                    url,
                    headers=final_headers,
                    params=payload,
                    timeout=config.timeout,
                    verify=True
                )
            elif method.upper() == 'POST':
                response = requests.post(
                    url,
                    headers=final_headers,
                    json=payload,
                    timeout=config.timeout,
                    verify=True
                )
            elif method.upper() == 'PUT':
                response = requests.put(
                    url,
                    headers=final_headers,
                    json=payload,
                    timeout=config.timeout,
                    verify=True
                )
            elif method.upper() == 'DELETE':
                response = requests.delete(
                    url,
                    headers=final_headers,
                    timeout=config.timeout,
                    verify=True
                )
            else:
                return None, f'Método HTTP no soportado: {method}', 0

        except requests.exceptions.Timeout:
            error_message = f'Timeout después de {config.timeout}s'
        except requests.exceptions.ConnectionError as e:
            error_message = f'Error de conexión: {str(e)}'
        except Exception as e:
            error_message = f'Error inesperado: {str(e)}'

        elapsed_time = time.time() - start_time

        return response, error_message, elapsed_time

    def _log_transaction(self, config, method, endpoint, url, req_headers, req_body,
                         response, error_message, elapsed_time, source_ip):
        """Registra la transacción en el log."""
        try:
            request.env['api.gateway.log'].sudo().log_request(
                api_code=config.code if config else 'UNKNOWN',
                method=method,
                endpoint=endpoint,
                url=url,
                headers=req_headers,
                body=req_body,
                response_status=response.status_code if response else None,
                response_headers=dict(response.headers) if response else None,
                response_body=response.text if response else None,
                response_time=elapsed_time,
                source_ip=source_ip,
                error_message=error_message,
            )
        except Exception as e:
            _logger.error(f'[API Gateway] Error registrando log: {str(e)}')

    def _json_response(self, data, status=200):
        """Retorna una respuesta JSON estándar."""
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
            status=status
        )

    # ==================== PROXY GENÉRICO ====================

    @http.route('/api_gateway/proxy', type='json', auth='public', methods=['POST'], csrf=False, cors='*')
    def proxy_request(self, **kwargs):
        """
        Proxy genérico para cualquier API configurada.

        Payload esperado:
        {
            "api_code": "ahorita",
            "method": "POST",
            "endpoint": "/v1/payments",
            "payload": {...},
            "headers": {...},  // opcional
            "api_key": "xxx"   // API key del OFFLINE
        }
        """
        try:
            # Obtener datos del request
            data = kwargs
            if not data:
                raw = request.httprequest.data.decode('utf-8')
                data = json.loads(raw) if raw else {}

            api_code = data.get('api_code')
            method = data.get('method', 'POST')
            endpoint = data.get('endpoint', '')
            payload = data.get('payload', {})
            custom_headers = data.get('headers', {})

            if not api_code:
                return {'success': False, 'error': 'api_code es requerido'}

            # Validar request
            config, branch, error = self._validate_request(api_code, data)
            if error:
                return {'success': False, **error}

            # Verificar endpoint permitido
            if not config.is_endpoint_allowed(endpoint):
                return {'success': False, 'error': f'Endpoint "{endpoint}" no permitido'}

            # Hacer request externo
            source_ip = request.httprequest.remote_addr
            response, error_message, elapsed_time = self._make_external_request(
                config, method, endpoint, payload, custom_headers
            )

            # Registrar log
            url = f"{config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            self._log_transaction(
                config, method, endpoint, url, custom_headers, payload,
                response, error_message, elapsed_time, source_ip
            )

            if error_message:
                return {'success': False, 'error': error_message}

            # Parsear respuesta
            try:
                response_data = response.json()
            except (json.JSONDecodeError, ValueError):
                response_data = response.text

            return {
                'success': True,
                'status_code': response.status_code,
                'data': response_data,
                'elapsed_time': elapsed_time,
            }

        except Exception as e:
            _logger.error(f'[API Gateway] Error en proxy: {str(e)}')
            return {'success': False, 'error': str(e)}

    # ==================== AHORITA ENDPOINTS ====================

    @http.route('/api_gateway/ahorita/generate_deeplink', type='json', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def ahorita_generate_deeplink(self, **kwargs):
        """
        Proxy para generar deeplink de Ahorita.
        Usa el módulo payments_ahorita del PRINCIPAL.
        """
        try:
            data = kwargs
            if not data:
                raw = request.httprequest.data.decode('utf-8')
                data = json.loads(raw) if raw else {}

            # Obtener parámetros
            user_id = data.get('userId', 415472)
            message_id = data.get('messageId')
            transaction_id = data.get('transactionId')
            device_id = data.get('deviceId', '127.0.0.1')
            amount = data.get('amount', 0.0)

            # Llamar al modelo de Ahorita
            Payment = request.env['payment.payment'].sudo()
            deeplink = Payment.generateDeeplink(
                userId=user_id,
                messageId=message_id,
                transactionId=transaction_id,
                deviceId=device_id,
                amount=amount,
            )

            if not deeplink:
                return {'success': False, 'error': 'No se pudo generar el deeplink'}

            # Generar QR
            import qrcode
            import base64
            from io import BytesIO
            from qrcode.constants import ERROR_CORRECT_M

            qr_builder = qrcode.QRCode(
                version=None,
                error_correction=ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr_builder.add_data(deeplink)
            qr_builder.make(fit=True)
            img = qr_builder.make_image(fill_color="black", back_color="white")

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=95)
            qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            qr_data_url = f"data:image/jpeg;base64,{qr_base64}"

            return {
                'success': True,
                'deeplink': deeplink,
                'deeplink_id': deeplink.split('?')[-1] if '?' in deeplink else deeplink,
                'transactionId': transaction_id,
                'qr': qr_data_url,
            }

        except Exception as e:
            _logger.error(f'[API Gateway] Error en ahorita/generate_deeplink: {str(e)}')
            return {'success': False, 'error': str(e)}

    # ==================== DEUNA ENDPOINTS ====================

    @http.route('/api_gateway/deuna/payment/request', type='json', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def deuna_payment_request(self, **kwargs):
        """
        Proxy para solicitar pago Deuna.
        """
        try:
            data = kwargs
            if not data:
                raw = request.httprequest.data.decode('utf-8')
                data = json.loads(raw) if raw else {}

            amount = data.get('amount')
            point_of_sale_id = data.get('point_of_sale_id')
            qr_type = data.get('qr_type', 'dynamic')

            if not amount:
                return {'success': False, 'error': 'El campo "amount" es requerido'}

            # Obtener configuración de Deuna
            config = request.env['digital.payment.config'].sudo().search([
                ('bank_name', '=', 'DEUNA BCO PICHINCHA')
            ], limit=1)

            if not config:
                return {'success': False, 'error': 'Configuración de Deuna no encontrada'}

            # Construir request
            url = config.prod_request_payment_url if config.is_production else config.test_request_payment_url
            headers = {
                "Content-Type": "application/json",
                "x-api-key": config.prod_api_key if config.is_production else config.test_api_key,
                "x-api-secret": config.prod_api_secret if config.is_production else config.test_api_secret
            }
            payload = {
                "pointOfSale": point_of_sale_id,
                "qrType": qr_type,
                "amount": float(amount),
                "detail": "Pago realizado.",
                "internalTransactionReference": "Pago Digital App",
                "format": "2"
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response_data = response.json()

            return {
                'success': True,
                'data': response_data,
            }

        except Exception as e:
            _logger.error(f'[API Gateway] Error en deuna/payment/request: {str(e)}')
            return {'success': False, 'error': str(e)}

    @http.route('/api_gateway/deuna/payment/status', type='json', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def deuna_payment_status(self, **kwargs):
        """
        Proxy para consultar estado de pago Deuna.
        """
        try:
            data = kwargs
            if not data:
                raw = request.httprequest.data.decode('utf-8')
                data = json.loads(raw) if raw else {}

            transaction_id = data.get('transaction_id')

            if not transaction_id:
                return {'success': False, 'error': 'transaction_id es requerido'}

            # Obtener configuración
            config = request.env['digital.payment.config'].sudo().search([
                ('bank_name', '=', 'DEUNA BCO PICHINCHA')
            ], limit=1)

            if not config:
                return {'success': False, 'error': 'Configuración de Deuna no encontrada'}

            url = config.prod_payment_status_url if config.is_production else config.test_payment_status_url
            headers = {
                "Content-Type": "application/json",
                "x-api-key": config.prod_api_key if config.is_production else config.test_api_key,
                "x-api-secret": config.prod_api_secret if config.is_production else config.test_api_secret,
            }
            payload = {
                "idTransacionReference": transaction_id,
                "idType": "0",
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response_data = response.json()

            return {
                'success': True,
                'status': response_data.get('status', 'desconocido'),
                'data': response_data,
            }

        except Exception as e:
            _logger.error(f'[API Gateway] Error en deuna/payment/status: {str(e)}')
            return {'success': False, 'error': str(e)}

    # ==================== WEBHOOKS PENDIENTES ====================

    @http.route('/api_gateway/webhooks/pending', type='json', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def get_pending_webhooks(self, **kwargs):
        """
        Endpoint para que las sucursales OFFLINE consulten webhooks pendientes.

        Payload:
        {
            "api_code": "ahorita",
            "limit": 50,
            "api_key": "xxx"
        }
        """
        try:
            data = kwargs
            if not data:
                raw = request.httprequest.data.decode('utf-8')
                data = json.loads(raw) if raw else {}

            api_code = data.get('api_code')
            api_key = data.get('api_key')
            limit = data.get('limit', 100)

            if not api_code:
                return {'success': False, 'error': 'api_code es requerido'}

            # Validar API key y obtener sucursal
            branch = None
            if api_key:
                branch = request.env['api.gateway.branch'].sudo().validate_api_key(api_key)

            webhooks = request.env['api.gateway.webhook'].sudo().get_pending_webhooks(
                api_code=api_code,
                branch_id=branch.id if branch else None,
                limit=limit
            )

            return {
                'success': True,
                'count': len(webhooks),
                'webhooks': webhooks,
            }

        except Exception as e:
            _logger.error(f'[API Gateway] Error en webhooks/pending: {str(e)}')
            return {'success': False, 'error': str(e)}

    @http.route('/api_gateway/webhooks/mark_synced', type='json', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def mark_webhooks_synced(self, **kwargs):
        """
        Marca webhooks como sincronizados para una sucursal.

        Payload:
        {
            "webhook_ids": [1, 2, 3],
            "api_key": "xxx"
        }
        """
        try:
            data = kwargs
            if not data:
                raw = request.httprequest.data.decode('utf-8')
                data = json.loads(raw) if raw else {}

            webhook_ids = data.get('webhook_ids', [])
            api_key = data.get('api_key')

            if not webhook_ids:
                return {'success': False, 'error': 'webhook_ids es requerido'}

            # Validar API key y obtener sucursal
            branch = None
            if api_key:
                branch = request.env['api.gateway.branch'].sudo().validate_api_key(api_key)

            if not branch:
                return {'success': False, 'error': 'api_key inválida'}

            webhooks = request.env['api.gateway.webhook'].sudo().browse(webhook_ids)
            webhooks.mark_as_synced(branch.id)

            return {'success': True, 'marked': len(webhook_ids)}

        except Exception as e:
            _logger.error(f'[API Gateway] Error en webhooks/mark_synced: {str(e)}')
            return {'success': False, 'error': str(e)}
