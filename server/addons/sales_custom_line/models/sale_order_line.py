# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    profit_percent = fields.Float(
        string='% Utilidad',
        compute='_compute_profit_percent',
        store=True,
        digits=(16, 2),
        help='Porcentaje de utilidad: ((PVP - DESCUENTO - (COSTO+IVA)) * 100) / (COSTO+IVA).'
    )

    @api.depends(
        'price_unit',
        'discount',
        'product_id',
        'tax_id',
        'order_id.pricelist_id',
        'order_id.currency_id',
        'order_id.date_order',
        'company_id',
    )
    def _compute_profit_percent(self):
        for line in self:
            if not line.product_id or not line.price_unit:
                line.profit_percent = 0.0
                continue

            # Precio efectivo tras descuento
            effective_price = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)

            if effective_price <= 0.0:
                line.profit_percent = 0.0
                continue

            company = line.company_id or self.env.company
            order_currency = line.order_id.currency_id or company.currency_id
            company_currency = company.currency_id
            date = line.order_id.date_order or fields.Date.context_today(line)

            # Costo en moneda del pedido
            cost_in_order_currency = company_currency._convert(
                line.product_id.standard_price or 0.0,
                order_currency,
                company,
                date,
            )

            # IVA % (solo impuestos percentuales de venta)
            iva_percent = sum(line.tax_id.filtered(
                lambda t: t.amount_type == 'percent' and t.type_tax_use in ('sale', 'none')
            ).mapped('amount'))
            iva_decimal = iva_percent / 100.0

            # Costo + IVA
            cost_with_iva = cost_in_order_currency * (1.0 + iva_decimal)

            # Fórmula: ((PVP - DESCUENTO - (COSTO+IVA)) * 100) / (COSTO+IVA)
            line.profit_percent = ((effective_price - cost_with_iva) / cost_with_iva) * 100.0 if cost_with_iva > 0 else 0.0
