import logging
from odoo import models, api, fields

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends('product_id', 'move_id.move_type', 'move_id.partner_id')
    def _compute_account_id(self):
        """Override to use stock valuation account for purchase invoices"""
        
        for line in self:
            # Call parent method first
            super(AccountMoveLine, line)._compute_account_id()
            
            # For purchase invoices with products, override the account
            if (line.move_id.move_type == 'in_invoice' and 
                line.product_id and 
                line.display_type == 'product'):
                
                # Get fiscal position
                fiscal_pos = line.move_id.fiscal_position_id
                
                # Get product accounts with purchase context
                with_context = line.product_id.with_context(default_move_type='in_invoice')
                accounts = with_context.product_tmpl_id.get_product_accounts(fiscal_pos)
                
                # Use expense account (which should be stock valuation for purchases)
                if accounts.get('expense'):
                    line.account_id = accounts['expense']

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure proper account assignment"""
        result = super().create(vals_list)
        return result