import json

from odoo import models, fields, api


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    is_mobile_enabled = fields.Boolean(
        string='Habilitado para App Móvil',
        default=False
    )
    prod_mode = fields.Boolean(
        string='Habilitado para Producción',
        help='Habilitar para uso en producción',
        default=False
    )

    mobile_dev_config = fields.Json(
        string='Configuración Móvil (Desarrollo)',
        help='Configuración en formato JSON para la app móvil'
    )
    mobile_prod_config = fields.Json(
        string='Configuración Móvil (Producción)',
        help='Configuración en formato JSON para la app móvil'
    )

    @api.model
    def generate_paymentez_token(self, app_code, app_key):
        import base64
        import hashlib
        import time

        timestamp = str(int(time.time()))
        key_time = app_key + timestamp
        signature = hashlib.sha256(key_time.encode('utf-8')).hexdigest()
        token_str = f"{app_code};{timestamp};{signature}"
        token = base64.b64encode(token_str.encode('utf-8')).decode('utf-8')
        return token

    @api.model
    def get_payment_credentials(self, provider_code):
        """
        Retrieve payment credentials based on the provider code and mode (production or development).

        Args:
            provider_code (str): The code of the payment provider.
            prod_mode (bool): If True, retrieve production credentials; otherwise, development credentials.

        Returns:
            dict: A dictionary containing the payment credentials.
        """
        method = self.env['payment.method'].sudo().search([
            ('code', '=', provider_code),
            ('is_mobile_enabled', '=', True)
        ], limit=1)
        if not method:
            return {}
        config = method.mobile_prod_config if method.prod_mode else method.mobile_dev_config
        return json.loads(config)