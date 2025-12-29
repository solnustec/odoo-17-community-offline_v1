from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)


class AhoritaPost(models.Model):
    _name = 'ahorita.post'
    _description = 'Registros de Webhook Ahorita'

    datetime_created = fields.Datetime(string='Fecha de creación', default=fields.Datetime.now)
    deeplink = fields.Char(string='Deeplink')
    data = fields.Json(string='Datos JSON', default=dict)
    status_payment = fields.Char(string='Estado del pago',default='pendiente', help='Estado del pago procesado por Ahorita')
    order_id_name = fields.Char(string="Orden ID", help='Identificador de la orden de pago')
    transactionId = fields.Char(
        string='ID de Transacción',
        help='Identificador único de la transacción'
    )

    # Campo computado para mostrar los datos en formato legible
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
                record.data_text = f"Error al formatear datos: {str(e)}"
                _logger.error("Error al formatear datos JSON: %s", str(e))