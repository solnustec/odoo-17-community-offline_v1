from odoo import models, fields


class ResCountryState(models.Model):
    _inherit = 'res.country.state'

    latitude = fields.Char(
        string='Latitud',
        required=True,
        help='Coordenadas geográficas de latitud.',
    )
    longitude = fields.Char(
        string='Longitud',
        required=True,
        help='Coordenadas geográficas de longitud.',
    )

