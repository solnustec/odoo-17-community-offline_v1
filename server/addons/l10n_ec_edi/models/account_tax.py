# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import math

from odoo import fields, models
from odoo.tools import float_round

L10N_EC_TAXSUPPORTS = [
    ('01', '01 Tax credit for VAT declaration (services and goods other than inventories and fixed assets)'),
    ('02', '02 Cost or Expense for IR declaration (services and goods other than inventories and fixed assets)'),
    ('03', '03 Fixed Asset - Tax Credit for VAT return'),
    ('04', '04 Fixed Asset - Cost or Expense for IR declaration'),
    ('05', '05 Settlement of travel, lodging and food expenses IR expenses (on behalf of employees and not of the company)'),
    ('06', '06 Inventory - Tax Credit for VAT return'),
    ('07', '07 Inventory - Cost or Expense for IR declaration'),
    ('08', '08 Amount paid to request Expense Reimbursement (intermediary)'),
    ('09', '09 Claims Reimbursement'),
    ('10', '10 Distribution of Dividends, Benefits or Profits'),
    ('15', '15 Payments made for own and third-party consumption of digital services'),
    ('00', '00 Special cases whose support does not apply to the above options')
]


class AccountTax(models.Model):

    _inherit = "account.tax"

    l10n_ec_code_taxsupport = fields.Selection(
        L10N_EC_TAXSUPPORTS,
        string='Tax Support',
        help='Indicates if the purchase invoice supports tax credit or cost or expenses, conforming table 5 of ATS'
    )



    def compute_all(self, price_unit, currency=None, quantity=1.0,
                    product=None, partner=None, is_refund=False,
                    handle_price_include=True, include_caba_tags=False,
                    fixed_multiplicator=1):

        withholding_tax_groups = [
            'withhold_vat_sale',
            'withhold_vat_purchase',
            'withhold_income_sale',
            'withhold_income_purchase'
        ]
        is_withhold_tax = self.filtered(
            lambda x: x.tax_group_id.l10n_ec_type in withholding_tax_groups)
        if is_withhold_tax:
            return super(AccountTax,
                         self.with_context(round=True)).compute_all(price_unit,
                                                                    currency,
                                                                    quantity,
                                                                    product,
                                                                    partner,
                                                                    is_refund=is_refund,
                                                                    handle_price_include=handle_price_include,
                                                                    include_caba_tags=include_caba_tags,
                                                                    fixed_multiplicator=fixed_multiplicator)

        # Llamar a la función original
        res = super(AccountTax, self).compute_all(
            price_unit, currency, quantity, product, partner, is_refund,
            handle_price_include, include_caba_tags, fixed_multiplicator
        )

        # Identificar el impuesto IRBPNR
        irbpnr_tax = self.filtered(lambda tax: tax.name == 'IRBPNR')
        if not irbpnr_tax:
            return res  # Si no hay IRBPNR, devolver el resultado original

        # Obtener la compañía y moneda
        company = self.env.company if not self else self[
                                                        0].company_id._accessible_branches()[
                                                    :1] or self[0].company_id
        currency = currency or company.currency_id
        prec = currency.rounding

        # Calcular el monto del impuesto IRBPNR (quantity * uom * 0.02)
        uom = product.uom_po_id.factor_inv if product else 1.0
        irbpnr_amount = float_round(
            abs(quantity * uom) * irbpnr_tax.amount * abs(fixed_multiplicator),
            precision_rounding=prec)

        # Ajustar el signo para devoluciones
        sign = -1 if is_refund else 1

        # Obtener las líneas de reparto para IRBPNR
        tax_repartition_lines = (
                is_refund and irbpnr_tax.refund_repartition_line_ids
                or irbpnr_tax.invoice_repartition_line_ids
        ).filtered(lambda x: x.repartition_type == 'tax')
        sum_repartition_factor = sum(tax_repartition_lines.mapped('factor'))

        # Crear las entradas para el impuesto IRBPNR
        irbpnr_vals = []
        factorized_irbpnr_amount = float_round(
            irbpnr_amount * sum_repartition_factor, precision_rounding=prec)
        repartition_line_amounts = [
            float_round(irbpnr_amount * line.factor, precision_rounding=prec)
            for line in tax_repartition_lines]
        total_rounding_error = float_round(
            factorized_irbpnr_amount - sum(repartition_line_amounts),
            precision_rounding=prec)
        nber_rounding_steps = int(
            abs(total_rounding_error / currency.rounding)) if total_rounding_error else 0
        rounding_error = float_round(
            total_rounding_error / nber_rounding_steps if nber_rounding_steps else 0.0,
            precision_rounding=prec)

        for repartition_line, line_amount in zip(tax_repartition_lines,
                                                 repartition_line_amounts):
            if nber_rounding_steps:
                line_amount += rounding_error
                nber_rounding_steps -= 1

            irbpnr_vals.append({
                'id': irbpnr_tax.id,
                'name': partner and irbpnr_tax.with_context(
                    lang=partner.lang).name or irbpnr_tax.name,
                'amount': sign * line_amount,
                'base': float_round(sign * res['total_excluded'],
                                    precision_rounding=prec),
                # Use total_excluded as base
                'sequence': irbpnr_tax.sequence,
                'account_id': repartition_line._get_aml_target_tax_account(
                    force_caba_exigibility=include_caba_tags).id,
                'analytic': irbpnr_tax.analytic,
                'use_in_tax_closing': repartition_line.use_in_tax_closing,
                'price_include': False,  # No afecta el precio incluido
                'tax_exigibility': irbpnr_tax.tax_exigibility,
                'tax_repartition_line_id': repartition_line.id,
                'group': res['taxes'][0]['group'] if res['taxes'] else None,
                'tag_ids': (repartition_line.tag_ids.ids + (
                    product.sudo().account_tag_ids.ids if product else [])),
                'tax_ids': [],  # IRBPNR no afecta otros impuestos
            })

        # Actualizar los resultados
        total_void_adjustment = sum(
            line['amount'] for line in irbpnr_vals if not line['account_id'])
        res['taxes'] = [tax for tax in res['taxes'] if
                        tax['id'] != irbpnr_tax.id] + irbpnr_vals
        res['total_included'] = currency.round(
            res['total_included'] + sign * factorized_irbpnr_amount)
        res['total_void'] = currency.round(
            res['total_void'] + sign * total_void_adjustment)

        return res