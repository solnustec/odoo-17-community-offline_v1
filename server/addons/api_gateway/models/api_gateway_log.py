# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ApiGatewayLog(models.Model):
    """
    Log de todas las transacciones que pasan por el gateway.
    Útil para debugging y auditoría.
    """
    _name = 'api.gateway.log'
    _description = 'Log de API Gateway'
    _order = 'create_date desc'

    name = fields.Char(
        string='Referencia',
        compute='_compute_name',
        store=True
    )
    api_config_id = fields.Many2one(
        'api.gateway.config',
        string='API',
        ondelete='set null'
    )
    api_code = fields.Char(string='Código API')

    # Información del request
    request_method = fields.Selection([
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('DELETE', 'DELETE'),
        ('PATCH', 'PATCH'),
    ], string='Método')
    request_endpoint = fields.Char(string='Endpoint')
    request_url = fields.Char(string='URL Completa')
    request_headers = fields.Text(string='Headers (Request)')
    request_body = fields.Text(string='Body (Request)')

    # Información de la respuesta
    response_status = fields.Integer(string='Status Code')
    response_headers = fields.Text(string='Headers (Response)')
    response_body = fields.Text(string='Body (Response)')
    response_time = fields.Float(string='Tiempo de Respuesta (s)')

    # Origen
    source_ip = fields.Char(string='IP Origen')
    source_branch_id = fields.Many2one(
        'api.gateway.branch',
        string='Sucursal Origen',
        ondelete='set null'
    )
    source_user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        ondelete='set null'
    )

    # Estado
    state = fields.Selection([
        ('success', 'Exitoso'),
        ('error', 'Error'),
        ('timeout', 'Timeout'),
    ], string='Estado', default='success')
    error_message = fields.Text(string='Mensaje de Error')

    # Tipo de transacción
    transaction_type = fields.Selection([
        ('proxy', 'Proxy Request'),
        ('webhook', 'Webhook Recibido'),
    ], string='Tipo', default='proxy')

    @api.depends('api_code', 'request_endpoint', 'create_date')
    def _compute_name(self):
        for record in self:
            date_str = record.create_date.strftime('%Y%m%d-%H%M%S') if record.create_date else 'NEW'
            record.name = f"{record.api_code or 'UNKNOWN'}/{date_str}"

    @api.model
    def log_request(self, api_code, method, endpoint, url, headers, body,
                    response_status, response_headers, response_body,
                    response_time, source_ip=None, branch_id=None,
                    user_id=None, error_message=None, transaction_type='proxy'):
        """Crea un registro de log para una transacción."""
        state = 'success'
        if response_status and response_status >= 400:
            state = 'error'
        if error_message and 'timeout' in error_message.lower():
            state = 'timeout'

        # Buscar configuración de API
        api_config = self.env['api.gateway.config'].sudo().search([
            ('code', '=', api_code)
        ], limit=1)

        # Truncar bodies muy grandes
        max_body_size = 50000
        if body and len(str(body)) > max_body_size:
            body = str(body)[:max_body_size] + '... [TRUNCATED]'
        if response_body and len(str(response_body)) > max_body_size:
            response_body = str(response_body)[:max_body_size] + '... [TRUNCATED]'

        return self.sudo().create({
            'api_config_id': api_config.id if api_config else False,
            'api_code': api_code,
            'request_method': method,
            'request_endpoint': endpoint,
            'request_url': url,
            'request_headers': str(headers) if headers else False,
            'request_body': str(body) if body else False,
            'response_status': response_status,
            'response_headers': str(response_headers) if response_headers else False,
            'response_body': str(response_body) if response_body else False,
            'response_time': response_time,
            'source_ip': source_ip,
            'source_branch_id': branch_id,
            'source_user_id': user_id,
            'state': state,
            'error_message': error_message,
            'transaction_type': transaction_type,
        })

    @api.autovacuum
    def _gc_old_logs(self):
        """Limpia logs antiguos (más de 30 días)."""
        limit_date = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        old_logs = self.sudo().search([
            ('create_date', '<', limit_date),
            ('state', '=', 'success'),  # Solo borramos los exitosos
        ])
        _logger.info(f'[API Gateway] Eliminando {len(old_logs)} logs antiguos')
        old_logs.unlink()
