from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.onchange('price_subtotal')
    def _onchange_price_subtotal_manual(self):
        if not self.taxes_id or not self.price_subtotal or not self.product_qty:
            return

        # Validación: solo ejecutar si el usuario cambió manualmente
        expected_subtotal = self.price_unit * self.product_qty * (1 - (self.discount / 100.0))
        if self.price_subtotal == expected_subtotal:
            return

        # Actualizar precio unitario para que Odoo recalcule todos los valores
        discount_factor = 1 - (self.discount / 100.0)
        if discount_factor:
            self.price_unit = self.price_subtotal / (self.product_qty * discount_factor)

    @api.onchange('price_total')
    def _onchange_price_total_manual(self):
        if not self.taxes_id or not self.price_total or not self.product_qty:
            return

        # Validación: solo ejecutar si el usuario cambió manualmente
        expected_total = self.price_subtotal + self.price_tax
        if self.price_total == expected_total:
            return

        fixed_amount = 0
        ice_rate = 0
        iva_rate = 0

        for tax in self.taxes_id:
            if tax.amount_type == 'fixed':
                fixed_amount += tax.amount * self.product_qty   # IRBPNR
            elif tax.amount_type == 'percent':
                if tax.include_base_amount:
                    ice_rate += tax.amount / 100                # ICE
                else:
                    iva_rate += tax.amount / 100                # IVA

        # Calcular subtotal previo: Restar al total el impuesto fijo ==> IRBPNR
        price_subtotal_prev = self.price_total - fixed_amount

        # Calcular multiplicador de impuestos porcentuales: ICE e IVA
        multiplier = (1 + ice_rate) * (1 + iva_rate)

        # Calcular subtotal: Dividir subtotal previo para los impuestos porcentuales ==> ICE e IVA
        price_subtotal = price_subtotal_prev / multiplier

        # Actualizar precio unitario para que Odoo recalcule todos los valores
        discount_factor = 1 - (self.discount / 100.0)
        if discount_factor and self.product_qty:
            self.price_unit = price_subtotal / (self.product_qty * discount_factor)