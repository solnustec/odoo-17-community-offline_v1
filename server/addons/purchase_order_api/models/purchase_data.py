import json
import logging
import ast
import requests
_logger = logging.getLogger(__name__)
from odoo import models, fields, api


class PurchaseData(models.Model):
    _name = 'purchase.data'
    account_move_id = fields.Many2one('account.move', string="Invoice")
    # purchase_order_id = fields.Many2one('purchase.order', string="Purchase Order")
    json_data = fields.Text(string="JSON Data")
    sent = fields.Boolean(string="Sent", default=False)
    active = fields.Boolean(string="Active", default=False)
    sync_date = fields.Datetime(string="Sync Date")
    errors = fields.Char(string="Errors")
    invoice_id = fields.Char(string="Invoice Id")

    @api.model
    def sync_purchase_data(self):

        api_url = self.env['ir.config_parameter'].sudo().get_param(
            'url_api_create_order_in_system_visual')
        headers = {
            "Content-Type": "application/json",
            'Authorization': 'Bearer ' + 'cuxiloja2025__'
        }
        purchase_data = self.env['purchase.data'].search([('active', '=', True), ('sent', '=', False)])

        for record in purchase_data:
            try:
                # 1. Parsear JSON de forma segura (soporta ambos formatos)
                try:
                    data_dict = ast.literal_eval(record.json_data)
                except (ValueError, TypeError) as e:
                    record.errors = f"Error parseando JSON: {str(e)}"
                    _logger.error(f"Record {record.id}: Error parseando JSON - {e}")
                    continue

                # 2. Realizar petición con manejo de excepciones
                try:
                    response = requests.post(
                        api_url,
                        json=data_dict,
                        headers=headers,
                        timeout=30
                    )
                except requests.exceptions.Timeout:
                    record.errors = "Timeout: El servidor no respondió a tiempo"
                    _logger.warning(f"Record {record.id}: Timeout en la petición")
                    continue
                except requests.exceptions.ConnectionError:
                    record.errors = "Error de conexión con el servidor"
                    _logger.error(f"Record {record.id}: Error de conexión")
                    continue
                except requests.exceptions.RequestException as e:
                    record.errors = f"Error en la petición: {str(e)}"
                    _logger.error(f"Record {record.id}: RequestException - {e}")
                    continue

                # 3. Procesar respuesta
                if response.status_code in (200, 201):
                    try:
                        data = response.json()
                    except json.JSONDecodeError:
                        record.errors = f"Respuesta no es JSON válido: {response.text[:200]}"
                        _logger.error(f"Record {record.id}: Respuesta no es JSON válido")
                        continue

                    # 4. Extraer ID de forma segura
                    po_id = data.get('po', {}).get('ID')
                    if not po_id:
                        record.errors = f"Respuesta sin ID de PO: {response.text[:200]}"
                        _logger.warning(f"Record {record.id}: Respuesta sin ID de PO")
                        continue

                    # 5. Actualizar registro exitoso
                    record.write({
                        'invoice_id': po_id,
                        'sent': True,
                        'sync_date': fields.Datetime.now(),
                        'errors': False,
                    })
                    _logger.info(f"Record {record.id}: Sincronizado exitosamente - PO ID: {po_id}")

                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:500]}"
                    record.errors = error_msg
                    _logger.error(f"Record {record.id}: {error_msg}")

            except Exception as e:
                record.errors = f"Error inesperado: {str(e)}"
                _logger.exception(f"Record {record.id}: Error inesperado")
