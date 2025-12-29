from odoo import models, fields


class JsonStorage(models.Model):
    _inherit = 'json.storage'

    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        index=True,
        help='Related invoice for this JSON storage record. for app mobile store.',
    )
