from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mode_strict = fields.Boolean(
        string="Modo estricto",
        default=False,
        help="Habilita la validación de lotes en inventario"
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        mode_strict = self.env['ir.config_parameter'].sudo().get_param(
            'quality_control_stock_oca.mode_strict')

        res.update(
            mode_strict=mode_strict if mode_strict else False,
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'quality_control_stock_oca.mode_strict',
            self.mode_strict)