from odoo import http
from odoo.http import request
from ..templates.linkpayadd_flow import LinkPayAddFlow

class WhatsappController(http.Controller):

    @http.route('/send_whatsapp_message', type='json', auth='public', methods=['POST'], csrf=False)
    def send_whatsapp_message(self, phone=None, deeplink=None, amount=None):
        try:
            if not phone:
                return {'error': 'Número de teléfono no recibido.'}

            if not deeplink:
                return {'error': 'No se recibió el enlace de pago (deeplink).'}

            if not amount:
                return {'error': 'No se recibió el valor de pago.'}

            print("variables 22",phone, deeplink, amount)

            LinkPayAddFlow.link_pay_add(phone, deeplink, amount)

            return {'success': True}

        except Exception as e:
            return {'error': str(e)}
