import math
import re as regex
from odoo import models, api, _, fields
from odoo.fields import Command


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def create(self, vals):
        """Override create to process discount lines before sale order creation"""
        if 'order_line' in vals:
            vals['order_line'] = self._process_order_lines_with_discounts(vals['order_line'])
        return super().create(vals)
    
    def write(self, vals):
        """Override write to process discount lines before sale order update"""
        if 'order_line' in vals:
            vals['order_line'] = self._process_order_lines_with_discounts(vals['order_line'])
        return super().write(vals)
    
    def _process_order_lines_with_discounts(self, order_line_commands):
        """Process order line commands to integrate discount lines into product lines"""
        if not order_line_commands:
            return order_line_commands
            
        # Only apply for Ecuador
        if hasattr(self, 'company_id') and self.company_id and self.company_id.country_id.code != 'EC':
            return order_line_commands
        elif not hasattr(self, 'company_id'):
            # For new records, check if we can determine the company
            company = self.env.company
            if company.country_id.code != 'EC':
                return order_line_commands
            
        processed_commands = []
        discount_lines_by_product = {}
        
        # First pass: identify discount lines and regular product lines
        for i, command in enumerate(order_line_commands):
            if command[0] == 0:  # Command.CREATE
                line_vals = command[2]
                
                # Check if this is a discount/reward line
                is_discount_line = (
                    line_vals.get('price_unit', 0) < 0 and (
                        line_vals.get('reward_id') or 
                        line_vals.get('is_reward_line') or
                        line_vals.get('reward_identifier_code') or
                        'descuento' in line_vals.get('name', '').lower() or
                        'discount' in line_vals.get('name', '').lower() or
                        '%' in line_vals.get('name', '')
                    )
                )
                
                if is_discount_line:
                    # Extract discount percentage from name
                    discount_percentage = 0.0
                    line_name = line_vals.get('name', '')
                    
                    match = regex.search(r'(\d+(?:\.\d+)?)%', line_name)
                    if match:
                        discount_percentage = float(match.group(1))
                    
                    # Find the target product - look at the previous non-discount line
                    target_product_id = None
                    for j in range(len(processed_commands) - 1, -1, -1):
                        prev_command = processed_commands[j]
                        if prev_command[0] == 0:  # CREATE command
                            prev_vals = prev_command[2]
                            if (prev_vals.get('price_unit', 0) > 0 and 
                                not prev_vals.get('is_reward_line') and
                                prev_vals.get('product_id')):
                                target_product_id = prev_vals['product_id']
                                break
                    
                    if target_product_id:
                        discount_lines_by_product[target_product_id] = {
                            'discount_amount': abs(line_vals.get('price_unit', 0)),
                            'discount_percentage': discount_percentage,
                            'quantity': line_vals.get('product_uom_qty', 1)
                        }
                    # Don't add discount line to processed_commands
                    continue
            
            processed_commands.append(command)
        
        # Second pass: apply discounts to corresponding product lines
        final_commands = []
        for command in processed_commands:
            if command[0] == 0:  # CREATE command
                line_vals = command[2].copy()
                product_id = line_vals.get('product_id')
                
                if product_id in discount_lines_by_product:
                    discount_info = discount_lines_by_product[product_id]
                    price_unit = line_vals.get('price_unit', 0)
                    quantity = line_vals.get('product_uom_qty', 1)
                    
                    if price_unit > 0:
                        if discount_info['discount_percentage'] > 0:
                            line_vals['discount'] = discount_info['discount_percentage']
                        else:
                            # Calculate percentage from discount amount and quantity
                            total_line_amount = price_unit * quantity
                            if total_line_amount > 0:
                                discount_percentage = (discount_info['discount_amount'] / total_line_amount) * 100
                                line_vals['discount'] = round(discount_percentage, 2)
                        
                        final_commands.append((command[0], command[1], line_vals))
                    else:
                        final_commands.append(command)
                else:
                    final_commands.append(command)
            else:
                final_commands.append(command)
        
        return final_commands

    def _apply_program_reward(self, reward, coupon, **kwargs):
        """Override loyalty program reward application to apply discounts directly to product lines"""
        # Check if we're in Ecuador and dealing with a discount reward
        if (self.company_id.country_id.code == 'EC' and 
            reward.reward_type == 'discount' and 
            reward.discount_applicability == 'specific'):
            
            # Apply discount directly to the target product lines instead of creating separate lines
            target_lines = self._get_reward_applicable_lines(reward)
            if target_lines and reward.discount > 0:
                # Calculate discount percentage
                discount_percentage = reward.discount
                
                # Apply discount to each applicable line
                for line in target_lines:
                    if line.discount < discount_percentage:  # Don't reduce existing discounts
                        line.discount = discount_percentage

                # Fixed: return a dict instead of bool
                return {"success": True}

        # For other cases, use the default behavior
        res = super()._apply_program_reward(reward, coupon, **kwargs)

        # Fixed: ensure we always return a dict
        if isinstance(res, bool):
            return {"success": res} if res else {"error": "Failed to apply reward"}
        return res

    def _get_reward_applicable_lines(self, reward):
        """Get the order lines that are applicable for the reward"""
        applicable_lines = self.env['sale.order.line']
        
        if reward.discount_applicability == 'specific' and reward.discount_product_ids:
            # Find lines with products that match the reward criteria
            product_ids = reward.discount_product_ids.ids
            applicable_lines = self.order_line.filtered(
                lambda line: line.product_id.id in product_ids and not line.is_reward_line
            )
        elif reward.discount_applicability == 'cheapest':
            # Find the cheapest line
            regular_lines = self.order_line.filtered(lambda line: not line.is_reward_line)
            if regular_lines:
                applicable_lines = min(regular_lines, key=lambda line: line.price_unit)
        else:
            # For 'order' applicability, apply to all regular lines
            applicable_lines = self.order_line.filtered(lambda line: not line.is_reward_line)
        
        return applicable_lines

    def _prepare_invoice(self):
        """Override to apply discount logic when creating invoices from sale orders"""
        invoice_vals = super()._prepare_invoice()
        
        # Only apply for Ecuador
        if self.company_id.country_id.code == 'EC':
            invoice_lines = invoice_vals.get('invoice_line_ids', [])
            processed_lines = self._process_discount_lines_for_invoice(invoice_lines)
            invoice_vals['invoice_line_ids'] = processed_lines
            
        return invoice_vals
    
    def _process_discount_lines_for_invoice(self, invoice_line_ids):
        """Process invoice lines to integrate discount lines into product lines"""
        if not invoice_line_ids:
            return invoice_line_ids
            
        processed_lines = []
        discount_lines_by_product = {}
        
        # First pass: identify discount lines and group them by product
        for line_command in invoice_line_ids:
            if line_command[0] == 0:  # Create command
                line_vals = line_command[2]
                sale_line = None
                
                # Get the sale order line
                if 'sale_line_ids' in line_vals:
                    sale_line_ids = line_vals['sale_line_ids']
                    if sale_line_ids and isinstance(sale_line_ids[0], list):
                        # Extract sale line ID from the command tuple
                        sale_line_id = sale_line_ids[0][1] if len(sale_line_ids[0]) > 1 else None
                        if sale_line_id:
                            sale_line = self.env['sale.order.line'].browse(sale_line_id)
                
                # Check if this is a discount line (negative price and has reward_prod_id attribute)
                is_discount_line = (
                    line_vals.get('price_unit', 0) < 0 and
                    sale_line and 
                    hasattr(sale_line, 'reward_prod_id') and 
                    sale_line.reward_prod_id
                )
                
                if is_discount_line:
                    # Extract discount percentage from line name if available
                    discount_percentage = 0.0
                    line_name = line_vals.get('name', '')
                    
                    if line_name:
                        match = regex.search(r'(\d+(?:\.\d+)?)%', line_name)
                        if match:
                            discount_percentage = float(match.group(1))
                    
                    # Store discount information by the product it applies to
                    product_key = sale_line.reward_prod_id.id if sale_line.reward_prod_id else None
                    if product_key:
                        discount_lines_by_product[product_key] = {
                            'discount_amount': abs(line_vals.get('price_unit', 0)),
                            'discount_percentage': discount_percentage,
                            'sale_line': sale_line
                        }
                    # Skip adding this line to processed_lines (it will be integrated)
                    continue
                    
            processed_lines.append(line_command)
        
        # Second pass: apply discounts to corresponding product lines
        for i, line_command in enumerate(processed_lines):
            if line_command[0] == 0:  # Create command
                line_vals = line_command[2]
                
                # Check if this product line has a corresponding discount
                product_id = line_vals.get('product_id')
                if product_id and product_id in discount_lines_by_product:
                    discount_info = discount_lines_by_product[product_id]
                    price_unit = line_vals.get('price_unit', 0)
                    
                    if price_unit > 0:
                        if discount_info['discount_percentage'] > 0:
                            # Use the percentage from the discount line name
                            line_vals['discount'] = discount_info['discount_percentage']
                        else:
                            # Calculate percentage from discount amount
                            discount_percentage = (discount_info['discount_amount'] / price_unit) * 100
                            line_vals['discount'] = round(discount_percentage, 2)
                        
                        # Update the processed line
                        processed_lines[i] = (line_command[0], line_command[1], line_vals)
        
        return processed_lines

_CEIL_FACTOR = 100.0
_ROUND_FACTOR = 10000.0
_PERCENT_DIVISOR = 0.01

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def write(self, vals):
        """Override write to apply adjusted pricing logic."""
        if self.env.context.get('skip_price_adjustment'):
            return super().write(vals)

        result = super().write(vals)

        # Solo procesar si hay campos relevantes
        if not ({'price_unit', 'product_uom_qty', 'discount', 'product_id'} & set(vals)):
            return result

        for line in self:
            if line.reward_id or line.price_unit <= 0 or not line.product_id:
                continue

            # Obtener % de impuesto
            tax_percent = 0.0
            for tax in line.product_id.taxes_id:
                if tax.amount_type == 'percent':
                    tax_percent = float(tax.amount)
                    break

            adjusted_price = self._calculate_adjusted_price(
                line.price_unit,
                line.product_uom_qty,
                line.product_id.uom_po_factor_inv or 1.0,
                line.discount,
                tax_percent
            )

            # Solo escribir si hay cambio
            if abs(adjusted_price - line.price_unit) > 0.0001:
                line.with_context(skip_price_adjustment=True).write({
                    'price_unit': adjusted_price
                })

        return result

    @api.model
    def _calculate_adjusted_price(self, unit_price, quantity, conversion_factor, discount_percent, tax_percent):
        """Calculate adjusted unit price."""
        if conversion_factor < 1.0:
            conversion_factor = 1.0

        discount_factor = 1.0 - discount_percent * _PERCENT_DIVISOR
        tax_factor = 1.0 + tax_percent * _PERCENT_DIVISOR

        net_price = unit_price * discount_factor * tax_factor

        if quantity >= conversion_factor:
            net_price = round(net_price * _ROUND_FACTOR) / _ROUND_FACTOR
        else:
            net_price = math.ceil(net_price * _CEIL_FACTOR) / _CEIL_FACTOR

        price_no_discount = round(
            (net_price / (tax_factor * discount_factor)) * _ROUND_FACTOR
        ) / _ROUND_FACTOR

        return price_no_discount




    def _prepare_invoice_line(self, **optional_values):
        """Override to ensure discount information is properly passed to invoice lines"""
        invoice_line_vals = super()._prepare_invoice_line(**optional_values)

        # For Ecuador, if this line has a discount applied via loyalty programs,
        # make sure it's reflected in the discount field
        if (self.order_id.company_id.country_id.code == 'EC' and
            hasattr(self, 'reward_prod_id') and
            self.reward_prod_id and
            self.discount > 0):
            invoice_line_vals['discount'] = self.discount

        return invoice_line_vals