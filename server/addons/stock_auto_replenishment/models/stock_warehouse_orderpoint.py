# -*- coding: utf-8 -*-
"""Extensión de stock.warehouse.orderpoint para reabastecimiento automático."""
from odoo import models, fields, api


class StockWarehouseOrderpoint(models.Model):
    """Extensión de stock.warehouse.orderpoint con acciones de auto replenishment."""
    _inherit = 'stock.warehouse.orderpoint'

    has_pending_queue = fields.Boolean(
        string='En Cola',
        compute='_compute_has_pending_queue',
    )
    hide_order_once = fields.Boolean(
        string='Ocultar Ordenar una vez',
        compute='_compute_hide_order_once',
    )

    @api.depends_context('uid')
    def _compute_hide_order_once(self):
        """Oculta botón 'Ordenar una vez' cuando el módulo está habilitado."""
        ICP = self.env['ir.config_parameter'].sudo()
        enabled = ICP.get_param('stock_auto_replenishment.enabled', 'False') == 'True'
        # Ocultar el botón de Odoo cuando nuestro módulo está habilitado (cualquier modo)
        for op in self:
            op.hide_order_once = enabled

    @api.depends_context('uid')
    def _compute_has_pending_queue(self):
        """Verifica si existe un registro pendiente en la cola."""
        Queue = self.env['product.replenishment.procurement.queue']
        for op in self:
            op.has_pending_queue = bool(Queue.search_count([
                ('orderpoint_id', '=', op.id),
                ('state', '=', 'pending'),
            ], limit=1))

    def action_view_auto_replenishment_pickings(self):
        """Abre la lista de transferencias automáticas."""
        self.ensure_one()
        pickings = self.env['stock.picking'].search([
            ('auto_replenishment_orderpoint_id', '=', self.id),
        ])
        action = {
            'type': 'ir.actions.act_window',
            'name': f'Transferencias - {self.product_id.display_name}',
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [('auto_replenishment_orderpoint_id', '=', self.id)],
        }
        if len(pickings) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = pickings.id
        return action

    def action_view_procurement_queue(self):
        """Abre la cola de procurements para este orderpoint."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Cola - {self.product_id.display_name}',
            'res_model': 'product.replenishment.procurement.queue',
            'view_mode': 'tree,form',
            'domain': [('orderpoint_id', '=', self.id)],
        }

    def action_force_enqueue(self):
        """Encola el orderpoint para procurement (botón "Forzar Transferencia")."""
        self.ensure_one()

        if self.qty_to_order <= 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin necesidad de reabastecimiento',
                    'message': f'qty_to_order = {self.qty_to_order}',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        Queue = self.env['product.replenishment.procurement.queue']
        enqueued = Queue.enqueue_single(self)

        if enqueued:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Encolado',
                    'message': f'{self.product_id.display_name} encolado para procesamiento',
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Ya existe en cola',
                    'message': 'Este orderpoint ya está en cola o fue procesado hoy',
                    'type': 'warning',
                    'sticky': False,
                }
            }
