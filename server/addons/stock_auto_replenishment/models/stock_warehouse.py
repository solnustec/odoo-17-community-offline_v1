# -*- coding: utf-8 -*-
"""Extensión de stock.warehouse para reabastecimiento automático."""
from odoo import api, fields, models


class StockWarehouse(models.Model):
    """Extensión de stock.warehouse con configuración de reabastecimiento."""
    _inherit = 'stock.warehouse'

    auto_replenishment_source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén Origen para Reabastecimiento',
        domain="[('id', '!=', id), ('company_id', '=', company_id)]",
        help='Almacén origen para transferencias automáticas. '
             'Si no se especifica, usa el almacén principal.',
    )
    auto_replenishment_enabled = fields.Boolean(
        string='Habilitar Reabastecimiento Automático',
        default=True,
    )

    def action_view_auto_replenishment_pickings(self):
        """Abre la lista de transferencias automáticas para este almacén."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Transferencias Automáticas - {self.name}',
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [
                ('is_auto_replenishment', '=', True),
                ('location_dest_id', 'child_of', self.view_location_id.id),
            ],
            'context': {'search_default_filter_todo': 1},
        }

    @api.model
    def get_main_warehouse(self, company_id=None):
        """Obtiene el almacén principal de una compañía."""
        if company_id is None:
            company_id = self.env.company.id
        return self.search([
            ('is_main_warehouse', '=', True),
            ('company_id', '=', company_id),
        ], limit=1)

    def get_source_warehouse_for_replenishment(self):
        """Obtiene el almacén origen para reabastecimiento."""
        self.ensure_one()
        if self.auto_replenishment_source_warehouse_id:
            return self.auto_replenishment_source_warehouse_id
        return self.get_main_warehouse(self.company_id.id)
