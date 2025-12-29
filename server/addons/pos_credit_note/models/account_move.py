from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def create(self, vals):
        if vals.get('move_type') == 'out_refund':
            _logger.info("Credit note creation started with values: %s", vals)
        return super(AccountMove, self).create(vals)
