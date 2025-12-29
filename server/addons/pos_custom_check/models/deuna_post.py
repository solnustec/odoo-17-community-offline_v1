from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)


class DeunaPost(models.Model):
    _name = 'deuna.post'
    _description = 'Registros de Webhook Deuna'

    datetime_created = fields.Datetime(string='Fecha de creación', default=fields.Datetime.now)
    transactionId = fields.Char(string='ID de Transacción')
    order_id_name = fields.Char(string='Orden ID')
    status_payment = fields.Char(string='Estado del pago', default='pendiente')
    data = fields.Json(string='Datos JSON', default=dict)

    data_text = fields.Text(
        string='Datos Formateados',
        compute='_compute_data_text',
        store=False
    )

    @api.depends('data')
    def _compute_data_text(self):
        for record in self:
            try:
                record.data_text = json.dumps(record.data, indent=4, ensure_ascii=False) if record.data else ''
            except Exception as e:
                _logger.error("Error al formatear datos JSON: %s", str(e))
                record.data_text = f"Error: {str(e)}"
