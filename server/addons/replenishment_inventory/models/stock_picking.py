from odoo import models, fields, api, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def create(self, vals):
         stock_picking = super(StockPicking, self).create(vals)
         stock_picking.action_confirm()
         return stock_picking