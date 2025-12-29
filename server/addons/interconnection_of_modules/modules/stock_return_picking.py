from odoo import models, fields, api

class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Almacén",
        domain = [('lot_stock_id.return_location', '=', True)],
        required = True,
    )

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        """Autoseleccionar la ubicacion de acuerdo al almacen seleccionado"""
        if self.warehouse_id:
            self.location_id = self.warehouse_id.lot_stock_id.id
        else:
            self.location_id = False