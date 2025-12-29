from odoo import http
from odoo.http import request
import json
import requests
from odoo.exceptions import UserError
import time
import logging

_logger = logging.getLogger(__name__)


class DeunaPaymentController(http.Controller):

    def _get_effective_digital_payment_id(self, pos_config):
        if not pos_config:
            raise UserError("No POS configuration found.")

        warehouse = pos_config.picking_type_id.warehouse_id
        if not warehouse:
            # keep your existing error semantics
            raise UserError("No warehouse linked to this Point of Sale.")

        pos_id = pos_config.id_digital_payment or warehouse.id_digital_payment
        if not pos_id:
            # keep your existing error semantics/message style
            raise UserError(
                f"No digital payment ID configured for POS '{pos_config.display_name}' "
                f"or its warehouse '{warehouse.name}'."
            )
        return pos_id

    @http.route('/get_deuna_config', type='json', auth='public', cors='*')
    def get_deuna_config(self, pos_session_id=None):
        try:
            config = request.env['digital.payment.config'].sudo().search(
                [('bank_name', '=', 'DEUNA BCO PICHINCHA')],
                limit=1
            )
            if not config:
                return {"error": "No API configuration found for bank 'DEUNA BCO PICHINCHA'."}

            if not pos_session_id:
                return {"enable_advanced_payments": False, "warning": "No session_id provided"}

            pos_session = request.env['pos.session'].sudo().browse(pos_session_id)
            if not pos_session.exists() or pos_session.state != 'opened':
                return {"enable_advanced_payments": False, "warning": "Invalid or closed POS session"}

            try:
                _ = self._get_effective_digital_payment_id(pos_session.config_id)
            except UserError:
                return {"enable_advanced_payments": False}

            return {"enable_advanced_payments": config.enable_advanced_payments}
        except Exception as e:
            return {"error": str(e)}

    @http.route('/get_ahorita_config', type='json', auth='public', cors='*')
    def get_ahorita_config(self, pos_session_id=None):
        try:
            config = request.env['digital.payment.config'].sudo().search(
                [('bank_name', '=', 'AHORITA BANCO DE LOJA')],
                limit=1
            )
            if not config:
                return {"error": "No API configuration found for bank 'AHORITA BANCO DE LOJA'."}

            if not pos_session_id:
                return {"enable_advanced_payments": False, "warning": "No session_id provided"}

            pos_session = request.env['pos.session'].sudo().browse(pos_session_id)
            if not pos_session.exists() or pos_session.state != 'opened':
                return {"enable_advanced_payments": False, "warning": "Invalid or closed POS session"}

            warehouse = pos_session.config_id.picking_type_id.warehouse_id
            if not warehouse or not warehouse.id_digital_payment:
                return {"enable_advanced_payments": False}

            return {
                "enable_advanced_payments": config.enable_advanced_payments
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_api_config(self):
        """Fetch the API configuration for DEUNA BCO PICHINCHA."""
        config = request.env['digital.payment.config'].sudo().search([('bank_name', '=', 'DEUNA BCO PICHINCHA')],
                                                                     limit=1)
        if not config:
            raise UserError("No API configuration found for bank 'DEUNA BCO PICHINCHA'.")
        return config

    def _get_point_of_sale_id(self):
        pos_session = request.env['pos.session'].sudo().search(
            [('user_id', '=', request.session.uid), ('state', '=', 'opened')],
            limit=1
        )
        if not pos_session:
            raise UserError("No active POS session found.")

        pos_config = pos_session.config_id
        return self._get_effective_digital_payment_id(pos_config)

    @http.route('/deuna/payment/request', type='json', auth='public', cors='*')
    def request_payment(self, **kwargs):
        try:
            raw_data = request.httprequest.data
            try:
                data = json.loads(raw_data)
                params = data.get('params', data)
            except Exception:
                return {'error': 'Formato de datos inválido'}

            amount = params.get('amount')
            point_of_sale_id = params.get('point_of_sale_id')

            if point_of_sale_id is None:
                point_of_sale_id = self._get_point_of_sale_id()

            if amount is None:
                return {'error': 'El campo "amount" es requerido'}
            try:
                amount_float = float(amount)
            except (TypeError, ValueError):
                return {'error': 'El campo "amount" debe ser un número válido'}

            config = self._get_api_config()
            url = config.prod_request_payment_url if config.is_production else config.test_request_payment_url
            headers = {
                "Content-Type": "application/json",
                "x-api-key": config.prod_api_key if config.is_production else config.test_api_key,
                "x-api-secret": config.prod_api_secret if config.is_production else config.test_api_secret
            }

            payload = {
                "pointOfSale": point_of_sale_id,
                "qrType": "static",
                "amount": amount_float,
                "detail": "Pago realizado.",
                "internalTransactionReference": "Pago Digital App",
                "format": "2"
            }

            response = requests.post(url, headers=headers, json=payload)

            response_data = response.json()

            return response_data

        except Exception as e:
            return {'error': f'Error interno del servidor: {str(e)}'}

    @http.route('/deuna/canal_digital/payment/request', type='json', auth='public', cors='*')
    def request_payment_canal_digital(self, **kwargs):
        try:
            raw_data = request.httprequest.data
            try:
                data = json.loads(raw_data)
                params = data.get('params', data)
            except Exception:
                return {'error': 'Formato de datos inválido'}

            amount = params.get('amount')
            point_of_sale_id = params.get('point_of_sale_id')

            if point_of_sale_id is None:
                point_of_sale_id = self._get_point_of_sale_id()

            if amount is None:
                return {'error': 'El campo "amount" es requerido'}
            try:
                amount_float = float(amount)
            except (TypeError, ValueError):
                return {'error': 'El campo "amount" debe ser un número válido'}

            config = self._get_api_config()
            url = config.prod_request_payment_url if config.is_production else config.test_request_payment_url
            headers = {
                "Content-Type": "application/json",
                "x-api-key": config.prod_api_key if config.is_production else config.test_api_key,
                "x-api-secret": config.prod_api_secret if config.is_production else config.test_api_secret
            }

            payload = {
                "pointOfSale": point_of_sale_id,
                "qrType": "dynamic",
                "amount": amount_float,
                "detail": "Pago realizado.",
                "internalTransactionReference": "Pago Digital App",
                "format": "2"
            }

            response = requests.post(url, headers=headers, json=payload)

            response_data = response.json()

            return response_data

        except Exception as e:
            return {'error': f'Error interno del servidor: {str(e)}'}
        
    
        


    # @http.route('/send_whatsapp_message', type='json', auth='public', cors='*')
    # def send_whatsapp(self, phone, deeplink):
    #     try:
    #         emisor = request.env['ir.config_parameter'].sudo().get_param('number_digitalpayment')
    #         if not emisor:
    #             return {
    #                 "error": "El número emisor para pagos digitales no está configurado",
    #                 "code": "missing_config"
    #             }

    #         response = requests.post(
    #             "https://apiwhatsapp.solnustec.com/sendmessage",
    #             json={
    #                 "emisor": emisor,
    #                 "messages": [{"destinatary": phone, "message": f"Realiza tu pago aquí: {deeplink}"}]
    #             },
    #             headers={'Content-Type': 'application/json'},
    #             timeout=20
    #         )

    #         if response.status_code != 200:
    #             return {
    #                 "error": f"Error en el servicio de WhatsApp: {response.text}",
    #                 "status_code": response.status_code
    #             }

    #         return {
    #             "success": True,
    #             "response": response.json()
    #         }

    #     except requests.exceptions.Timeout:
    #         return {"error": "Timeout al conectar con el servicio de WhatsApp"}
    #     except Exception as e:
    #         return {
    #             "error": str(e)
    #         }

    @http.route('/deuna/payment/status', type='json', auth='public', cors='*', csrf=False)
    def payment_status(self, transaction_id=None, **kwargs):
        try:

            config = self._get_api_config()
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

            r = requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            response_data = r.json()

            record = request.env['deuna.post'].sudo().search([('transactionId', '=', transaction_id)], limit=1)

            if record:
                record.write({
                    'status_payment': response_data.get("status", "desconocido"),
                    'data': response_data,
                })

            return {
                "status": response_data.get("status", "desconocido"),
                **response_data
            }
        except Exception as e:
            _logger.exception("Error en /deuna/payment/status")
            return {"error": str(e)}

    # OBTENER LA SUCURSAL ACTUAL
    @http.route('/get_warehouse', type='json', auth='public', cors='*')
    def get_warehouse_info(self, pos_session_id=None):
        try:
            pos_session = request.env['pos.session'].sudo().browse(pos_session_id)
            warehouse = pos_session.config_id.picking_type_id.warehouse_id

            if not warehouse:
                return {"error": "No warehouse found for the given POS session."}

            warehouse_data = {}
            for field_name in warehouse._fields:
                try:
                    value = getattr(warehouse, field_name)
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        warehouse_data[field_name] = value
                    elif hasattr(value, 'ids'):
                        warehouse_data[field_name] = value.ids
                    elif hasattr(value, 'id'):
                        warehouse_data[field_name] = value.id
                    else:
                        warehouse_data[field_name] = str(value)
                except Exception:
                    continue

            return warehouse_data
        except Exception as e:
            return {"error": str(e)}

    @http.route('/deuna/create_record', type='json', auth='public', methods=['POST'], csrf=False)
    def create_deuna_record(self, **kwargs):
        try:
            order_id = kwargs.get('order_id')
            transaction_id = kwargs.get('transactionId')

            if not order_id or not transaction_id:
                return {"error": True, "message": "Faltan datos requeridos"}

            record = request.env['deuna.post'].sudo().create({
                'order_id_name': order_id,
                'transactionId': transaction_id,
                'status_payment': 'pendiente',
            })
            return {"error": False, "record_id": record.id}
        except Exception as e:
            return {"error": True, "message": str(e)}


