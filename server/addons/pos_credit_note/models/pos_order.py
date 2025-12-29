from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    # @api.model
    # def refund(self, order_id=None):
    #     _logger.info("Refund process started for POS order ID: %s", order_id)
    #     order = self.browse(order_id)
    #     _logger.info("Original order data: %s", order.read())
    #
    #     # Call the original refund method
    #     result = super(PosOrder, self).refund(order_id)
    #
    #     _logger.info("Refund result: %s", result)
    #     return result
