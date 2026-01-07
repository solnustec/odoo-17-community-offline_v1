# -*- coding: utf-8 -*-
import logging
import json
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ApiGatewayWebhook(models.Model):
    """
    Almacena webhooks recibidos de APIs externas.
    Las sucursales OFFLINE pueden consultar estos webhooks.
    """
    _name = 'api.gateway.webhook'
    _description = 'Webhooks recibidos por API Gateway'
    _order = 'create_date desc'

    name = fields.Char(
        string='Referencia',
        compute='_compute_name',
        store=True
    )
    api_code = fields.Char(
        string='Código API',
        required=True,
        index=True
    )
    transaction_id = fields.Char(
        string='ID Transacción',
        required=True,
        index=True,
        help='ID único de la transacción en la API externa'
    )

    # Datos del webhook
    event_type = fields.Char(
        string='Tipo de Evento',
        help='Tipo de evento recibido (ej: payment_success, payment_failed)'
    )
    payload = fields.Text(
        string='Payload',
        help='Datos JSON recibidos en el webhook'
    )
    headers = fields.Text(
        string='Headers',
        help='Headers HTTP del webhook'
    )

    # Estado
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('processed', 'Procesado'),
        ('synced', 'Sincronizado'),
        ('error', 'Error'),
    ], string='Estado', default='pending', index=True)

    # Sincronización con OFFLINE
    synced_to_branch_ids = fields.Many2many(
        'api.gateway.branch',
        string='Sincronizado a Sucursales',
        help='Sucursales que ya consultaron este webhook'
    )
    sync_date = fields.Datetime(
        string='Fecha Sincronización',
        help='Última vez que fue consultado por una sucursal'
    )

    # Referencia a orden (si aplica)
    order_reference = fields.Char(
        string='Referencia Orden',
        index=True,
        help='Referencia de la orden POS relacionada'
    )

    # Metadatos
    source_ip = fields.Char(string='IP Origen')
    error_message = fields.Text(string='Mensaje de Error')

    @api.depends('api_code', 'transaction_id')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.api_code}/{record.transaction_id}"

    def get_payload_dict(self):
        """Retorna el payload como diccionario."""
        self.ensure_one()
        if not self.payload:
            return {}
        try:
            return json.loads(self.payload)
        except (json.JSONDecodeError, TypeError):
            return {}

    @api.model
    def create_webhook(self, api_code, transaction_id, event_type, payload,
                       headers=None, order_reference=None, source_ip=None):
        """
        Crea o actualiza un registro de webhook.
        Si ya existe uno con el mismo transaction_id, lo actualiza.
        """
        existing = self.sudo().search([
            ('api_code', '=', api_code),
            ('transaction_id', '=', transaction_id),
        ], limit=1)

        vals = {
            'api_code': api_code,
            'transaction_id': transaction_id,
            'event_type': event_type,
            'payload': json.dumps(payload) if isinstance(payload, dict) else payload,
            'headers': json.dumps(headers) if isinstance(headers, dict) else headers,
            'order_reference': order_reference,
            'source_ip': source_ip,
            'state': 'pending',
        }

        if existing:
            existing.write(vals)
            _logger.info(f'[API Gateway] Webhook actualizado: {api_code}/{transaction_id}')
            return existing
        else:
            record = self.sudo().create(vals)
            _logger.info(f'[API Gateway] Webhook creado: {api_code}/{transaction_id}')
            return record

    @api.model
    def get_pending_webhooks(self, api_code, branch_id=None, limit=100):
        """
        Obtiene webhooks pendientes para una sucursal.
        Usado por las sucursales OFFLINE para consultar notificaciones.
        """
        domain = [
            ('api_code', '=', api_code),
            ('state', 'in', ['pending', 'processed']),
        ]

        # Si se especifica branch, excluir los ya sincronizados a esa sucursal
        if branch_id:
            domain.append(('synced_to_branch_ids', 'not in', [branch_id]))

        webhooks = self.sudo().search(domain, limit=limit, order='create_date asc')

        result = []
        for wh in webhooks:
            result.append({
                'id': wh.id,
                'transaction_id': wh.transaction_id,
                'event_type': wh.event_type,
                'payload': wh.get_payload_dict(),
                'order_reference': wh.order_reference,
                'create_date': wh.create_date.isoformat() if wh.create_date else None,
            })

        return result

    def mark_as_synced(self, branch_id):
        """Marca webhooks como sincronizados para una sucursal."""
        branch = self.env['api.gateway.branch'].sudo().browse(branch_id)
        if not branch.exists():
            return False

        for record in self:
            record.synced_to_branch_ids = [(4, branch_id)]
            record.sync_date = fields.Datetime.now()
            if record.state == 'pending':
                record.state = 'processed'

        return True

    @api.autovacuum
    def _gc_old_webhooks(self):
        """Limpia webhooks antiguos sincronizados (más de 7 días)."""
        limit_date = fields.Datetime.subtract(fields.Datetime.now(), days=7)
        old_webhooks = self.sudo().search([
            ('create_date', '<', limit_date),
            ('state', '=', 'synced'),
        ])
        _logger.info(f'[API Gateway] Eliminando {len(old_webhooks)} webhooks antiguos')
        old_webhooks.unlink()
