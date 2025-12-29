# -*- coding: utf-8 -*-

from odoo import models, fields


class IrModelFields(models.Model):

    _inherit = 'ir.model.fields'

    is_dynamic_field = fields.Boolean(string="Dynamic Field",
                                      help="To filter dynamically"
                                           " created fields")
