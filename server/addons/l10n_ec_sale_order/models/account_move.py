# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
import re

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _is_discount_line(self, line):
        """
        Identifies if a line is a discount line
        Checks both product name AND line description
        Returns: False, 'global_discount', or 'specific_discount'
        """
        if not line.product_id:
            return False
        
        # Check discount indicators in name/description
        line_description = (line.name or '').lower()
        product_name = (line.product_id.name or '').lower()
        
        discount_indicators = [
            'descuento', 'desconto', 'discount', 'desc.',
            'promocion', 'promoção', 'promotion',
            'rebaja', 'rebate', 'reduccion', 'redução'
        ]
        
        # Special prefixes for discount products
        discount_prefixes = ['[disc]', '[desc]', '[descuento]', '[desconto]']
        
        # Check if it's a discount product by name OR description
        is_discount_product = any(indicator in product_name for indicator in discount_indicators)
        has_discount_prefix = any(prefix in product_name for prefix in discount_prefixes)
        is_discount_description = any(indicator in line_description for indicator in discount_indicators)
        
        # Only proceed if it has discount indicators
        if not (is_discount_product or has_discount_prefix or is_discount_description):
            return False
        
        # Case 1: Global discount (with % in discount field) - Product-based global discount
        if line.discount > 0:
            _logger.info(f"Global discount product detected in invoice: {line.name} (Product: {product_name}) with {line.discount}%")
            return 'global_discount'
        
        # Case 2: Negative value discount lines
        if line.price_unit < 0:
            # Check if it's a SPECIFIC discount (mentions a product name explicitly)
            # Pattern: "27% en AZVITS..." or "5% para PRODUCTO X"
            specific_patterns = [
                r'\d+(?:\.\d+)?%\s+(en|em|in|para|for|de)\s+\w+',  # "27% en AZVITS"
                r'\d+(?:\.\d+)?%\s+en\s+[A-Z]',  # "27% en PRODUCTO"
            ]
            
            is_specific = any(re.search(pattern, line_description, re.IGNORECASE) for pattern in specific_patterns)
            
            if is_specific:
                _logger.info(f"Specific discount line detected in invoice: {line.name}")
                return 'specific_discount'
            
            # Check if it's a GLOBAL discount (generic description like "Descuento: 5.000%")
            # Pattern: "Descuento: X.XXX%" or "Discount: X%"
            global_patterns = [
                r'descuento:\s*\d+\.\d+%',  # "Descuento: 5.000%"
                r'desconto:\s*\d+\.\d+%',   # "Desconto: 5.000%"
                r'discount:\s*\d+\.\d+%',   # "Discount: 5.000%"
            ]
            
            is_global = any(re.search(pattern, line_description, re.IGNORECASE) for pattern in global_patterns)
            
            if is_global:
                return 'global_discount'
            
            # If has discount indicators but doesn't match specific patterns, treat as global
            return 'global_discount'
                
        return False

    def _process_specific_discount_lines(self):
        """
        Processes only specific discount lines (negative value) that still reached the invoice
        """
        if self.move_type not in ['out_invoice', 'out_refund']:
            return
        

        specific_discount_lines = []
        
        for line in self.invoice_line_ids:
            discount_type = self._is_discount_line(line)
            #exclude line with producto ENVIOSAPPMOVIL
            if line.product_id.default_code == 'ENVIOSAPPMOVIL':
                continue
            if discount_type == 'specific_discount':
                specific_discount_lines.append(line)
        
        if not specific_discount_lines:
            return
        
        # Process specific discounts
        for discount_line in specific_discount_lines:
            target_line = self._find_target_line_for_discount(discount_line)
            
            if target_line:
                discount_percentage = self._calculate_discount_percentage(discount_line, target_line)
                discount_percentage = min(discount_percentage, 100.0)
                
                current_discount = target_line.discount or 0
                new_discount = current_discount + discount_percentage
                new_discount = min(new_discount, 100.0)
                

                target_line.write({'discount': new_discount})
                discount_line.unlink()


    def action_post(self):
        """
        Processes only specific discounts when invoice is confirmed
        (global discounts already processed in SO)
        """
        for move in self:
            move._process_specific_discount_lines()
        
        return super().action_post()

    @api.model_create_multi
    def create(self, vals_list):
        """
        Processes specific discounts when invoice is created
        """
        moves = super().create(vals_list)
        
        for move in moves:
            move._process_specific_discount_lines()
        
        return moves

    def _find_target_line_for_discount(self, discount_line):
        """
        Finds the product line that should receive the specific discount
        """
        line_name = (discount_line.name or '').lower()
        
        # Pattern: "27% en AZVITS REFORZADO CAP"
        percentage_match = re.search(r'(\d+(?:\.\d+)?)%\s+(en|em|in|de)\s+(.+)', line_name, re.IGNORECASE)
        if percentage_match:
            product_name_fragment = percentage_match.group(3).strip().upper()
            
            # Search for line with similar name
            for line in self.invoice_line_ids:
                if (line.product_id and 
                    line.price_unit > 0 and 
                    not self._is_discount_line(line)):
                    line_description = (line.name or '').upper()
                    if product_name_fragment in line_description:
                        return line
        
        # If not found by name, get the previous line in sequence
        all_lines = self.invoice_line_ids.sorted('sequence')
        discount_index = None
        
        for i, line in enumerate(all_lines):
            if line.id == discount_line.id:
                discount_index = i
                break
        
        if discount_index is not None and discount_index > 0:
            target_line = all_lines[discount_index - 1]
            if target_line.product_id and not self._is_discount_line(target_line):
                return target_line
        
        # As last resort, get the first valid product line
        for line in self.invoice_line_ids:
            if (line.product_id and 
                line.price_unit > 0 and 
                not self._is_discount_line(line)):
                return line
        
        return None

    def _calculate_discount_percentage(self, discount_line, target_line):
        """
        Calculates the specific discount percentage
        """
        # First try to extract from description
        line_name = (discount_line.name or '').lower()
        percentage_match = re.search(r'(\d+(?:\.\d+)?)%', line_name)
        if percentage_match:
            return float(percentage_match.group(1))
        
        # If not in description, calculate based on value
        discount_amount = abs(discount_line.price_subtotal)
        target_subtotal = target_line.price_subtotal
        
        if target_subtotal > 0:
            return (discount_amount / target_subtotal) * 100
        
        return 0

    def _calculate_discount_percentage(self, discount_line, target_line):
        """
        Calculates the specific discount percentage
        """
        # First try to extract from description
        line_name = (discount_line.name or '').lower()
        percentage_match = re.search(r'(\d+(?:\.\d+)?)%', line_name)
        if percentage_match:
            return float(percentage_match.group(1))
        
        # If not in description, calculate based on value
        discount_amount = abs(discount_line.price_subtotal)
        target_subtotal = target_line.price_subtotal
        
        if target_subtotal > 0:
            return (discount_amount / target_subtotal) * 100
        
        return 0

    def _apply_global_discount(self, discount_line):
        """
        Applies global discount to all product lines in the invoice
        Extracts the percentage from the description if not in discount field
        """
        global_discount_percentage = discount_line.discount
        
        # If discount field is not set, try to extract from description
        if global_discount_percentage <= 0:
            line_description = (discount_line.name or '')
            # Try to extract percentage from description: "Descuento: 5.000%"
            percentage_match = re.search(r'(\d+(?:\.\d+)?)%', line_description)
            if percentage_match:
                global_discount_percentage = float(percentage_match.group(1))

        if global_discount_percentage <= 0:
            return
        

        lines_processed = 0
        # Apply discount to all product lines (except the discount line itself)
        for line in self.invoice_line_ids:
            if (line.product_id and 
                line.id != discount_line.id and 
                not self._is_discount_line(line) and
                line.price_unit > 0):
                
                # Add global discount to existing discount
                current_discount = line.discount or 0
                new_discount = current_discount + global_discount_percentage
                
                # Limit to 100%
                new_discount = min(new_discount, 100.0)
                

                line.write({'discount': new_discount})
                lines_processed += 1
        

    def _process_discount_lines(self):
        """
        Processes discount lines: removes and applies discount to product lines
        """
        if self.move_type not in ['out_invoice', 'out_refund']:
            return
        

        # FIRST: List ALL lines for debug
        for i, line in enumerate(self.invoice_line_ids):
            product_name = line.product_id.name if line.product_id else 'NO PRODUCT'

        # Identify discount lines
        specific_discount_lines = []
        global_discount_lines = []
        
        for line in self.invoice_line_ids:

            discount_type = self._is_discount_line(line)
            if discount_type == 'specific_discount':
                specific_discount_lines.append(line)
            elif discount_type == 'global_discount':
                global_discount_lines.append(line)

        
        total_discount_lines = len(specific_discount_lines) + len(global_discount_lines)
        if total_discount_lines == 0:
            return
        

        # First process global discounts - Extract unique percentage values
        if global_discount_lines:
            global_discount_percentages = set()  # Use set to avoid duplicates
            
            for discount_line in global_discount_lines:
                # Extract percentage from discount field or description
                discount_percentage = discount_line.discount
                
                if discount_percentage <= 0:
                    line_description = (discount_line.name or '')
                    percentage_match = re.search(r'(\d+(?:\.\d+)?)%', line_description)
                    if percentage_match:
                        discount_percentage = float(percentage_match.group(1))

                if discount_percentage > 0:
                    global_discount_percentages.add(discount_percentage)

            # Calculate total - if all percentages are the same, use only once
            if len(global_discount_percentages) == 1:
                # All global discounts have the same percentage - use it once
                total_global_discount = list(global_discount_percentages)[0]
            else:
                # Different percentages - sum them
                total_global_discount = sum(global_discount_percentages)

            # Limit to 100%
            total_global_discount = min(total_global_discount, 100.0)
            
            if total_global_discount > 0:

                # Apply the consolidated discount to all product lines
                for line in self.invoice_line_ids:
                    if (line.product_id and 
                        not self._is_discount_line(line) and
                        line.price_unit > 0):
                        
                        current_discount = line.discount or 0
                        new_discount = current_discount + total_global_discount
                        new_discount = min(new_discount, 100.0)
                        
                        line.write({'discount': new_discount})
            
            # Remove all global discount lines
            for discount_line in global_discount_lines:
                discount_line.unlink()
        
        # Then process specific discounts (lines with negative value)
        for discount_line in specific_discount_lines:
            target_line = self._find_target_line_for_discount(discount_line)
            
            if target_line:
                discount_percentage = self._calculate_discount_percentage(discount_line, target_line)
                discount_percentage = min(discount_percentage, 100.0)  # Maximum 100%
                
                # Add to existing discount (which may already include global discount)
                current_discount = target_line.discount or 0
                new_discount = current_discount + discount_percentage
                new_discount = min(new_discount, 100.0)  # Maximum 100%
                

                # Apply the discount
                target_line.write({'discount': new_discount})
                
                # Remove the discount line
                discount_line.unlink()



    def action_post(self):
        """
        Processes discounts when invoice is confirmed
        """
        for move in self:
            move._process_discount_lines()
        
        return super().action_post()

    def write(self, vals):
        """
        Processes discounts when invoice is modified
        """
        result = super().write(vals)
        
        # If invoice lines were modified, reprocess discounts
        if 'invoice_line_ids' in vals:
            for move in self:
                if move.move_type in ['out_invoice', 'out_refund'] and move.state == 'draft':
                    move._process_discount_lines()
        
        return result



    def process_discounts_manually(self):
        """
        Method to process discounts manually (can be called via button or action)
        """
        for move in self:
            if move.move_type in ['out_invoice', 'out_refund']:
                # First do debug
                # Then process
                move._process_discount_lines()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Discounts Processed',
                        'message': f'Discounts processed for invoice {move.name}',
                        'type': 'success',
                        'sticky': False,
                    }
                }

    @api.model_create_multi
    def create(self, vals_list):
        """
        Processes discounts when invoice is created
        """
        moves = super().create(vals_list)
        
        for move in moves:
            move._process_discount_lines()
        
        return moves