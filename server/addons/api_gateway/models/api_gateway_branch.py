# -*- coding: utf-8 -*-
import logging
import secrets
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ApiGatewayBranch(models.Model):
    """
    Registro de sucursales OFFLINE autorizadas para usar el API Gateway.
    Cada sucursal tiene un código único y una API key para autenticación.
    """
    _name = 'api.gateway.branch'
    _description = 'Sucursal API Gateway'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre descriptivo de la sucursal (ej: Sucursal Loja Centro)'
    )
    code = fields.Char(
        string='Código',
        required=True,
        help='Código único de la sucursal (ej: SUC001, LOJA01)'
    )
    api_key = fields.Char(
        string='API Key',
        readonly=True,
        copy=False,
        help='Clave de autenticación generada automáticamente'
    )
    active = fields.Boolean(default=True)

    # Información adicional
    description = fields.Text(string='Descripción')
    ip_address = fields.Char(
        string='Última IP',
        readonly=True,
        help='Última dirección IP desde donde se conectó'
    )
    last_connection = fields.Datetime(
        string='Última Conexión',
        readonly=True
    )

    # Estadísticas
    request_count = fields.Integer(
        string='Total Requests',
        readonly=True,
        default=0
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'El código de sucursal debe ser único.'),
        ('api_key_unique', 'UNIQUE(api_key)', 'La API key debe ser única.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Genera API key automáticamente al crear."""
        for vals in vals_list:
            if not vals.get('api_key'):
                vals['api_key'] = self._generate_api_key()
        return super().create(vals_list)

    def _generate_api_key(self):
        """Genera una API key segura."""
        return f"gw_{secrets.token_urlsafe(32)}"

    def action_regenerate_api_key(self):
        """Regenera la API key de la sucursal."""
        for record in self:
            record.api_key = self._generate_api_key()
            _logger.info(f'[API Gateway] API key regenerada para sucursal: {record.code}')
        return True

    def update_connection_info(self, ip_address):
        """Actualiza información de conexión."""
        self.ensure_one()
        self.sudo().write({
            'ip_address': ip_address,
            'last_connection': fields.Datetime.now(),
            'request_count': self.request_count + 1,
        })

    @api.model
    def validate_api_key(self, api_key):
        """
        Valida una API key y retorna la sucursal si es válida.

        Returns:
            recordset: La sucursal si la key es válida, False si no
        """
        if not api_key:
            return False

        branch = self.sudo().search([
            ('api_key', '=', api_key),
            ('active', '=', True),
        ], limit=1)

        return branch if branch else False
