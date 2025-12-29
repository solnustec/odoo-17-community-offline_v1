import base64
import hashlib
import json
import time
from datetime import timedelta

import requests
import logging

# Configurar el logger
_logger = logging.getLogger(__name__)

from odoo import models, fields, api


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    """
    Represents a payment transaction in the API Store.
    """

    payment_json_data = fields.Json(string='Payment Data', readonly=True, copy=False
                                    , help='JSON data containing payment transaction details')
    is_app_transaction = fields.Boolean(string='Pago desde la aplicación', readonly=True, copy=False
                                        ,
                                        help='Indica si la transacción fue realizada desde la aplicación móvil')
    payment_transaction_id = fields.Char(string='Id de la transacción', readonly=True, copy=False
                                         , help='Identificador único de la transacción de pago')
    status_url = fields.Char(string='URL de estado', readonly=True, copy=False
                             , help='URL para verificar el estado de la transacción de pago')
    expiration_payment_date = fields.Datetime(string='Fecha de expiración del enlace',
                                              readonly=True, copy=False
                                              , help='Fecha y hora en que el enlace de pago expira')
    checkout_url = fields.Char(string='URL del pago', readonly=True, copy=False)
    qr_code = fields.Char(string='URL del QR', readonly=True, copy=False)
    url_type = fields.Char(string='Tipo de pago(Link/Form)', readonly=True, copy=False)

    @api.model
    def get_payment_status_by_app_mobile(self):
        """
        Retrieves payment transactions made through the mobile app that are in 'pending' state.

        Returns:
            recordset: A recordset of payment transactions in 'pending' state made via the mobile app.
        """

        payment_transactions = self.env['payment.transaction'].sudo().search(
            [('state', '=', 'pending'), ('is_app_transaction', '=', True)])
        # payment_transactions = self.env['payment.transaction'].sudo().browse(100)
        _logger.info('Payment transactions: %s', payment_transactions)
        for transaction in payment_transactions:
            transaction._check_payment_status()
        # return payment_transactions
        self._check_expiration_payment_date()

    def _check_expiration_payment_date(self):
        """ marcar las transacciones como canceladas si han expirado """
        current_datetime = fields.Datetime.now() - timedelta(minutes=1)
        expired_transactions = self.search([
            ('state', '=', 'pending'), ('is_app_transaction', '=', True),
            ('expiration_payment_date', '<=', current_datetime)
        ])
        for transaction in expired_transactions:
            # get order
            order = transaction.sale_order_ids
            if order.state != 'done':
                try:
                    user_id = self.env['res.users'].sudo().search(
                        [('partner_id', '=', order.partner_id.id)], limit=1)
                    message_record = self.env[
                        'notification.message'].sudo().get_message_by_type(
                        'payment_failed')
                    self.env['user.notification'].sudo().create({
                        'name': message_record.title,
                        'user_id': user_id.id,
                        'message': f"{message_record.body}",
                    })
                    self.env['firebase.service']._send_single_push_notification(user_id=user_id.id,
                                                                                title=message_record.title,
                                                                                body=message_record.body)
                except Exception as e:
                    pass
                order.with_context(disable_cancel_warning=True).action_cancel()
                order.apply_app_mobile_promotions()
            transaction.write({'state': 'cancel'})
        return True

    def _check_payment_status(self):
        """ obtener los estados de las transacciones realizadas desde la app movil """
        if self.is_app_transaction:
            import requests
            PaymentMethod = self.env['payment.method'].sudo()
            try:
                if self.provider_code == 'paymentez':
                    # if self.state == 'cancel':
                    if self.state == 'done':
                        # self.sudo().write({'state': 'done'})
                        self._set_payment_done()
                    else:
                        self._set_payment_canceled()


                elif self.payment_method_id and self.payment_method_id.code == 'deuna':
                    payment_credentials = PaymentMethod.get_payment_credentials(
                        provider_code=self.payment_method_id.code,
                    )
                    headers = payment_credentials.get('headers')
                    body = {
                        "idTransacionReference": self.payment_transaction_id,
                        "idType": "0"
                    }
                    url = f"{payment_credentials.get('payment_status_url')}"
                    response = requests.post(url, json=body, headers=headers, timeout=10)

                    if response.status_code == 200:
                        data = response.json()
                        _logger.info('Payment status: %s', data)
                        status = data.get('status')
                        if status == 'APPROVED':
                        # if status == 'PENDING':
                            # update transaction status to done
                            self.sudo().write({'state': 'done'})
                            self._set_payment_done()
                        elif status == 'REJECTED':
                            self.sudo().write({'state': 'cancel'})
                            self._set_payment_canceled()

            except requests.RequestException as e:
                print(f"Error checking payment status for transaction {self.id}: {e}")

    def generate_paymentez_token(self, app_code, app_key):
        timestamp = str(int(time.time()))
        key_time = app_key + timestamp
        uniq_token = hashlib.sha256(key_time.encode()).hexdigest()
        str_union = f"{app_code};{timestamp};{uniq_token}"
        token = base64.b64encode(str_union.encode()).decode()
        return token

    @api.model
    def _set_payment_done(self):
        """Marcar la transacción como realizada y crear el registro en account.payment
        - Usar ids primitivos en los valores pasados a create.
        - Comprobar existencia de journal / payment_method_line.
        - Registrar excepciones para facilitar debugging.
        """
        AccountPayment = self.env['account.payment']
        for record in self:
            # Determinar journal y payment_method_line de forma segura
            if record.provider_code == 'paymentez':
                journal = self.env['account.journal'].sudo().search([('code', '=', 'PYMTZ')],
                                                                    limit=1)
                method_line = self.env['account.payment.method.line'].sudo().search(
                    [('journal_id', '=', journal.id if journal else False),
                     ('name', 'in', ['Paymentez'])], limit=1
                )
            else:
                journal = self.env['account.journal'].sudo().search([('code', '=', 'BCOPH')],
                                                                    limit=1)
                method_line = self.env['account.payment.method.line'].sudo().search(
                    [('journal_id', '=', journal.id if journal else False),
                     ('name', 'in', ['Deuna', 'De Una', 'Transferencia De una'])], limit=1
                )

            if not journal:
                _logger.warning(
                    'Journal no encontrado para la transacción %s, se omite creación de pago.',
                    record.id)
                continue

            method_line_id = method_line.id if method_line else False

            # Obtener una orden relacionada (la primera) para referencias de moneda/pricelist
            order = record.sale_order_ids[:1] if record.sale_order_ids else None
            currency_id = False
            if order and order.pricelist_id and order.pricelist_id.currency_id:
                currency_id = order.pricelist_id.currency_id.id

            try:
                if record.state in ('authorized', 'done'):
                    pay_vals = {
                        'payment_type': 'inbound',
                        'partner_type': 'customer',
                        'partner_id': record.partner_id.id if record.partner_id else False,
                        'payment_method_line_id': method_line_id,
                        'amount': record.amount or 0.0,
                        'currency_id': currency_id,
                        'payment_method_code': record.payment_method_id.code if record.payment_method_id else False,
                        'journal_id': journal.id,
                        'ref': record.reference or False,
                        'date': fields.Date.context_today(self),
                        'state': 'draft',
                    }

                    pay = AccountPayment.sudo().create(pay_vals)
                    # asegurar que write recibe primitivos
                    record.sudo().write({'payment_id': pay.id, 'state': 'done'})
                    pay.sudo().action_post()
                    # verifiacar si hay otros pagos pendientes y cancelarlos
                    pending_transactions = self.env['payment.transaction'].sudo().search([
                        ('sale_order_ids', 'in', record.sale_order_ids.ids),
                        ('state', '=', 'pending'),
                        ('id', '!=', record.id)
                    ])
                    for pending in pending_transactions:
                        pending.sudo().write({'state': 'cancel'})
            except Exception:
                _logger.exception('Error creando account.payment para la transacción %s', record.id)

            # Actualizar órdenes asociadas: crear facturas y notificar
            for order in record.sale_order_ids:
                try:
                    if order.invoice_status != 'invoiced':
                        order.sudo()._create_invoices()
                        order.invoice_status = 'invoiced'
                        try:
                            user_id = self.env['res.users'].sudo().search(
                                [('partner_id', '=', order.partner_id.id)], limit=1)
                            message_record = self.env[
                                'notification.message'].sudo().get_message_by_type(
                                'payment_successful')
                            self.env['user.notification'].sudo().create({
                                'name': message_record.title,
                                'user_id': user_id.id,
                                'message': f"{message_record.body}",
                            })
                            self.env['firebase.service']._send_single_push_notification(
                                user_id=user_id.id, title=message_record.title,
                                body=message_record.body)
                        except Exception:
                            _logger.exception('Error notificando pago exitoso para la orden %s',
                                              order.name)
                except Exception:
                    _logger.exception('Error al crear la factura para la orden %s', order.name)
        return True

    # def _set_payment_done(self):
    #     """ marcar la transaccion como realizada """
    #     AccountPayment = self.env['account.payment']
    #     for record in self:
    #         if record.provider_code == 'paymentez':
    #             journal_id = self.env['account.journal'].sudo().search([('code', '=', 'PYMTZ')],
    #                                                                    limit=1)
    #             account_payment_method_line = self.env['account.payment.method.line'].sudo().search(
    #                 [('journal_id', '=', journal_id.id), ('name', 'in', ['Paymentez', ])
    #                  ])
    #         else:
    #             journal_id = self.env['account.journal'].sudo().search([('code', '=', 'BCOPH')],
    #                                                                    limit=1)
    #             account_payment_method_line = self.env['account.payment.method.line'].sudo().search(
    #                 [('journal_id', '=', journal_id.id),
    #                  ('name', 'in', ['Deuna', 'De Una', 'Transferencia De una'])
    #                  ])
    #
    #         #
    #         print(
    #             f"Journal ID: {journal_id.id}, Payment Method Line ID:{account_payment_method_line} {record.state}")
    #         if record.state == 'authorized' or record.state == 'done':
    #             try:
    #                 pay = AccountPayment.sudo().create({
    #                     'payment_type': 'inbound',
    #                     'partner_type': 'customer',
    #                     'partner_id': record.partner_id.id,
    #                     'payment_method_line_id': account_payment_method_line,
    #                     'amount': record.amount,
    #                     'currency_id': record.sale_order_ids.pricelist_id.currency_id.id,
    #                     'payment_method_code': record.payment_method_id.code,
    #                     'journal_id': journal_id.id,
    #                     'ref': record.reference,
    #                     # 'payment_token_id': record.payment_transaction_id,
    #                     'date': fields.Date.context_today(self),
    #                     'state': 'draft',
    #                 })
    #
    #                 record.sudo().write(
    #                     {'payment_id': pay.id, 'state': 'done'}
    #                 )
    #                 pay.sudo().action_post()
    #             except Exception as e:
    #                 pass
    #
    #             # update order status to 'paid'
    #         for order in record.sale_order_ids:
    #             try:
    #                 if order.invoice_status != 'invoiced':
    #                     order.sudo()._create_invoices()
    #                     order.invoice_status = 'invoiced'
    #                     try:
    #                         user_id = self.env['res.users'].sudo().search(
    #                             [('partner_id', '=', order.partner_id.id)], limit=1)
    #                         message_record = self.env[
    #                             'notification.message'].sudo().get_message_by_type(
    #                             'payment_successful')
    #                         self.env['user.notification'].sudo().create({
    #                             'name': message_record.title,
    #                             'user_id': user_id.id,
    #                             'message': f"{message_record.body}",
    #                         })
    #                         self.env['firebase.service']._send_single_push_notification(
    #                             user_id=user_id.id, title=message_record.title,
    #                             body=message_record.body)
    #                     except Exception as e:
    #                         pass
    #
    #             except Exception as e:
    #                 print(f"Error al crear la factura para la orden {order.name}: {e}")
    #     return True

    @api.model
    def _set_payment_canceled(self):
        """ marcar la transaccion como cancelada """
        for record in self:
            if record.state == 'cancel':
                for order in record.sale_order_ids:
                    try:
                        user_id = self.env['res.users'].sudo().search(
                            [('partner_id', '=', order.partner_id.id)], limit=1)
                        message_record = self.env[
                            'notification.message'].sudo().get_message_by_type(
                            'payment_failed')
                        self.env['user.notification'].sudo().create({
                            'name': message_record.title,
                            'user_id': user_id.id,
                            'message': f"{message_record.body}",
                        })
                        self.env['firebase.service']._send_single_push_notification(
                            user_id=user_id.id, title=message_record.title,
                            body=message_record.body)
                    except Exception as e:
                        pass
                    if order.state != 'sale':
                        order.sudo().with_context(disable_cancel_warning=True).action_cancel()
                    # order.sudo().with_context(disable_cancel_warning=True).action_draft()
                    # order.apply_app_mobile_promotions()
        return True

    @api.model
    def manual_check_payment_status(self, payment_transaction_id):
        """ metodo cron para verificar el estado de las transacciones """
        PaymentMethod = self.env['payment.method'].sudo()
        payment_credentials = PaymentMethod.get_payment_credentials(
            provider_code=self.payment_method_id.code,
        )
        token = PaymentMethod.generate_paymentez_token(
            app_code=payment_credentials.get('app_code'),
            app_key=payment_credentials.get('app_key')
        )
        headers = {
            "Auth-Token": token,
            "Content-Type": "application/json"
        }
        url = f"{payment_credentials.get('payment_status_url')}/{payment_transaction_id}"
        response = requests.get(url, headers=headers, timeout=10)
        # TODO falta la url para ver el estado de la transaccion
        print(response.json())
        _logger.info(response.json())
        if response.status_code == 200:
            data = response.json()
            status = data.get('status')
            if status == 'completed':
                self._set_payment_done()
            elif status == 'failed':
                self._set_payment_canceled()
