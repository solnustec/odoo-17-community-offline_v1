# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        """
        Override action_post to create purchase history when a vendor bill is posted.

        This creates records in product.purchase.history for each line of the
        related purchase order when the invoice is confirmed.
        """
        result = super(AccountMove, self).action_post()

        for move in self:
            # Only process vendor bills (in_invoice)
            if move.move_type != 'in_invoice':
                continue

            # Get the purchase order from invoice_origin
            if not move.invoice_origin:
                continue

            # Search for the purchase order by name
            purchase_order = self.env['purchase.order'].search([
                ('name', '=', move.invoice_origin)
            ], limit=1)

            if not purchase_order:
                continue

            # Create purchase history for each line of the purchase order
            PurchaseHistory = self.env['product.purchase.history']
            for line in purchase_order.order_line:
                if not line.product_id:
                    continue

                # Check if history already exists to avoid duplicates
                existing_history = PurchaseHistory.search([
                    ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id),
                    ('purchase_order_id', '=', purchase_order.id),
                    ('date_order', '=', purchase_order.date_order.date() if purchase_order.date_order else False),
                ], limit=1)

                if existing_history:
                    continue

                # Create the purchase history record
                PurchaseHistory.create_from_purchase_line(line)

        return result
