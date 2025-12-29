from odoo import models, fields, api
import logging
from odoo.http import request

_logger = logging.getLogger(__name__)

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    # Definir el nuevo campo para almacenar el ID personalizado
    external_id = fields.Char(string='ID Externo')

   
    @api.model
    def get_warehouses_by_external_ids(self, params):
        try:
            warehouse = request.env['stock.warehouse'].sudo().search_read(
                [('external_id', '=', params)],
                ['id'],
                limit=1
            )
            result_query = warehouse[0]['id'] if warehouse else None
            return result_query
        except Exception as e:
            print(e)
