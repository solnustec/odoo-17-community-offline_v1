from odoo import models, api, _
from odoo.http import request
import re
from odoo.fields import Command
from odoo.exceptions import UserError, ValidationError
from odoo.exceptions import ValidationError
import logging
import time

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _write_vals_from_reward_vals(self, reward_vals, old_lines, delete=True):
        self.ensure_one()
        command_list = []
        for vals, line in zip(reward_vals, old_lines):

            command_list.append((Command.UPDATE, line.id, vals))
        if len(reward_vals) > len(old_lines):
            command_list.extend((Command.CREATE, 0, vals) for vals in reward_vals[len(old_lines):])
        elif len(reward_vals) < len(old_lines) and delete:
            command_list.extend((Command.DELETE, line.id) for line in old_lines[len(reward_vals):])
        self.write({'order_line': command_list})
        return self.env['sale.order.line'] if delete else old_lines[len(reward_vals):]

    def apply_website_promotions(self):
        self.ensure_one()
        self._update_programs_and_rewards()
        self._auto_apply_rewards()
        claimable_rewards = self._get_claimable_rewards()

        if not claimable_rewards:
            return True

        # Iterate over all coupons and their rewards
        for coupon, rewards in claimable_rewards.items():
            if rewards:
                for r in rewards:
                    if not r.multi_product:
                        self._apply_program_reward(r, coupon)

        return True


    def _get_cart_and_free_qty(self, product, line=None):
        """ Get cart quantity and free quantity for given product or line's product.

        Note: self.ensure_one()

        :param ProductProduct product: The product
        :param SaleOrderLine line: The optional line

        se agrega la funcionalidad para que use la boedga del ecomerce al crear la orden
        """
        warehouse_id = self._get_warehouse_available()
        self.ensure_one()
        if not line and not product:
            return 0, 0
        cart_qty = sum(self._get_common_product_lines(line, product).mapped('product_uom_qty'))
        free_qty = (product or line.product_id).with_context(warehouse=warehouse_id).free_qty
        return cart_qty, free_qty


    def _remove_delivery_line(self):
        """Remove delivery products from the sales orders"""
        delivery_lines = self.order_line.filtered("is_delivery")
        if not delivery_lines:
            return
        to_delete = delivery_lines.filtered(lambda x: x.qty_invoiced == 0)
        if not to_delete:
            raise UserError(
                _('You can not update the shipping costs on an order where it was already invoiced!\n\nThe following delivery lines (product, invoiced quantity and price) have already been processed:\n\n')
                + '\n'.join(['- %s: %s x %s' % (line.product_id.with_context(display_default_code=False).display_name, line.qty_invoiced, line.price_unit) for line in delivery_lines])
            )
        to_delete.unlink()

    def _cart_update(self, product_id, line_id=None, add_qty=0, set_qty=0, **kwargs):
        """ Add or set product quantity, add_qty can be negative """
        self.ensure_one()
        self = self.with_company(self.company_id)

        if self.state != 'draft':
            request.session.pop('sale_order_id', None)
            request.session.pop('website_sale_cart_quantity', None)
            raise UserError(_('It is forbidden to modify a sales order which is not in draft status.'))

        product = self.env['product.product'].browse(product_id).exists()
        if add_qty and (not product or not product._is_add_to_cart_allowed()):
            raise UserError(_("The given product does not exist therefore it cannot be added to cart."))

        if line_id is not False:
            order_line = self._cart_find_product_line(product_id, line_id, **kwargs)[:1]
        else:
            order_line = self.env['sale.order.line']

        try:
            if add_qty:
                add_qty = int(add_qty)
        except ValueError:
            add_qty = 1

        try:
            if set_qty:
                set_qty = int(set_qty)
        except ValueError:
            set_qty = 0

        quantity = 0
        if set_qty:
            quantity = set_qty
        elif add_qty is not None:
            if order_line:
                quantity = order_line.product_uom_qty + (add_qty or 0)
            else:
                quantity = add_qty or 0

        if quantity > 0:
            quantity, warning = self._verify_updated_quantity(
                order_line,
                product_id,
                quantity,
                **kwargs,
            )
        else:
            # If the line will be removed anyway, there is no need to verify
            # the requested quantity update.
            warning = ''

        self._remove_delivery_line()

        order_line = self._cart_update_order_line(product_id, quantity, order_line, **kwargs)

        if (
            order_line
            and order_line.price_unit == 0
            and self.website_id.prevent_zero_price_sale
            and product.detailed_type not in self.env['product.template']._get_product_types_allow_zero_price()
        ):
            raise UserError(_(
                "The given product does not have a price therefore it cannot be added to cart.",
            ))

        res = {
            'line_id': order_line.id,
            'quantity': quantity,
            'option_ids': list(set(order_line.option_line_ids.filtered(lambda l: l.order_id == order_line.order_id).ids)),
            'warning': warning,
        }

        if kwargs.get('order_id'):
            order = self.browse(kwargs.get('order_id'))
        else:
            order = request.website.sale_get_order(force_create=True) if request else self.env['sale.order']

        if order and order.state == 'draft':
            order.apply_website_promotions()

        return res


    ## funcion para modificar el nombre de promocion si esta activo venta por cajas
    def _get_reward_values_product(self, reward, coupon, product=None, **kwargs):
        res = super()._get_reward_values_product(reward=reward, coupon=coupon, product=product, **kwargs)

        for item in res:
            product = self.env['product.product'].sudo().browse(item['product_id'])
            if product.sale_uom_ecommerce:
                item['name'] = f"{item['name']} - {product.uom_po_id.name}"

        return res

    ## función que actualiza las lineas de pedido sitio web
    def _cart_update_order_line(self, product_id, quantity, order_line, **kwargs):
        self.ensure_one()

        if order_line and quantity <= 0:
            # Remove zero or negative lines
            if  order_line.is_reward_line:
                raise UserError(_("El producto tiene una recompensa asociada, por lo que no se puede borrar."))
            order_line.unlink()
            order_line = self.env['sale.order.line']
        elif order_line:
            # Update existing line
            update_values = self._prepare_order_line_update_values(order_line, quantity, **kwargs)
            if update_values:
                self._update_cart_line_values(order_line, update_values)
        elif quantity > 0:
            # Create new line
            order_line_values = self._prepare_order_line_values(product_id, quantity, **kwargs)
            order_line = self.env['sale.order.line'].sudo().create(order_line_values)
        return order_line



class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def write(self, vals):
        #cpdigo para actualizar la unidad de medida del producto en la línea de recompensa en producto gratis
        for line in self.reward_id:
            if 'product_uom' in vals and line.reward_type == 'product':
                product_id = self.env['product.product'].browse(vals['product_id'])
                vals['product_uom']= product_id.product_tmpl_id.uom_po_id.id
        result = super(SaleOrderLine, self).write(vals)
        if self.env.context.get('skip_sequence_update'):
            return result
        lines_to_update = self.filtered(
            lambda line: line.order_id.website_id)
        if lines_to_update:
            # Usar un contexto para evitar recursión al actualizar sequence
            lines_to_update.with_context(skip_sequence_update=True).write(
                {'sequence': 10})
        return result

    def _set_shop_warning_stock(self, desired_qty, new_qty):
        self.ensure_one()
        self.shop_warning = _(
            'Has solicitado %(desired_qty)s de %(product_name)s, pero únicamente contamos con %(new_qty)s en stock.',
            desired_qty=int(desired_qty),
            product_name=self.product_id.name,
            new_qty=int(new_qty),
        )

        return self.shop_warning

    @api.model
    def clean_line_name(self):
        name = self.get('name', '') if isinstance(self, dict) else self.name or ''
        return re.sub(r'\[\d+\]\s*', '', name).strip()