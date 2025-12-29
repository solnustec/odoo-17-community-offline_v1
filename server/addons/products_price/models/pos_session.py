from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()

        result['search_params']['fields'].append('uom_po_factor_inv')
        return result

