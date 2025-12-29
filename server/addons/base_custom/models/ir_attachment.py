
from odoo import api, fields, models
import logging
_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _post_add_create(self, **kwargs):
        kwargs.pop('tmp_url', None)
        kwargs.pop('temporary_id', None)
        return super()._post_add_create(**kwargs)

