# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    logo = fields.Binary(related="pos_config_id.logo",
                               string="Logo",
                               help="Logo del pos",
                               readonly=False)