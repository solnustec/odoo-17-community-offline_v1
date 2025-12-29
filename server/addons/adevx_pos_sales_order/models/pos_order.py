from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _generate_pos_order_invoice(self):
        """
        Override para actualizar qty_delivered y qty_invoiced al facturar
        desde el POS cuando la orden viene de un sale.order.
        """
        result = super()._generate_pos_order_invoice()

        # Actualizar sale.order relacionado
        for order in self:
            order._update_sale_order_from_pos_invoice()

        return result

    def _update_sale_order_from_pos_invoice(self):
        """
        Actualiza el sale.order relacionado cuando se factura desde el POS:
        - qty_delivered para productos gratis (reward)
        - qty_invoiced para todas las líneas para que el estado cambie a 'invoiced'
        """
        self.ensure_one()
        sale_order_ids = set()

        # Buscar sale.order relacionado a través de las líneas del pos.order
        for line in self.lines:
            if hasattr(line, 'sale_order_line_id') and line.sale_order_line_id:
                sale_order_ids.add(line.sale_order_line_id.order_id.id)

        if sale_order_ids:
            sale_orders = self.env['sale.order'].browse(list(sale_order_ids))
            for sale_order in sale_orders:
                try:
                    for so_line in sale_order.order_line:
                        # Para productos gratis (reward), actualizar qty_delivered
                        if hasattr(so_line, 'reward_product_id') and so_line.reward_product_id:
                            so_line.sudo().write({
                                'qty_delivered': so_line.product_uom_qty,
                                'qty_invoiced': so_line.product_uom_qty
                            })
                        else:
                            # Para productos normales, solo actualizar qty_invoiced
                            so_line.sudo().write({
                                'qty_invoiced': so_line.product_uom_qty
                            })


                except Exception as e:
                    _logger.warning(f"[adevx_pos_sales_order] Error actualizando sale.order {sale_order.name}: {e}")
