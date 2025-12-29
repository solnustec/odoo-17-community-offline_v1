import json

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.model
    def _prepare_purchase_order_line(self, product_id, product_qty,
                                     product_uom, company_id, values, po):
        res = super(PurchaseOrderLine, self)._prepare_purchase_order_line(
            product_id, product_qty, product_uom, company_id, values, po
        )

        if po.picking_type_id and po.picking_type_id.warehouse_id:
            warehouse = po.picking_type_id.warehouse_id
            if warehouse.analytic_account_id:
                res['analytic_distribution'] = {
                    str(warehouse.analytic_account_id.id): 100.0
                }

        return res

    @api.onchange('product_id', 'product_qty', 'product_uom')
    def _onchange_product_id(self):
        self.ensure_one()
        """Actualiza la distribución analítica al cambiar el producto, cantidad o unidad de medida."""
        if self.order_id.picking_type_id and self.order_id.picking_type_id.warehouse_id:
            warehouse = self.order_id.picking_type_id.warehouse_id
            if warehouse.analytic_account_id:
                self.analytic_distribution = {
                    str(warehouse.analytic_account_id.id): 100.0
                }
            else:
                raise ValidationError(
                    f"La bodega {warehouse.name} asociada a la orden de compra no tiene una cuenta analítica asignada."
                )
        return None
