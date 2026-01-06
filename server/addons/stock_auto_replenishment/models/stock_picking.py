# -*- coding: utf-8 -*-
"""Extensión de stock.picking para transferencias automáticas."""
from odoo import fields, models


class StockPicking(models.Model):
    """Extensión de stock.picking con campos de reabastecimiento automático."""
    _inherit = 'stock.picking'

    is_auto_replenishment = fields.Boolean(
        string='Transferencia Automática',
        default=False,
        copy=False,
        index=True,
    )
    auto_replenishment_orderpoint_id = fields.Many2one(
        'stock.warehouse.orderpoint',
        string='Regla de Reorden',
        ondelete='set null',
        copy=False,
    )

    def action_view_orderpoint(self):
        """Abre el orderpoint relacionado."""
        self.ensure_one()
        if not self.auto_replenishment_orderpoint_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Regla de Reorden',
            'res_model': 'stock.warehouse.orderpoint',
            'res_id': self.auto_replenishment_orderpoint_id.id,
            'view_mode': 'form',
        }
