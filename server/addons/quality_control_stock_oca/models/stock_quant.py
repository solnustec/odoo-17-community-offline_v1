from odoo import api, fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    active = fields.Boolean(
        default=True, string="Active",
    )

    @api.model_create_multi
    def create(self, val_list):
        # Obtener el parámetro mode_strict desde la configuración
        mode_strict = self.env['ir.config_parameter'].sudo().get_param(
            'quality_control_stock_oca.mode_strict', default=False
        )

        if mode_strict:
            for val in val_list:
                # Verificar si tiene ubicación y si Ubicación de reabastecimiento es True
                if 'location_id' in val and val['location_id']:
                    location = self.env['stock.location'].sudo().browse(val['location_id'])
                    if location.replenish_location:
                        val['active'] = False

        return super().create(val_list)
