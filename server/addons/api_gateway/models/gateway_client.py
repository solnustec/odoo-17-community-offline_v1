# -*- coding: utf-8 -*-
"""
API Gateway Client

Clase de utilidad para que los módulos OFFLINE puedan comunicarse
fácilmente con el servidor PRINCIPAL a través del API Gateway.

Uso:
    client = env['api.gateway.client'].get_client()
    result = client.ahorita_generate_deeplink(amount=10.50, transaction_id='POS001')
"""
import logging
import json
import requests
from odoo import models, api

_logger = logging.getLogger(__name__)


class ApiGatewayClient(models.AbstractModel):
    """
    Cliente para comunicarse con el API Gateway del servidor PRINCIPAL.
    Este modelo es abstracto y no crea tabla en la base de datos.
    """
    _name = 'api.gateway.client'
    _description = 'Cliente API Gateway'

    @api.model
    def _get_gateway_url(self):
        """Obtiene la URL base del servidor PRINCIPAL."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'pos_offline_sync.principal_url', ''
        ).rstrip('/')

    @api.model
    def _get_offline_api_key(self):
        """Obtiene la API key del OFFLINE para autenticación."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'pos_offline_sync.api_key', ''
        )

    @api.model
    def _get_branch_code(self):
        """Obtiene el código de sucursal del OFFLINE."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'pos_offline_sync.branch_code', ''
        )

    @api.model
    def _make_request(self, endpoint, payload, timeout=30):
        """
        Hace un request al API Gateway.

        Args:
            endpoint: Endpoint del gateway (ej: '/api_gateway/proxy')
            payload: Diccionario con los datos a enviar
            timeout: Timeout en segundos

        Returns:
            dict con 'success', 'data' o 'error'
        """
        gateway_url = self._get_gateway_url()
        if not gateway_url:
            return {
                'success': False,
                'error': 'URL del servidor PRINCIPAL no configurada. Configure pos_offline_sync.principal_url'
            }

        url = f"{gateway_url}{endpoint}"

        # Agregar credenciales del OFFLINE
        payload['api_key'] = self._get_offline_api_key()
        payload['branch_code'] = self._get_branch_code()

        headers = {
            'Content-Type': 'application/json',
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json={'jsonrpc': '2.0', 'method': 'call', 'params': payload, 'id': None},
                timeout=timeout,
                verify=True
            )

            if response.status_code == 200:
                result = response.json()
                if 'result' in result:
                    return result['result']
                elif 'error' in result:
                    return {'success': False, 'error': result['error'].get('message', str(result['error']))}
                return result
            else:
                return {
                    'success': False,
                    'error': f'Error HTTP {response.status_code}: {response.text[:200]}'
                }

        except requests.exceptions.Timeout:
            return {'success': False, 'error': f'Timeout después de {timeout}s'}
        except requests.exceptions.ConnectionError as e:
            return {'success': False, 'error': f'Error de conexión con el servidor PRINCIPAL: {str(e)}'}
        except Exception as e:
            _logger.error(f'[Gateway Client] Error: {str(e)}')
            return {'success': False, 'error': str(e)}

    # ==================== PROXY GENÉRICO ====================

    @api.model
    def proxy_request(self, api_code, method, endpoint, payload=None, headers=None):
        """
        Hace un request a través del proxy genérico.

        Args:
            api_code: Código de la API (ej: 'ahorita', 'deuna')
            method: Método HTTP ('GET', 'POST', etc.)
            endpoint: Endpoint de la API externa
            payload: Datos a enviar
            headers: Headers adicionales

        Returns:
            dict con 'success', 'data' o 'error'
        """
        return self._make_request('/api_gateway/proxy', {
            'api_code': api_code,
            'method': method,
            'endpoint': endpoint,
            'payload': payload or {},
            'headers': headers or {},
        })

    # ==================== AHORITA ====================

    @api.model
    def ahorita_generate_deeplink(self, amount, transaction_id=None, message_id=None,
                                   user_id=415472, device_id='127.0.0.1'):
        """
        Genera un deeplink de pago Ahorita.

        Args:
            amount: Monto a cobrar
            transaction_id: ID único de transacción (opcional, se genera uno si no se proporciona)
            message_id: Mensaje/referencia de la factura
            user_id: ID de usuario en Ahorita
            device_id: Identificador del dispositivo

        Returns:
            dict con 'success', 'deeplink', 'qr', 'transactionId' o 'error'
        """
        import time

        if not transaction_id:
            transaction_id = f"OFFLINE_{int(time.time() * 1000)}"
        if not message_id:
            message_id = f"Pago POS {transaction_id}"

        return self._make_request('/api_gateway/ahorita/generate_deeplink', {
            'userId': user_id,
            'messageId': message_id,
            'transactionId': transaction_id,
            'deviceId': device_id,
            'amount': float(amount),
        }, timeout=60)

    @api.model
    def ahorita_check_status(self, deeplink_id):
        """
        Consulta el estado de un pago Ahorita.

        Args:
            deeplink_id: ID del deeplink generado

        Returns:
            dict con 'success', 'status', 'data' o 'error'
        """
        # Primero intentar consultar webhooks pendientes
        webhooks = self.get_pending_webhooks('ahorita')
        if webhooks.get('success') and webhooks.get('webhooks'):
            for wh in webhooks['webhooks']:
                if wh.get('transaction_id') == deeplink_id:
                    return {
                        'success': True,
                        'status': wh.get('event_type', 'unknown'),
                        'data': wh.get('payload', {}),
                    }

        return {'success': True, 'status': 'pending'}

    # ==================== DEUNA ====================

    @api.model
    def deuna_request_payment(self, amount, point_of_sale_id=None, qr_type='dynamic'):
        """
        Solicita un pago a través de Deuna.

        Args:
            amount: Monto a cobrar
            point_of_sale_id: ID del punto de venta
            qr_type: Tipo de QR ('dynamic' o 'static')

        Returns:
            dict con 'success', 'data' o 'error'
        """
        return self._make_request('/api_gateway/deuna/payment/request', {
            'amount': float(amount),
            'point_of_sale_id': point_of_sale_id,
            'qr_type': qr_type,
        }, timeout=60)

    @api.model
    def deuna_check_status(self, transaction_id):
        """
        Consulta el estado de un pago Deuna.

        Args:
            transaction_id: ID de la transacción

        Returns:
            dict con 'success', 'status', 'data' o 'error'
        """
        return self._make_request('/api_gateway/deuna/payment/status', {
            'transaction_id': transaction_id,
        })

    # ==================== WEBHOOKS ====================

    @api.model
    def get_pending_webhooks(self, api_code, limit=100):
        """
        Obtiene webhooks pendientes del servidor PRINCIPAL.

        Args:
            api_code: Código de la API ('ahorita', 'deuna', etc.)
            limit: Cantidad máxima de webhooks a obtener

        Returns:
            dict con 'success', 'webhooks' o 'error'
        """
        return self._make_request('/api_gateway/webhooks/pending', {
            'api_code': api_code,
            'limit': limit,
        })

    @api.model
    def mark_webhooks_synced(self, webhook_ids):
        """
        Marca webhooks como sincronizados.

        Args:
            webhook_ids: Lista de IDs de webhooks

        Returns:
            dict con 'success' o 'error'
        """
        return self._make_request('/api_gateway/webhooks/mark_synced', {
            'webhook_ids': webhook_ids,
        })

    # ==================== UTILIDADES ====================

    @api.model
    def test_connection(self):
        """
        Prueba la conexión con el servidor PRINCIPAL.

        Returns:
            dict con 'success' y 'message' o 'error'
        """
        gateway_url = self._get_gateway_url()
        if not gateway_url:
            return {
                'success': False,
                'error': 'URL del servidor PRINCIPAL no configurada'
            }

        try:
            response = requests.get(f"{gateway_url}/web/webclient/version_info", timeout=10)
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': f'Conexión exitosa con {gateway_url}',
                    'version_info': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'Error HTTP {response.status_code}'
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}
