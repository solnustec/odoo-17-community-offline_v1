import pytz
import re as regex

from odoo import models, fields, _, api
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_repr, float_compare


class PosOrder(models.Model):
    _inherit = 'pos.order'

    sri_authorization = fields.Char(
        string="SRI Authorization",
        related="account_move.l10n_ec_authorization_number",
        store=True,
        readonly=True,
    )

    def _prepare_invoice_lines(self):
        """ Prepare a list of orm commands containing the dictionaries to fill the
        'invoice_line_ids' field when creating an invoice.

        :return: A list of Command.create to fill 'invoice_line_ids' when calling account.move.create.
        """
        sign = 1 if self.amount_total >= 0 else -1
        line_values_list = self._prepare_tax_base_line_values(sign=sign)
        invoice_lines = []
        
        filtered_line_values = []
        discount_lines_by_product = {}
        
        for line_values in line_values_list:
            line = line_values['record']
            
            if (hasattr(line, 'price_unit') and line.price_unit < 0 and 
                hasattr(line, 'reward_prod_id') and line.reward_prod_id):
                discount_percentage = 0.0
                line_name = (
                        getattr(line, 'full_product_name', None)
                        or line_values.get('name')
                        or (line.product_id and line.product_id.display_name)
                        or ''
                )

                if line_name:
                    match = regex.search(r'(\d+(?:\.\d+)?)%', line_name)
                    if match:
                        discount_percentage = float(match.group(1))
                
                discount_lines_by_product[line.reward_prod_id] = {
                    'discount_amount': abs(line.price_unit),
                    'discount_percentage': discount_percentage,
                    'line': line
                }
            elif (line.price_unit < 0 and line.sale_order_line_id):
                discount_percentage = 0.0
                line_name = line_values.get('name', '')

                if line_name:
                    match = regex.search(r'(\d+(?:\.\d+)?)%', line_name)
                    if match:
                        discount_percentage = float(match.group(1))

                discount_lines_by_product[line.sale_order_line_id.reward_product_id] = {
                    'discount_amount': abs(line.price_unit),
                    'discount_percentage': discount_percentage,
                    'line': line
                }

            else:
                filtered_line_values.append(line_values)
        
        for line_values in filtered_line_values:
            line = line_values['record']
            invoice_lines_values = self._get_invoice_lines_values(line_values, line)
            
            if line.product_id.id in discount_lines_by_product:
                discount_info = discount_lines_by_product[line.product_id.id]
                if line_values['price_unit'] > 0:
                    if discount_info['discount_percentage'] > 0:
                        invoice_lines_values['discount'] = discount_info['discount_percentage']
                    else:
                        discount_percentage = (discount_info['discount_amount'] / line_values['price_unit']) * 100
                        invoice_lines_values['discount'] = round(discount_percentage, 2)
            
            invoice_lines.append((0, None, invoice_lines_values))
            
            if line.order_id.pricelist_id.discount_policy == 'without_discount' and float_compare(line.price_unit, line.product_id.lst_price,
                                                                                                  precision_rounding=self.currency_id.rounding) < 0:
                invoice_lines.append((0, None, {
                    'name': _('Price discount from %s -> %s',
                              float_repr(line.product_id.lst_price, self.currency_id.decimal_places),
                              float_repr(line.price_unit, self.currency_id.decimal_places)),
                    'display_type': 'line_note',
                }))
            if line.customer_note:
                invoice_lines.append((0, None, {
                    'name': line.customer_note,
                    'display_type': 'line_note',
                }))
        
        return invoice_lines


    def _prepare_invoice_vals(self):
        # EXTENDS 'point_of_sale'
        vals = super()._prepare_invoice_vals()

        # TODO esto de aca es para evitar que las facturas del pos se envien al sri no descomentar solo para pruebas
        # TODO remover el  vals['edi_state'] = 'sent' para evitar que las facturas del odoo se envien al sri
        # vals['edi_state'] = 'sent'

        if self.company_id.country_id.code == 'EC':
            if len(self.payment_ids) > 1:
                vals['l10n_ec_sri_payment_id'] = self.env['l10n_ec.sri.payment'].search([("code", "=", "mpm")]).id
            else:
                vals['l10n_ec_sri_payment_id'] = self.payment_ids.payment_method_id.l10n_ec_sri_payment_id.id
        return vals

    def _export_for_ui(self, order):
        res = super()._export_for_ui(order)
        res['sri_authorization'] = order.sri_authorization or False
        return res
