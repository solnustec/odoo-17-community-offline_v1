# -*- coding: utf-8 -*-
from odoo import models, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _commercial_fields(self):
        """
        Remover 'vat' de los campos comerciales para que las direcciones
        puedan tener un VAT diferente al del contacto padre
        """
        commercial_fields = super()._commercial_fields()
        if 'vat' in commercial_fields:
            commercial_fields.remove('vat')
            commercial_fields.remove('l10n_latam_identification_type_id')
        return commercial_fields
