# -*- coding: utf-8 -*-
from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _create_asset(self):
        """Extiende la creación de activos para vincular correctamente el product.template"""
        assets = super()._create_asset()

        for line, asset in zip(self, assets):
            if line.product_id and asset:
                # Forzar siempre que se guarde el product.template
                asset.write({
                    "product_id": line.product_id.product_tmpl_id.id,
                    "name": line.product_id.name,  # sincronizar nombre
                })

        return assets
