from odoo import models, fields, api

class ResPartnerProvider(models.Model):
    _inherit = 'res.partner'

    id_database_old_provider = fields.Char(string="Id base anterior proveedor")