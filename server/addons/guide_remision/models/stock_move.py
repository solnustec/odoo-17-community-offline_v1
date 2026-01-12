from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import float_round


class StockMove(models.Model):
    _inherit = 'stock.move'

    bulto = fields.Char(string="Bulto", default="1")
    stock_product = fields.Float(string="Stock Disponible", readonly=True)
    name = fields.Char(string="Description", required=True, default="Stock Move")
    picking_type_code = fields.Selection(
        selection=[
            ('incoming', 'Receipt'),
            ('outgoing', 'Delivery'),
            ('internal', 'Internal Transfer')
        ],
        string='Código del Tipo de Operación',
        related='picking_type_id.code',
        store=False,
    )

    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
        readonly=True
    )

    total_line = fields.Monetary(
        string="Total",
        compute="_compute_total_line",
        store=True,
        currency_field="currency_id"
    )

    @api.depends('product_uom_qty', 'product_id.list_price')
    def _compute_total_line(self):
        for move in self:
            product = move.product_id

            # Precio sin impuestos
            base_price = product.list_price or 0.0

            # Aplicar impuestos configurados en el producto
            taxes = product.taxes_id.compute_all(
                base_price,
                currency=move.company_id.currency_id,
                quantity=1.0,
                product=product,
                partner=False
            )

            # Precio unitario + IVA
            final_price_with_tax = taxes['total_included']

            # Total de la línea
            move.total_line = float_round(
                final_price_with_tax * move.product_uom_qty,
                precision_rounding=move.company_id.currency_id.rounding
            )

    @api.onchange('product_id', 'location_id')
    def _onchange_product_id(self):
        for move in self:
            if move.product_id and move.location_id:
                stock_quant = self.env['stock.quant'].search([
                    ('product_id', '=', move.product_id.id),
                    ('location_id', '=', move.location_id.id)
                ], limit=1)
                move.stock_product = stock_quant.inventory_quantity_auto_apply - stock_quant.reserved_quantity if stock_quant else 0
            else:
                move.stock_product = 0.0

    def _update_stock_product(self):
        """Método auxiliar para actualizar stock_product basado en product_id y location_id"""
        for move in self:
            if move.product_id and move.location_id:
                stock_quant = self.env['stock.quant'].search([
                    ('product_id', '=', move.product_id.id),
                    ('location_id', '=', move.location_id.id)
                ], limit=1)
                move.stock_product = stock_quant.inventory_quantity_auto_apply - stock_quant.reserved_quantity if stock_quant else 0
            else:
                move.stock_product = 0.0
    #
    # @api.onchange('product_uom_qty')
    # def _onchange_product_uom_qty(self):
    #     """Validar que la cantidad no supere el stock disponible"""
    #     for record in self:
    #         if record.product_uom_qty > record.stock_product:
    #             raise UserError(
    #                 f'La cantidad solicitada supera el stock disponible. Solo hay {record.stock_product} unidades en inventario.'
    #             )

    # @api.onchange('quantity')
    # def _onchange_quantity(self):
    #     """Validar que la cantidad no supere el stock disponible"""
    #     for record in self:
    #         if record.quantity > record.stock_product:
    #             raise UserError(
    #                 f'La cantidad solicitada supera el stock disponible. Solo hay {record.stock_product} unidades en inventario.'
    #             )
