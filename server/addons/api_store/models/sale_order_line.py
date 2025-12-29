from odoo import models, fields, api
from odoo.exceptions import UserError


class SaleOrderApp(models.Model):
    _inherit = "sale.order.line"

    reward_prod_id = fields.Integer(string="Reward Product ID")
    reward_discount = fields.Integer(string="Reward Discount Percentage")
    is_delivery_product = fields.Boolean(string="Is Delivery Product", default=False)
    is_claimed_reward = fields.Boolean(string="Is Claimed Reward", default=False)
    is_global_discount = fields.Boolean(string='Descuento Global', default=False)

    additional_discount_applied = fields.Boolean(
        string="Additional discount applied", default=False)
    additional_discount_percent = fields.Float(
        string="Additional discount percent", digits=(5, 2), default=0.0)
    additional_original_discount = fields.Float(
        string="Additional original discount", digits=(5, 4), default=0.0)

    @api.model
    def _check_qty_with_other_quotations(self, warehouse_id, current_quantity_requested):
        """ Verifica la cantidad disponible en stock considerando otras cotizaciones en estado borrador o enviado.
            warehouse_id: ID del almacén para verificar el stock.
            Retorna un diccionario con el mensaje de error si la cantidad solicitada excede el stock disponible.
        """
        self.ensure_one()
        if self.product_id.type != 'product':
            return {}
        # Obtener todas las cotizaciones en estado borrador o enviado que no sean la actual
        other_quotations = self.env['sale.order'].search([
            ('state', 'in', ['draft', 'sent']),
            ('id', '!=', self.order_id.id)
        ])
        # Calcular la cantidad total solicitada en otras cotizaciones para el mismo producto
        total_requested_qty = sum(
            line.product_uom_qty for order in other_quotations for line in order.order_line if
            line.product_id == self.product_id
        )
        # Obtener la cantidad disponible en stock para el producto en el almacén especificado
        available_qty = self.product_id.with_context(warehouse=warehouse_id).qty_available

        # Verificar si la cantidad solicitada en la cotización actual más la cantidad solicitada en otras cotizaciones excede el stock disponible
        if current_quantity_requested > available_qty:
            return False
        return True

    def unlink(self):
        orders = self.mapped('order_id')
        for order in orders:
            if not getattr(order, 'is_order_app', False):
                continue

            normal_lines = order.order_line.filtered(
                lambda l: not l.is_global_discount and not l.reward_id and not l.is_claimed_reward)
            claimed_lines = order.order_line.filtered(lambda l: l.is_claimed_reward)
            lines_to_delete = self.filtered(lambda l: l.order_id == order)
            remaining_after = normal_lines - lines_to_delete
            if not remaining_after and len(claimed_lines) > 0:
                raise UserError(
                    'No se puede eliminar: la orden debe conservar al menos una línea de producto normal.')

        # Si todas las validaciones pasan, proceder con la eliminación
        return super(SaleOrderApp, self).unlink()

    # def unlink(self):
    #     # Guardar órdenes afectadas antes de eliminar las líneas
    #     orders = self.mapped('order_id')
    #     # Ejecutar la eliminación de líneas
    #     res = super(SaleOrderApp, self).unlink()
    #
    #     # Buscar variantes del producto de descuento (DESC-INST)
    #     # discount_variant = self.env['product.product'].sudo().search([('default_code', '=', 'DESC-INST')], limit=1)
    #     # if discount_variant:
    #     #     discount_variant_ids = [discount_variant.id]
    #     # else:
    #         # Si no hay variante con default_code, buscar en template y tomar sus variantes
    #     tpl = self.env['product.template'].sudo().search([('default_code', '=', 'DESC-INST')], limit=1)
    #     discount_variant_id = tpl.product_variant_id.id if tpl else []
    #     print(discount_variant_id,'discount_variant_id')
    #
    #     # Para cada orden afectada, si es `is_order_app` y no quedan líneas de producto reales,
    #     # eliminar las líneas que correspondan al producto de descuento
    #     for order in orders:
    #         if not order.is_order_app:
    #             continue
    #         remaining_product_lines = order.order_line.filtered(lambda l: not l.is_global_discount and not l.is_reward_line)
    #         has_claimed_rewards = order.order_line.filtered(lambda l:  l.is_claimed_reward)
    #         print(remaining_product_lines)
    #         print(has_claimed_rewards,'has_claimed_rewards')
    #         if not remaining_product_lines:
    #             if discount_variant_id:
    #                 lines_to_remove = order.order_line.filtered(lambda l: l.product_id.id == discount_variant_id)
    #                 # if lines_to_remove:
    #                 #     lines_to_remove.sudo().unlink()
    #         ##evitar eliminar produto cuando se aha reclamdomuna recompjesa
    #         claimed_lines = order.order_line.filtered(lambda l: l.is_claimed_reward)
    #         if not claimed_lines:
    #             continue
    #         # Líneas consideradas "normales" (no descuentos globales ni recompensas reclamadas)
    #         normal_lines = order.order_line.filtered(lambda l: not l.is_global_discount and not l.is_claimed_reward)
    #         print(normal_lines,'normal_lines',claimed_lines)
    #         # Líneas que se intentan eliminar de esta orden
    #         lines_to_delete = self.filtered(lambda l: l.order_id == order)
    #         # Lo que quedaría después de la eliminación
    #         remaining_after = normal_lines - lines_to_delete
    #         if not remaining_after:
    #             return None
    #
    #     return res


    # @api.ondelete(at_uninstall=False)
    # def _unlink_except_confirmed(self):
    #     if self._check_line_unlink():
    #         pass
            # raise UserError(_("Once a sales order is confirmed, you can't remove one of its lines (we need to track if something gets invoiced or delivered).\n\
            #     Set the quantity to 0 instead."))