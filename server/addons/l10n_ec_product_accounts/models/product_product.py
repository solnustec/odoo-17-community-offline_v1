import logging
from odoo import models, api, _

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        """
        When the taxes of a product are changed, we update the taxes of the products
        associated to loyalty rewards that use this product as a discount product.
        solo para los prodcutos de almacenables
        """
        res = super().write(vals)
        if 'taxes_id' in vals and self.detailed_type == 'product':
            for product_tmpl in self:
                rewards = self.env['loyalty.reward'].search([
                    ('discount_product_ids', 'in', product_tmpl.product_variant_ids.ids),
                ])
                for reward in rewards:
                    reward.discount_line_product_id.taxes_id = [(6, 0, product_tmpl.taxes_id.ids)]
        return res

    @api.onchange('taxes_id')
    def _onchange_taxes_id(self):
        if not self.taxes_id:
            return {
                'warning': {
                    'title': _("Advertencia"),
                    'type': 'warning',
                    'message': _(
                        "Debe seleccionar al menos un impuesto para el producto."),
                }
            }
        else:
            tax_ids = self.env['account.tax'].search([
                ('id', 'in', self.taxes_id.ids),
            ])
            if not tax_ids[0].inventory_income_account_id or not tax_ids[0].inventory_expense_account_id:
                return {
                    'warning': {
                        'title': _("Advertencia"),
                        'type': 'warning',
                        'message': _(
                            "El impuesto seleccionado no tiene cuentas de ingresos o gastos configuradas."),
                    }
                }
            self.property_account_income_id = tax_ids[0].inventory_income_account_id
            self.property_account_expense_id = tax_ids[0].inventory_expense_account_id
        return None

    def get_product_accounts(self, fiscal_pos=None):        
        template_accounts = self.product_tmpl_id.get_product_accounts(fiscal_pos)
        
        # Check if we're in a purchase invoice context
        is_purchase_context = (
            self._context.get('default_move_type') == 'in_invoice' or \
            self._context.get('move_type') == 'in_invoice' or \
            'purchase' in str(self._context.get('active_model', '')) or \
            self._context.get('invoice_origin') and 'P00' in str(self._context.get('invoice_origin', '')) or \
            hasattr(self.env, 'context') and any('purchase' in str(k).lower() for k in self._context.keys()) or \
            # Check if we're being called from a purchase order context
            self._context.get('params', {}).get('active_model') == 'purchase.order' or \
            # Check if there's a purchase_line_id in the context (from purchase order lines)
            any('purchase_line_id' in str(v) for v in self._context.values() if isinstance(v, (list, dict)))
        )
        
        if self.taxes_id and len(self.taxes_id) > 0:
            tax = self.taxes_id[0]
            
            if tax.inventory_income_account_id:
                template_accounts['income'] = tax.inventory_income_account_id
            
            # For purchase invoices, use stock valuation account instead of expense account    
            if is_purchase_context and tax.inventory_stock_valuation_account_id:
                template_accounts['expense'] = tax.inventory_stock_valuation_account_id
            elif tax.inventory_expense_account_id:
                template_accounts['expense'] = tax.inventory_expense_account_id
                
            if tax.inventory_stock_valuation_account_id:
                template_accounts['stock_valuation'] = tax.inventory_stock_valuation_account_id
                
            if tax.inventory_expense_account_id:
                template_accounts['stock_output'] = tax.inventory_expense_account_id
        
        return template_accounts
