# -*- coding: utf-8 -*-

from odoo import fields, models


class PosConfig(models.Model):
    """Inherited pos config for uploading logo image"""
    _inherit = 'pos.config'

    logo = fields.Binary(string='Image', help="Logo del pos")
