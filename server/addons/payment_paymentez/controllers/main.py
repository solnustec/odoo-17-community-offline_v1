# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http
from odoo.http import request


class PaymentPaymentezController(http.Controller):
    _simulation_url = '/payment/paymentez/simulate_payment'

    @http.route(_simulation_url, type='json', auth='public')
    def demo_simulate_payment(self, **data):
        """ Simulate the response of a payment request.

        :param dict data: The simulated notification data.
        :return: None
        """
        request.env['payment.transaction'].sudo()._handle_notification_data('paymentez', data)

    @http.route('/paymentez/get_provider_info', type='json', auth='public')
    def get_provider_info(self):
        provider = request.env['payment.provider'].search([('code', '=', 'paymentez')], limit=1)
        if not provider:
            return {'error': 'Paymentez provider not found'}
        
        application_code = provider._paymentez_get_application_code()
        application_key = provider._paymentez_get_application_key()
        state = provider._paymentez_get_state()
        id = provider._paymentez_get_id()
        
        return {
            'id': id,
            'application_code': application_code,
            'application_key': application_key,
            'state': state
        }

    @http.route('/shop/paymentez/inline_values', type='json', auth='public', website=True, csrf=False)
    def paymentez_inline_values(self):
        """Devuelve el total actual del pedido en minor units (centavos)."""
        order = request.website.sale_get_order()
        if not order:
            return {'error': 'no_order'}
        decimals = getattr(order.currency_id, 'decimal_places', 2) or 2
        minor_amount = int(round(order.amount_total * (10 ** decimals)))
        return {
            'amount': float(order.amount_total),
            'minor_amount': minor_amount,
            'decimals': decimals,
        }