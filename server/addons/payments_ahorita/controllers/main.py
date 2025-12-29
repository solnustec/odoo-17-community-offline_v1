from odoo import http
from odoo.http import request
import logging, qrcode, base64, json
from io import BytesIO
from qrcode.constants import ERROR_CORRECT_M  # <- nuevo

_logger = logging.getLogger(__name__)


class AhoritaPaymentController(http.Controller):

    @http.route('/ahorita/generate_deeplink', type='json', auth='public', methods=['POST'], csrf=False)
    def generate_deeplink(self, **kwargs):
        if not kwargs:
            try:
                raw = request.httprequest.data.decode('utf-8')
                parsed = json.loads(raw) or {}
                kwargs = parsed
            except Exception as e:
                _logger.error("[Ahorita] Falló parsear JSON manual: %s — raw data: %s",
                              e, request.httprequest.data)

        try:
            payment = request.env['payment.payment'].sudo()
            transaction_id = kwargs.get('transactionId')

            deeplink = payment.generateDeeplink(
                userId=kwargs.get('userId', 415472),
                messageId=kwargs.get('messageId'),
                transactionId=transaction_id,
                deviceId=kwargs.get('deviceId', '127.0.0.1'),
                amount=kwargs.get('amount', 0.0),
            )

            if not deeplink:
                return {'error': 'No se pudo generar el enlace de pago'}

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
            jpeg_bytes = buffer.getvalue()

            qr_base64 = base64.b64encode(jpeg_bytes).decode("utf-8")
            qr_data_url = f"data:image/jpeg;base64,{qr_base64}"

            return {
                'deeplink': {
                    'deeplink': deeplink,
                    'deeplink_id': deeplink.split('?')[-1] if '?' in deeplink else deeplink,
                },
                'transactionId': transaction_id,
                'qr': qr_data_url,
            }

        except Exception as e:
            _logger.error("Error en get_token: %s", str(e))
            return {'error': 'No se pudo generar el enlace de pago'}
