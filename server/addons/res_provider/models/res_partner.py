from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    provider_config = fields.Char(
        string='Provider JSON Info from legacy systems',
        help='JSON field to store additional information from the provider',
        # default=dict,
        # copy=False
    )