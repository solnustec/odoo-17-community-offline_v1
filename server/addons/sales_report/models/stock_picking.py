from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()
        self._update_sale_summary_on_validate()
        return res

    def _update_sale_summary_on_validate(self):
        summary_model = self.env['product.warehouse.sale.summary']
        today = fields.Date.today()

        for picking in self:
            warehouse = picking.picking_type_id.warehouse_id
            if not warehouse:
                continue

            for move_line in picking.move_line_ids:
                product = move_line.product_id
                if not product:
                    continue

                if move_line.location_dest_id.usage == 'customer':
                    qty = move_line.quantity  # Venta
                    sale_price = 0
                elif move_line.location_id.usage == 'customer':
                    qty = -move_line.quantity  # Devolución
                    sale_price = 0
                else:
                    continue  # No afecta ventas

                # Buscar resumen existente
                summary = summary_model.search([
                    ('date', '=', today),
                    ('product_id', '=', product.id),
                    ('warehouse_id', '=', warehouse.id),
                ], limit=1)

                if summary:
                    print(summary.quantity_sold,'summary.quantity_sold')
                    print(qty,'qty')
                    # summary.quantity_sold += qty,
                    # summary.amount_total += sale_price
                else:
                    summary_model.create({
                        'date': today,
                        'product_id': product.id,
                        'warehouse_id': warehouse.id,
                        'quantity_sold': qty,
                        # 'amount_total': sale_price,
                        # 'user_id': self.env.user.id
                    })
