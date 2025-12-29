from odoo import http
from odoo.http import request


class PosOrderController(http.Controller):

    @http.route('/key_access_sri', type='json', auth='public', cors='*')
    def get_key_access_sri(self, key=None):
        try:
            order = request.env['pos.order'].sudo().search(
                [('access_token', '=', key)], limit=1
            )
            return order.sri_authorization or ''
        except Exception:
            return ''

    # 🔹 Obtener nombre/número de factura
    @http.route('/get_invoice_number', type='json', auth='public', cors='*')
    def get_invoice_number(self, key=None):
        try:
            order = request.env['pos.order'].sudo().search(
                [('access_token', '=', key)], limit=1
            )
            if order.account_move:
                return order.account_move.name or ''
            return ''
        except Exception:
            return ''
