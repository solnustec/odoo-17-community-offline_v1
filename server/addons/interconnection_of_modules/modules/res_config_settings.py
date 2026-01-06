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

    sync_transfer_without_moves = fields.Boolean(
        string="Sincronizar transferencias sin mover stock",
        help="Cuando está activo, las transferencias externas se registran "
             "sin validar el picking (no se mueve el stock). Útil para "
             "sincronización con sistemas externos.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env["ir.config_parameter"].sudo()

        block_param = ICP.get_param(
            "interconnection_of_modules.block_transfer_without_stock"
        )
        sync_param = ICP.get_param(
            "stock.sync_transfer_without_moves"
        )

        res.update(
            block_transfer_without_stock=block_param in ("True", True, "1", 1),
            sync_transfer_without_moves=sync_param in ("True", True, "1", 1),
        )
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env["ir.config_parameter"].sudo()

        ICP.set_param(
            "interconnection_of_modules.block_transfer_without_stock",
            bool(self.block_transfer_without_stock),
        )
        ICP.set_param(
            "stock.sync_transfer_without_moves",
            bool(self.sync_transfer_without_moves),
        )

