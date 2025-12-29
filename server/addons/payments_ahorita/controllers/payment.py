from odoo import models
import logging

_logger = logging.getLogger(__name__)

class Payment(models.Model):
    _name = 'payment.payment'
    _description = 'Pago ahorita'

    def get_credentials_json(self):
        secret_base64 = self.env["ir.config_parameter"].sudo().get_param("ahorita_webhook_secret")
        if not secret_base64:
            _logger.error("No se encontró el parámetro del sistema 'ahorita_webhook_secret'")
            return {}

        return {
            "credentials": secret_base64
        }

    def _get_param(self, key, default=""):
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

