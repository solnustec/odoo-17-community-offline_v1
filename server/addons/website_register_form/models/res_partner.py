# -*- coding: utf-8 -*-

from odoo import models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _signup_fields(self):
        fields = super()._signup_fields()
        fields.append('vat')
        fields.append('l10n_latam_identification_type_id')
        return fields
