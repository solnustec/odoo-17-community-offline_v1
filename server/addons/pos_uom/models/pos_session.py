from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _loader_params_product_product(self):
        """
        Este método modifica los parámetros del cargador de productos en el POS
        para agregar el campo uom_po_id.
        """
        res = super(PosSession, self)._loader_params_product_product()
        
        # Aseguramos que el campo 'uom_po_id' esté presente en los parámetros de búsqueda
        if 'search_params' in res and 'fields' in res['search_params']:
            if 'uom_po_id' not in res['search_params']['fields']:
                res['search_params']['fields'].append('uom_po_id')

        return res


    
