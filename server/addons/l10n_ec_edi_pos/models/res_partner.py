from odoo import models, fields, api

class ResPartnerProvider(models.Model):
    _inherit = 'res.partner'

    country_id = fields.Many2one(
        comodel_name='res.country',
        default=lambda self: self.env['res.country'].sudo().search([('code', '=', 'EC')], limit=1).id or False
    )