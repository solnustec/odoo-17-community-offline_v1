import base64
import hashlib
import time
import uuid
from datetime import datetime

import pytz
import requests

from odoo import http, fields, _
from odoo.http import request, Response
import json

from .api_security import validate_api_static_token
import logging

_logger = logging.getLogger(__name__)


class MobilePaymentAPI(http.Controller):

    @http.route('/api/store/payment-method',
                type='http',
                auth='public',  # o 'user' si requiere autenticación
                methods=['GET'],
                csrf=False,
                cors='*')
    @validate_api_static_token
    def get_mobile_payment_methods(self, **kwargs):
        """Obtener métodos de pago habilitados para app móvil"""
        try:
            # Buscar métodos de pago habilitados para móvil
            PaymentMethod = request.env['payment.method']
            methods = PaymentMethod.sudo().search([
                ('is_mobile_enabled', '=', True),
            ])
            result = []
            method_data = {}
            for method in methods:
                # filtar proveedor paymentes
                if method.code == 'card':
                    active_providers = method.provider_ids.filtered(
                        lambda p: p.state == 'enabled')
                    if active_providers[0].name == "Paymentez":
                        method_data = {
                            'provider': 'Tarjeta de Crédito/Débito',
                            'id': method.id,
                            'code': method.code,
                            'type': 'form',
                            'production': method.prod_mode,
                        }

                else:
                    method_data = {
                        'provider': method.name,
                        'id': method.id,
                        'code': method.code,
                        'type': 'link',
                        'production': method.prod_mode,

                    }
                result.append(method_data)
            return Response(json.dumps(
                {
                    'success': True,
                    'data': result,
                    'count': len(result)
                }
            ),
                mimetype='application/json')

        except Exception as e:
            return Response(json.dumps({
                'success': False,
                'error': str(e),
                'data': []
            }),
                status=500,
                mimetype='application/json')

    @http.route('/api/store/payment-method/<int:payment_id>',
                type='http',
                auth='public',
                methods=['POST'],
                csrf=False,
                cors='*')
    @validate_api_static_token
    def create_mobile_payment_link(self, payment_id, **kwargs):
        tz = pytz.timezone('America/Bogota')
        # jwt_data = getattr(request, '_jwt_data', {})
        # user_id = jwt_data.get('user_id')
        now = datetime.now(tz)
        now = now.astimezone(pytz.UTC).replace(tzinfo=None)
        data = json.loads(request.httprequest.data.decode('utf-8'))
        order_id = data.get('order_id')
        user_id = data.get('user_id')
        PaymentMethod = request.env['payment.method']
        method = PaymentMethod.sudo().search([
            ('id', '=', int(payment_id)),
            ('is_mobile_enabled', '=', True)
        ], limit=1)
        if not method:
            return Response(json.dumps({
                'success': False,
                'error': 'Método de pago no encontrado o no habilitado para móvil',
                'data': {}
            }), status=404, mimetype='application/json')
        # try:
        SaleOrder = request.env['sale.order']
        order = SaleOrder.sudo().search([
            ('id', '=', int(order_id)),
            # ('state', '=', 'sale'),
            # ('user_id', '=', int(user_id))
        ], limit=1)

        # veriffy if has not  line wirh default_code = ENVIOSAPPMOVIL and price > 0

        shipping_line = order.order_line.filtered(
            lambda l: l.product_id.default_code == 'ENVIOSAPPMOVIL')
        if not shipping_line :
            return Response(json.dumps({
                'success': False,
                'error': 'La dirección de envío seleccionada no es válida',
                'data': {}
            }), status=404, mimetype='application/json')

        if not order:
            return Response(json.dumps({
                'success': False,
                'error': 'Orden no encontrada o ya fue pagada',
                'data': {}
            }), status=404, mimetype='application/json')
        if not order.partner_shipping_id:
            return Response(json.dumps({
                'success': False,
                'error': 'Se debe agregar una dirección de Entrega, para poder continuar',
                'data': {}
            }), status=404, mimetype='application/json')
        if not order.partner_id.email:
            return Response(json.dumps({
                'success': False,
                'error': 'Correo electrónico del cliente no está definido, por favor actualice el correo del cliente para continuar',
                'data': {}
            }), status=404, mimetype='application/json')
        if order.amount_total == 0:
            return Response(json.dumps({
                'success': False,
                'error': 'No hay nada para pagar',
                'data': {}
            }), status=404, mimetype='application/json')
        if method.code == 'deuna':
            dev_mode = False
            if method.prod_mode:

                payment_data = method.mobile_prod_config
            else:
                dev_mode = True
                payment_data = method.mobile_dev_config
            payment_data_json = json.loads(payment_data)
            payment_data_json.get('payload').update({
                'amount': order.amount_total,
                'detail': f'Pago de pedido #{order.name} -{order.partner_id.name}',
                'internalTransactionReference': f'{order.name}-{int(time.time())}',
            })
            # veriffy if order have a payment transaction in state done or pending
            PaymentTransaction = request.env['payment.transaction']
            existing_tx = PaymentTransaction.sudo().search([
                ('sale_order_ids', 'in', order.id),
                ('state', 'in', ['pending']),
                ('payment_method_id.code', '=', 'deuna')
            ], limit=1)
            if existing_tx and existing_tx.amount == order.amount_total and existing_tx.payment_method_id.code == 'deuna':
                state_selection = dict(existing_tx._fields['state'].selection)
                return Response(json.dumps({
                    'success': True,
                    'msg': f'La orden ya tiene una transacción de pago Pendiente',
                    'data': {
                        'transaction_id': existing_tx.payment_transaction_id,
                        'qr': existing_tx.qr_code or '',
                        'deeplink': existing_tx.checkout_url,
                        'type': existing_tx.url_type,
                        'expiration_date': existing_tx.expiration_payment_date.isoformat(),
                    }
                }), status=200, mimetype='application/json')
            # elif existing_tx.payment_method_id.code != 'deuna':
            #     existing_tx.sudo().write({'state': 'cancel'})
            elif existing_tx.amount != order.amount_total:
                existing_tx.sudo().write({'state': 'cancel'})
            # create the payment link
            url = payment_data_json.get('url')
            headers = payment_data_json.get('headers')
            payload = payment_data_json.get('payload')
            response = requests.post(url, headers=headers, json=payload)
            response_data = response.json()
            if response.status_code != 200:
                return Response(json.dumps({
                    'success': False,
                    'error': 'Error al procesar el pago, Intente nuevamente',
                    'data': {}
                }), status=response.status_code, mimetype='application/json')
            # order.sudo().write({
            #     'state': 'sale'
            # })
            # calculate expiration date
            expiration_minutes = payload.get('expiredTime')
            expiration_date = fields.Datetime.add(now, minutes=expiration_minutes)

            # create the transaction
            PaymentTransaction.sudo().create({
                'amount': order.amount_total,
                'partner_id': order.partner_id.id,
                'currency_id': request.env.ref("base.USD").id,
                # 'payment_json_data': json.dumps(payment_data_json),
                'sale_order_ids': [(4, order.id)],
                'payment_method_id': method.id,
                'provider_id': method.provider_ids and method.provider_ids[0].id or False,
                'reference': f"{order.name}-{int(time.time())}",
                'checkout_url': response_data.get('deeplink'),
                'expiration_payment_date': expiration_date,
                'url_type': 'link',
                'qr_code': response_data.get('qr', ''),
                'payment_transaction_id': response_data.get('transactionId'),
                'is_app_transaction': True,
                'state': 'pending',
            })
            try:
                message_record = request.env[
                    'notification.message'].sudo().get_message_by_type(
                    'order_payment')
                if '{{order_numero}}' in message_record.body:
                    body = message_record.body.replace('{{order_numero}}', order.name)
                elif '{{order_total}}' in message_record.body:
                    body = message_record.body.replace('{{order_total}}', str(order.amount_total))
                else:
                    body = message_record.body
                request.env['user.notification'].sudo().create({
                    'name': message_record.title,
                    'user_id': user_id,
                    'message': f"{body}",
                })
                request.env['firebase.service']._send_single_push_notification(user_id=user_id,
                                                                               title=message_record.title,
                                                                               body=body)
            except Exception as e:
                print(e, "Error sending notification")
                pass
            try:
                if order.state == 'draft':
                    order.sudo().with_context(mail_notify_customer=False).action_confirm()
            except Exception as e:
                return Response(json.dumps({
                    'success': False,
                    'error': 'Error al procesar la orden, intente mas tarde.',
                    'data': {}
                }), status=200, mimetype='application/json')

            return Response(
                json.dumps({
                    'success': True,
                    'data': {
                        'transaction_id': response_data.get('transactionId'),
                        'qr': response_data.get('qr'),
                        'deeplink': response_data.get('deeplink'),
                        'type': 'link',
                        'expiration_date': expiration_date.isoformat()
                    }
                }), mimetype='application/json'
            )

        if method.code == 'card':
            if method.prod_mode:
                payment_data = method.mobile_prod_config
            else:
                payment_data = method.mobile_dev_config
            payment_data_json = json.loads(payment_data)
            app_code = payment_data_json.get('app_code')
            app_key = payment_data_json.get('app_key')
            expiration_time = payment_data_json.get(
                'expiration_time')  # 60m minutos tiempo de expircacion

            paymentez_url = payment_data_json.get('url')
            amount = order.amount_total
            description = f'Pago de pedido #{order.name}'
            user_email = order.partner_id.email
            # name = order.partner_id.name
            # last_name = order.partner_id.name
            cedula = order.partner_id.vat
            PaymentTransaction = request.env['payment.transaction']
            existing_tx = PaymentTransaction.sudo().search([
                ('sale_order_ids', 'in', order.id),
                ('state', 'in', ['pending']),
                ('payment_method_id.code', '=', 'card')
            ], limit=1)
            if existing_tx and existing_tx.amount == order.amount_total and existing_tx.payment_method_id.code == 'card':
                state_selection = dict(existing_tx._fields['state'].selection)
                state_label = state_selection.get(existing_tx.state, existing_tx.state)
                return Response(json.dumps({
                    'success': True,
                    'msg': f'La orden ya tiene una transacción de pago Pendiente',
                    'data': {
                        'transaction_id': existing_tx.payment_transaction_id,
                        'qr': existing_tx.qr_code or '',
                        'deeplink': existing_tx.checkout_url,
                        'type': existing_tx.url_type,
                        'expiration_date': existing_tx.expiration_payment_date.isoformat(),
                    }
                }), status=200, mimetype='application/json')
            # elif existing_tx.payment_method_id.code != 'card':
            #     existing_tx.sudo().write({'state': 'cancel'})
            elif existing_tx.amount != order.amount_total:
                existing_tx.sudo().write({'state': 'cancel'})
            # create the payment link
            format_partner_name = self._split_name(order.partner_id.name)
            name = format_partner_name.get('name')
            last_name = format_partner_name.get('last_name')

            response = self.create_paymentez_payment_link(app_code, app_key, paymentez_url, amount,
                                                          description, user_email, name, last_name,
                                                          cedula, expiration_time, order.id)
            if response.get('success'):
                response_data = response.get('data', {})
                payment_data = response_data.get('payment', {})
                payment_order = response_data.get('order', {})
                expiration_minutes = expiration_time // 60
                expiration_date = fields.Datetime.add(now, minutes=expiration_minutes)

                PaymentTransaction.sudo().create({
                    'amount': order.amount_total,
                    'partner_id': order.partner_id.id,
                    'currency_id': request.env.ref("base.USD").id,
                    'payment_json_data': json.dumps(response_data),
                    'sale_order_ids': [(4, order.id)],
                    'payment_method_id': method.id,
                    'checkout_url': payment_data.get('payment_url', ''),
                    'reference': f"{order.name}-{int(time.time())}",
                    'expiration_payment_date': expiration_date,
                    'provider_id': method.provider_ids and method.provider_ids[0].id or False,
                    'state': 'pending',
                    'url_type': 'form',
                    'qr_code': payment_data.get('payment_qr', ''),
                    'payment_transaction_id': payment_order.get('id'),
                    'is_app_transaction': True,
                })
                try:
                    message_record = request.env[
                        'notification.message'].sudo().get_message_by_type(
                        'order_payment')
                    if '{{order_numero}}' in message_record.body:
                        body = message_record.body.replace('{{order_numero}}', order.name)
                    elif '{{order_total}}' in message_record.body:
                        body = message_record.body.replace('{{order_total}}',
                                                           str(order.amount_total))
                    else:
                        body = message_record.body
                    request.env['user.notification'].sudo().create({
                        'name': message_record.title,
                        'user_id': user_id,
                        'message': f"{body}",
                    })
                    request.env['firebase.service']._send_single_push_notification(user_id=user_id,
                                                                                   title=message_record.title,
                                                                                   body=body)
                except Exception as e:
                    pass
                try:
                    # Aplicar with_context al recordset (no al resultado de action_confirm)
                    if order.state == 'draft':
                        order.sudo().with_context(mail_notify_customer=False).action_confirm()
                except Exception as e:
                    return Response(json.dumps({
                        'success': False,
                        'error': 'Error al procesar la orden, intente mas tarde.',
                        'data': {}
                    }), status=400, mimetype='application/json')

                return Response(json.dumps({
                    'success': True,
                    'data': {
                        'transaction_id': payment_order.get('id'),
                        'qr': payment_data.get('payment_qr', ''),
                        'deeplink': payment_data.get('payment_url', ''),
                        'type': 'form',
                        'expiration_date': expiration_date.isoformat()
                    }
                }), status=200, mimetype='application/json')
            else:
                return Response(json.dumps({
                    'success': False,
                    'error': 'Método de pago no disponible, intente con otro',
                    'data': {
                    }
                }), status=500, mimetype='application/json')
        # except Exception as e:
        #     print(e)
        #     return Response(json.dumps(
        #         {
        #             'success': False,
        #             'error': str(e),
        #             'data': {}
        #         }
        #     ), status=500, mimetype='application/json')

    def generate_paymentez_token(self, app_code, app_key):
        timestamp = str(int(time.time()))
        key_time = app_key + timestamp
        uniq_token = hashlib.sha256(key_time.encode()).hexdigest()
        str_union = f"{app_code};{timestamp};{uniq_token}"
        token = base64.b64encode(str_union.encode()).decode()
        return token

    def _split_name(self, full_name):
        if not full_name:
            return {"name": "", "last_name": ""}

        parts = full_name.strip().split()
        count = len(parts)

        if count == 1:
            return {"name": parts[0], "last_name": parts[0]}
        elif count == 2:
            return {"name": parts[0], "last_name": parts[1]}
        elif count == 3:
            return {"name": " ".join(parts[:2]), "last_name": parts[2]}
        else:
            return {"name": " ".join(parts[:2]), "last_name": " ".join(parts[2:])}

    # funcioon para generar el pago de paymentez
    def create_paymentez_payment_link(self, app_code, app_key, paymentez_url, amount, description,
                                      user_email, name, last_name, cedula,
                                      expiration_time, order_id):
        token = self.generate_paymentez_token(app_code, app_key)
        dev_reference = str(uuid.uuid4())
        # 2 horas
        data = {
            "user": {
                "id": str(cedula),
                "email": user_email,
                "name": name,
                "last_name": last_name,
                # "vat": cedula,
            },
            "order": {
                "dev_reference": f"{order_id}-{dev_reference}",
                "description": description,

                "amount": float(amount),
                "tax_percentage": 0,
                "taxable_amount": 0,
                "installments_type": 0,
                "currency": "USD"
            },
            "configuration": {
                "partial_payment": True,
                "expiration_time": int(expiration_time) or 3600,
                "allowed_payment_methods": ["Card"],
                "allow_retry": True,
                "success_url": "https://farmaciascuxibamba.com.ec/webhook/nuvei",
                "failure_url": "https://farmaciascuxibamba.com.ec/webhook/nuvei",
                "pending_url": "https://farmaciascuxibamba.com.ec/webhook/nuvei",
                "review_url": "https://farmaciascuxibamba.com.ec/webhook/nuvei",
            },
        }
        headers = {
            "Auth-Token": token,
            "Content-Type": "application/json"
        }

        response = requests.post(paymentez_url, json=data, headers=headers, timeout=30)
        return response.json()

    @http.route('/api/store/payment-method/status/<string:transaction_id>',
                type='http',
                auth='public',
                methods=['GET'],
                csrf=False,
                cors='*')
    @validate_api_static_token
    def check_payment_status(self, transaction_id, **kwargs):
        PaymentTransaction = request.env['payment.transaction']
        transaction = PaymentTransaction.sudo().search([
            ('payment_transaction_id', '=', transaction_id),
        ], limit=1)
        if not transaction:
            return Response(json.dumps({
                'success': False,
                'error': 'Transacción no encontrada',
                'data': {}
            }), status=404, mimetype='application/json')
        state_selection = dict(transaction._fields['state'].selection)
        state_label = state_selection.get(transaction.state, transaction.state)
        return Response(json.dumps({
            'success': True,
            'data': {
                'transaction_id': transaction.payment_transaction_id,
                'state': transaction.state,
                'state_label': _(state_label),
                'amount': transaction.amount,
                'reference': transaction.reference,
                'sale_order_ids': transaction.sale_order_ids.ids,
            }
        }), status=200, mimetype='application/json')
