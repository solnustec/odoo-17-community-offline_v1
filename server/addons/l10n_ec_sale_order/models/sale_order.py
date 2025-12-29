# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
import re

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _find_global_discount_lines(self):
        """
        Finds global discount lines in the sale order
        Identifies by product name OR line description
        Extracts percentage from discount field or description
        """
        global_discount_lines = []
        
        for line in self.order_line:
            if not line.product_id:
                continue
                
            product_name = (line.product_id.name or '').lower()
            line_description = (line.name or '').lower()
            
            # Discount product indicators
            discount_indicators = [
                'descuento', 'desconto', 'discount', 'desc.',
                'rebaja', 'rebate', 'reduccion', 'redução',
                'promocion', 'promoção', 'promotion'
            ]
            
            # Special prefixes
            discount_prefixes = ['[disc]', '[desc]', '[descuento]', '[desconto]']
            
            # Check if it's a discount product by name OR description
            is_discount_product = any(indicator in product_name for indicator in discount_indicators)
            has_discount_prefix = any(prefix in product_name for prefix in discount_prefixes)
            is_discount_description = any(indicator in line_description for indicator in discount_indicators)
            
            # Check if line has discount indicators
            if not (is_discount_product or has_discount_prefix or is_discount_description):
                continue
            
            # Global discount if:
            # 1. Has discount field filled (line.discount > 0)
            # 2. OR has percentage in description (e.g., "Descuento Institucional 5%")
            # 3. AND price is >= 0 (not a negative discount line)
            
            has_percentage_in_description = bool(re.search(r'\d+(?:\.\d+)?%', line_description))
            
            if (line.discount > 0 or has_percentage_in_description) and line.price_unit >= 0:
                _logger.info(f"Global discount found in SO: {line.name} (Product: {product_name}) with discount field: {line.discount}%")
                global_discount_lines.append(line)
        
        return global_discount_lines

    def _apply_global_discount_to_products(self, global_discount_percentage):
        """
        Applies global discount to all product lines in the order
        Only adds to existing discount if there's already a discount applied
        """
        _logger.info(f"Applying {global_discount_percentage}% global discount to products in SO {self.name}")
        
        for line in self.order_line:
            if (line.product_id and 
                line.price_unit > 0 and 
                not self._is_discount_line_so(line)):
                
                current_discount = line.discount or 0
                
                # Only add to existing discount if it's NOT the same as the global discount
                # This prevents double application (5% + 5% = 10%)
                if current_discount == 0:
                    # No discount yet, apply the global discount
                    new_discount = global_discount_percentage
                    _logger.info(f"SO Line {line.product_id.name}: applying {new_discount}% (was {current_discount}%)")
                elif current_discount != global_discount_percentage:
                    # Has a different discount, add them
                    new_discount = current_discount + global_discount_percentage
                    _logger.info(f"SO Line {line.product_id.name}: {current_discount}% + {global_discount_percentage}% = {new_discount}%")
                else:
                    # Already has the same discount, skip to avoid duplication
                    _logger.info(f"SO Line {line.product_id.name}: already has {current_discount}% - skipping")
                    continue
                
                new_discount = min(new_discount, 100.0)  # Maximum 100%
                line.write({'discount': new_discount})

    def _is_discount_line_so(self, line):
        """
        Checks if a SO line is a discount line
        Checks both product name AND line description
        """
        if not line.product_id:
            return False
            
        product_name = (line.product_id.name or '').lower()
        line_description = (line.name or '').lower()
        
        discount_indicators = [
            'descuento', 'desconto', 'discount', 'desc.',
            'promocion', 'promoção', 'promotion',
            'rebaja', 'rebate', 'reduccion', 'redução'
        ]
        
        discount_prefixes = ['[disc]', '[desc]', '[descuento]', '[desconto]']
        
        is_discount_product = any(indicator in product_name for indicator in discount_indicators)
        has_discount_prefix = any(prefix in product_name for prefix in discount_prefixes)
        is_discount_description = any(indicator in line_description for indicator in discount_indicators)
        
        # Also check if has percentage in description
        has_percentage_in_description = bool(re.search(r'\d+(?:\.\d+)?%', line_description))
        
        return (is_discount_product or has_discount_prefix or is_discount_description or 
                has_percentage_in_description or line.price_unit < 0)

    def _prepare_invoice(self):
        """
        Override to process global discounts before creating the invoice
        """
        _logger.info(f"Preparing invoice for SO {self.name}")
        
        # Find global discount lines
        global_discount_lines = self._find_global_discount_lines()
        
        if global_discount_lines:
            _logger.info(f"Found {len(global_discount_lines)} global discount lines")
            
            # Check if discounts were already applied (products already have discount > 0)
            products_already_discounted = any(
                line.discount > 0 
                for line in self.order_line 
                if line.product_id and not self._is_discount_line_so(line)
            )
            
            if products_already_discounted:
                _logger.info("Global discounts already applied to products - skipping reapplication")
            else:
                # Extract unique discount percentages (avoid duplicates)
                global_discount_percentages = set()
                
                for discount_line in global_discount_lines:
                    # Try to get from discount field
                    discount_value = discount_line.discount or 0
                    
                    # If not in discount field, extract from description
                    if discount_value <= 0:
                        line_description = discount_line.name or ''
                        percentage_match = re.search(r'(\d+(?:\.\d+)?)%', line_description)
                        if percentage_match:
                            discount_value = float(percentage_match.group(1))
                            _logger.info(f"Extracted {discount_value}% from description: {line_description}")
                    
                    if discount_value > 0:
                        global_discount_percentages.add(discount_value)
                        _logger.info(f"Global discount line: {discount_line.name} - {discount_value}%")
                
                # Calculate total - if all are the same, use only once
                if len(global_discount_percentages) == 1:
                    total_global_discount = list(global_discount_percentages)[0]
                    _logger.info(f"All global discounts are {total_global_discount}% - applying once")
                elif len(global_discount_percentages) > 1:
                    total_global_discount = sum(global_discount_percentages)
                    _logger.info(f"Multiple different global discounts - summing to {total_global_discount}%")
                else:
                    total_global_discount = 0
                
                # Limit to 100%
                total_global_discount = min(total_global_discount, 100.0)
                
                if total_global_discount > 0:
                    _logger.info(f"Applying consolidated global discount of {total_global_discount}% to products")
                    self._apply_global_discount_to_products(total_global_discount)
        
        # Call original method to create the invoice
        return super()._prepare_invoice()

    def debug_discount_detection(self):
        """
        Debug method - checks how each line is being detected
        """
        _logger.info(f"=== DEBUG DISCOUNT DETECTION FOR SO {self.name} ===")
        for line in self.order_line:
            product_name = line.product_id.name if line.product_id else 'NO PRODUCT'
            line_description = line.name or 'NO NAME'
            is_discount = self._is_discount_line_so(line)
            
            _logger.info(f"Line: {line_description}")
            _logger.info(f"  - Product: {product_name}")
            _logger.info(f"  - Unit price: {line.price_unit}")
            _logger.info(f"  - Discount %: {line.discount}")
            _logger.info(f"  - Is discount line: {is_discount}")
            print(f"Line: {line_description} | Product: {product_name} | Price: {line.price_unit} | Disc%: {line.discount} | Is discount: {is_discount}")
        
        return True

    def apply_global_discounts_manually(self):
        """
        Method to apply global discounts manually (can be called via button or action)
        """
        _logger.info(f"Manual global discount application started for SO {self.name}")
        
        # First do debug
        self.debug_discount_detection()
        
        # Find global discount lines
        global_discount_lines = self._find_global_discount_lines()
        
        if global_discount_lines:
            # Extract unique discount percentages
            global_discount_percentages = set()
            
            for discount_line in global_discount_lines:
                discount_value = discount_line.discount or 0
                
                # Extract from description if not in discount field
                if discount_value <= 0:
                    line_description = discount_line.name or ''
                    percentage_match = re.search(r'(\d+(?:\.\d+)?)%', line_description)
                    if percentage_match:
                        discount_value = float(percentage_match.group(1))
                        _logger.info(f"Extracted {discount_value}% from: {line_description}")
                
                if discount_value > 0:
                    global_discount_percentages.add(discount_value)
                    _logger.info(f"Found global discount: {discount_line.name} - {discount_value}%")
            
            # Calculate total - if all are the same, use only once
            if len(global_discount_percentages) == 1:
                total_global_discount = list(global_discount_percentages)[0]
                _logger.info(f"All global discounts are {total_global_discount}% - applying once")
            elif len(global_discount_percentages) > 1:
                total_global_discount = sum(global_discount_percentages)
                _logger.info(f"Multiple different discounts - summing to {total_global_discount}%")
            else:
                total_global_discount = 0
            
            # Limit to 100%
            total_global_discount = min(total_global_discount, 100.0)
            
            if total_global_discount > 0:
                self._apply_global_discount_to_products(total_global_discount)
                _logger.info(f"Applied consolidated global discount of {total_global_discount}%")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Descontos Globais Aplicados',
                'message': f'Aplicado desconto global total de {total_global_discount}% para SO {self.name}',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_confirm(self):
        """
        Override to process global discounts when order is confirmed
        """
        # Process global discounts before confirmation
        for order in self:
            global_discount_lines = order._find_global_discount_lines()
            
            if global_discount_lines:
                # Extract unique discount percentages
                global_discount_percentages = set()
                
                for line in global_discount_lines:
                    discount_value = line.discount or 0
                    
                    # Extract from description if not in discount field
                    if discount_value <= 0:
                        line_description = line.name or ''
                        percentage_match = re.search(r'(\d+(?:\.\d+)?)%', line_description)
                        if percentage_match:
                            discount_value = float(percentage_match.group(1))
                    
                    if discount_value > 0:
                        global_discount_percentages.add(discount_value)
                
                # Calculate total - if all are the same, use only once
                if len(global_discount_percentages) == 1:
                    total_global_discount = list(global_discount_percentages)[0]
                elif len(global_discount_percentages) > 1:
                    total_global_discount = sum(global_discount_percentages)
                else:
                    total_global_discount = 0
                
                total_global_discount = min(total_global_discount, 100.0)
                
                if total_global_discount > 0:
                    _logger.info(f"Auto-applying {total_global_discount}% global discount on order confirmation")
                    order._apply_global_discount_to_products(total_global_discount)
        
        return super().action_confirm()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_invoice_line(self, **optional_values):
        """
        Override to ensure discounts are transferred correctly
        and filter global discount lines
        """
        # Check if it's a global discount line that should be filtered
        if self._is_global_discount_line():
            _logger.info(f"Filtering global discount line from invoice: {self.name}")
            return None
            
        invoice_line_vals = super()._prepare_invoice_line(**optional_values)
        
        # Ensure discount is transferred
        if self.discount > 0:
            invoice_line_vals['discount'] = self.discount
            _logger.info(f"Transferring discount {self.discount}% to invoice: {self.name}")
        
        return invoice_line_vals

    def _is_global_discount_line(self):
        """
        Checks if this line is a global discount line
        Checks both product name AND line description
        Extracts percentage from description if needed
        """
        if not self.product_id:
            return False
            
        product_name = (self.product_id.name or '').lower()
        line_description = (self.name or '').lower()
        
        discount_indicators = [
            'descuento', 'desconto', 'discount', 'desc.',
            'promocion', 'promoção', 'promotion',
            'rebaja', 'rebate', 'reduccion', 'redução'
        ]
        
        discount_prefixes = ['[disc]', '[desc]', '[descuento]', '[desconto]']
        
        is_discount_product = any(indicator in product_name for indicator in discount_indicators)
        has_discount_prefix = any(prefix in product_name for prefix in discount_prefixes)
        is_discount_description = any(indicator in line_description for indicator in discount_indicators)
        
        # Check if has percentage in description
        has_percentage_in_description = bool(re.search(r'\d+(?:\.\d+)?%', line_description))
        
        # It's a global discount line if:
        # 1. Has discount characteristics (name/prefix/description)
        # 2. AND (has discount field filled OR has percentage in description)
        # 3. AND price >= 0 (not a negative line discount)
        
        has_discount_characteristics = is_discount_product or has_discount_prefix or is_discount_description
        has_discount_value = self.discount > 0 or has_percentage_in_description
        
        return has_discount_characteristics and has_discount_value and self.price_unit >= 0