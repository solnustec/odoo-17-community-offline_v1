from odoo import models, fields

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    transportista_id = fields.Many2one('res.partner', string='Transportista')
