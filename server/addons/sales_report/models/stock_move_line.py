from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)





class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._update_sale_summary()
        return record

    def _update_sale_summary(self):
        summary_model = self.env['product.warehouse.sale.summary']
        summary_date = fields.Date.today()

        for line in self:
            picking_type = line.picking_type_id
            is_pos = (
                    picking_type.code == 'outgoing' and
                    picking_type.sequence_code == "POS"
            )
            if not is_pos:
                continue

            product = line.product_id
            warehouse = line.picking_id.picking_type_id.warehouse_id
            if not warehouse or not product:
                continue

            quantity = 0
            sale_price = 0

            if line.location_dest_id.usage == 'customer':
                quantity = line.quantity_product_uom
                sale_price = line.sale_price
            elif line.location_id.usage == 'customer':
                quantity = -line.quantity_product_uom
                sale_price = -line.sale_price

            if abs(sale_price) < 0.0001:
                continue

            summary = summary_model.search([
                ('date', '=', summary_date),
                ('product_id', '=', product.id),
                ('warehouse_id', '=', warehouse.id),
            ], limit=1)

            if summary:
                new_qty = summary.quantity_sold + quantity
                new_amount = summary.amount_total + sale_price

                # Si cantidad llega a 0, eliminar registro
                if abs(new_qty) < 0.0001:
                    summary.unlink()
                else:
                    summary.write({
                        'quantity_sold': new_qty,
                        'amount_total': new_amount,
                    })
            else:
                # Solo crear si hay cantidad real
                if abs(quantity) >= 0.0001:
                    summary_model.create({
                        'date': summary_date,
                        'product_id': product.id,
                        'warehouse_id': warehouse.id,
                        'quantity_sold': quantity,
                        'amount_total': sale_price,
                    })

