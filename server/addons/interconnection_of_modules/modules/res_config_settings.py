from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    block_transfer_without_stock = fields.Boolean(
        string="Bloquear transferencias sin stock",
        config_parameter="interconnection_of_modules.block_transfer_without_stock",
        help="Evita validar transferencias cuando no existen existencias "
             "disponibles y bloquea la edición de cantidades en operaciones "
             "sin stock.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        param_value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("interconnection_of_modules.block_transfer_without_stock")
        )
        res.update(
            block_transfer_without_stock=param_value in ("True", True, "1", 1),
        )
        return res

    def set_values(self):
        super().set_values()
        self.env["ir.config_parameter"].sudo().set_param(
            "interconnection_of_modules.block_transfer_without_stock",
            bool(self.block_transfer_without_stock),
        )

