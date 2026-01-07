# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ApiGatewayConfig(models.Model):
    """
    Configuración de APIs permitidas para el gateway.
    Define qué APIs externas pueden ser accedidas a través del proxy.
    """
    _name = 'api.gateway.config'
    _description = 'Configuración de API Gateway'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre identificador de la API (ej: ahorita, deuna, whatsapp)'
    )
    code = fields.Char(
        string='Código',
        required=True,
        help='Código único para identificar la API en las llamadas'
    )
    description = fields.Text(string='Descripción')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    # Configuración de URLs
    base_url = fields.Char(
        string='URL Base',
        help='URL base de la API externa (ej: https://api.ahorita.com)'
    )
    allowed_endpoints = fields.Text(
        string='Endpoints Permitidos',
        help='Lista de endpoints permitidos, uno por línea. Usar * para permitir todos.'
    )

    # Autenticación
    auth_type = fields.Selection([
        ('none', 'Sin autenticación'),
        ('api_key', 'API Key'),
        ('bearer', 'Bearer Token'),
        ('basic', 'Basic Auth'),
        ('custom', 'Personalizado'),
    ], string='Tipo de Autenticación', default='none')

    api_key_header = fields.Char(
        string='Header API Key',
        default='x-api-key',
        help='Nombre del header para la API key'
    )
    api_key_value = fields.Char(string='API Key')
    api_secret_header = fields.Char(
        string='Header API Secret',
        default='x-api-secret'
    )
    api_secret_value = fields.Char(string='API Secret')

    # Configuración de seguridad
    allowed_branch_ids = fields.Many2many(
        'api.gateway.branch',
        string='Sucursales Permitidas',
        help='Dejar vacío para permitir todas las sucursales'
    )
    require_api_key = fields.Boolean(
        string='Requiere API Key del OFFLINE',
        default=True,
        help='Si está activo, las sucursales deben enviar su API key para usar este endpoint'
    )

    # Timeouts
    timeout = fields.Integer(
        string='Timeout (segundos)',
        default=30,
        help='Tiempo máximo de espera para la respuesta de la API'
    )

    # Configuración de webhook
    webhook_enabled = fields.Boolean(
        string='Recibe Webhooks',
        default=False,
        help='Si está activo, este gateway puede recibir webhooks de la API externa'
    )
    webhook_path = fields.Char(
        string='Path del Webhook',
        help='Path donde se recibirán los webhooks (ej: /api_gateway/webhook/ahorita)'
    )
    webhook_secret = fields.Char(
        string='Webhook Secret',
        help='Clave secreta para validar los webhooks entrantes'
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'El código de la API debe ser único.')
    ]

    def get_headers(self):
        """Retorna los headers de autenticación configurados."""
        self.ensure_one()
        headers = {'Content-Type': 'application/json'}

        if self.auth_type == 'api_key':
            if self.api_key_header and self.api_key_value:
                headers[self.api_key_header] = self.api_key_value
            if self.api_secret_header and self.api_secret_value:
                headers[self.api_secret_header] = self.api_secret_value

        elif self.auth_type == 'bearer' and self.api_key_value:
            headers['Authorization'] = f'Bearer {self.api_key_value}'

        return headers

    def is_endpoint_allowed(self, endpoint):
        """Verifica si un endpoint está permitido."""
        self.ensure_one()
        if not self.allowed_endpoints:
            return True

        allowed = [e.strip() for e in self.allowed_endpoints.split('\n') if e.strip()]
        if '*' in allowed:
            return True

        for pattern in allowed:
            if pattern.endswith('*'):
                if endpoint.startswith(pattern[:-1]):
                    return True
            elif endpoint == pattern:
                return True

        return False
