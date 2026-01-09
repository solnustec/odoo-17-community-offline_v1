from odoo import models, fields, api


class ProductsConsumable(models.Model):
    _name = 'allocations.consumable.products'
    _description = 'Productos Consumibles'
    _order = 'name'
    _sql_constraints = [
        ('name_unique', 'unique(name)', 'El nombre del producto debe ser único.'),
    ]

    name = fields.Char(string='Producto', required=True, index=True)

    stock_total = fields.Float(
        string='Stock Disponible',
        compute='_compute_stock_total',
        store=False,
        help='Suma de todas las cantidades disponibles en ingresos de este producto'
    )

    move_history_ids = fields.One2many(
        'allocations.consumable.move.line',
        compute='_compute_move_history',
        string="Historial de Movimientos",
    )

    id_visual = fields.Char(string='Id Visual', required=False, index=True)

    def action_view_moves(self):
        """Abre una vista de los movimientos relacionados a este producto."""
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
        """Calcula el historial de movimientos confirmados del producto."""
        MoveLine = self.env['allocations.consumable.move.line']
        for product in self:
            product.move_history_ids = MoveLine.search([
                ('product_id', '=', product.id),
                ('move_id.state', '=', 'done'),
            ])

    def _compute_stock_total(self):
        """
        Calcula el stock total disponible sumando qty_available de todas las líneas de ingreso.
        Optimizado con read_group para mejor rendimiento.
        """
        IntakeLine = self.env['allocations.consumable.intake.line']

        # Optimización: usar read_group para calcular sumas en una sola consulta
        result = IntakeLine.read_group(
            domain=[('product_id', 'in', self.ids)],
            fields=['qty_available:sum'],
            groupby=['product_id']
        )

        # Crear diccionario de resultados
        stock_by_product = {item['product_id'][0]: item['qty_available'] for item in result}

        # Asignar valores
        for product in self:
            product.stock_total = stock_by_product.get(product.id, 0.0)
