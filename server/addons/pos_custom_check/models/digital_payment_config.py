from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DigitalPaymentConfig(models.Model):
    _name = 'digital.payment.config'
    _description = 'Digital Payment Configuration'

    bank_name = fields.Char(string='Identificativo', required=True, help='Name of the associated bank')
    bank_id = fields.Many2one(
        comodel_name='res.bank',
        string='Banco Relacionado',
        help='Banco de Odoo relacionado con esta configuración'
    )
    is_production = fields.Boolean(string='Production Environment', default=False,
                                   help='Toggle between test and production environments')
    enable_advanced_payments = fields.Boolean(string='Habilitar Pagos Avanzados', default=False,
                                              help='Enable advanced payment features like WhatsApp messaging and QR code support')
    # Test environment fields
    test_request_payment_url = fields.Char(string='Test Request Payment URL',
                                           help='URL for the test environment payment request')
    test_payment_status_url = fields.Char(string='Test Payment Status URL',
                                          help='URL for the test environment payment status')
    test_api_key = fields.Char(string='Test API Key', help='API key for the test environment')
    test_api_secret = fields.Char(string='Test API Secret', help='API secret for the test environment')

    # Production environment fields
    prod_request_payment_url = fields.Char(string='Production Request Payment URL',
                                           help='URL for the production environment payment request')
    prod_payment_status_url = fields.Char(string='Production Payment Status URL',
                                          help='URL for the production environment payment status')
    prod_api_key = fields.Char(string='Production API Key', help='API key for the production environment')
    prod_api_secret = fields.Char(string='Production API Secret', help='API secret for the production environment')

    # Ahorita Params
    ahorita_deeplink_url = fields.Char(string="Ahorita DeepLink URL",)
    ahorita_generate_url = fields.Char(string="Ahorita Generate URL",
                                       help="URL para generar una transacción Ahorita")
    ahorita_query_url = fields.Char(string="Ahorita Query URL",)
    ahorita_token_url = fields.Char(string="Ahorita Token URL",
                                    help="URL para obtener el token de autenticación")
    ahorita_webhook_secret = fields.Char(string="Ahorita Webhook Secret",
                                         help="Clave secreta usada para verificar las llamadas webhook")


    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'The configuration name must be unique.'),
        ('bank_name_unique', 'UNIQUE(bank_name)', 'The bank name must be unique.')
    ]

    @api.constrains('test_request_payment_url', 'test_payment_status_url', 'test_api_key', 'test_api_secret',
                    'prod_request_payment_url', 'prod_payment_status_url', 'prod_api_key', 'prod_api_secret')
    def _check_urls_and_credentials(self):
        for record in self:
            if record.is_production:
                if not all([record.prod_request_payment_url, record.prod_payment_status_url,
                            record.prod_api_key, record.prod_api_secret]):
                    raise ValidationError(
                        'All production fields (URL, API Key, API Secret) must be filled when using production environment.')
            else:
                if not all([record.test_request_payment_url, record.test_payment_status_url,
                            record.test_api_key, record.test_api_secret]):
                    raise ValidationError(
                        'All test fields (URL, API Key, API Secret) must be filled when using test environment.')

    @api.model
    def get_enable_digital_payment(self):
        banks = self.env['digital.payment.config'].search([('enable_advanced_payments', '=', True)])
        list_bank_enable_advanced_payments = []

        if banks:
            for data in banks:
                list_bank_enable_advanced_payments.append({
                    "id_bank": data.bank_id.id if data.bank_id else False,
                    "bank_name": data.bank_name,
                    "enable_advanced_payments": data.enable_advanced_payments,
                })
            return list_bank_enable_advanced_payments
        else:
            return {
                "error": "No se encontraron bancos habilitados."
            }
