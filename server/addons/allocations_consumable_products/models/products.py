from odoo import models, fields, api


class ProductsConsumable(models.Model):
    _name = 'allocations.consumable.products'
    _description = 'ProductsConsumable'

    name = fields.Char(string='Producto', required=True)

    stock_total = fields.Float(
        string='Stock Disponible',
        compute='_compute_stock_total',
        store=False,
    )

    move_history_ids = fields.One2many(
        'allocations.consumable.move.line',
        compute='_compute_move_history',
        string="Historial de Movimientos",
    )

    id_visual = fields.Char(string='Id Visual', required=False)
    def action_view_moves(self):
        self.ensure_one()
        return {
            'name': f"Movimientos de {self.name}",
            'type': 'ir.actions.act_window',
            'res_model': 'allocations.consumable.move.line',
            'view_mode': 'tree,form',
            'views': [
                (self.env.ref('allocations_consumable_products.view_consumable_move_line_tree').id, 'tree'),
                (False, 'form')
            ],
            'domain': [('product_id', '=', self.id)],
            'context': {'default_product_id': self.id},
        }

    @api.depends()
    def _compute_move_history(self):
        MoveLine = self.env['allocations.consumable.move.line']
        for product in self:
            product.move_history_ids = MoveLine.search([
                ('product_id', '=', product.id),
                ('move_id.state', '=', 'done'),
            ])

    @api.depends()
    def _compute_stock_total(self):
        IntakeLine = self.env['allocations.consumable.intake.line']

        for product in self:
            # Buscar todas las líneas donde aparezca este producto
            lines = IntakeLine.search([('product_id', '=', product.id)])

            # Sumar cantidades disponibles
            product.stock_total = sum(lines.mapped('qty_available'))
