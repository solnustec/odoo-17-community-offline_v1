from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    parent_reference_id = fields.Many2one('res.partner',
                                          help="Referencia de Cliente Padre, para asociar las direcciones de facturación de la app movil",
                                          string="Referencia de Cliente Padre")
    app_reward_points = fields.Float("App móvil Reward Points")
