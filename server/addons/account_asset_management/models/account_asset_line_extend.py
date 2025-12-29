from odoo import models, api


class AccountAssetLine(models.Model):
    _inherit = "account.asset.line"

    @api.depends("amount", "asset_id", "type", "line_date")
    def _compute_values(self):
        """
        Cálculo corregido para que depreciated_value sea ACUMULADO real
        y remaining_value sea base - acumulado.
        """
        for line in self:
            line.depreciated_value = 0.0
            line.remaining_value = 0.0

        # Filtrar líneas de depreciación
        dlines = self.filtered(lambda l: l.type == "depreciate")
        assets = dlines.mapped("asset_id")

        for asset in assets:
            # Ordenadas
            lines = dlines.filtered(lambda l: l.asset_id == asset).sorted("line_date")

            acumulado = 0.0
            base = asset.depreciation_base

            for dl in lines:
                acumulado += dl.amount
                dl.depreciated_value = acumulado
                dl.remaining_value = base - acumulado
