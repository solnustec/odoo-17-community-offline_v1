from odoo import models, fields, api
from datetime import date


class ConsumiblesKardexDashboard(models.TransientModel):
    _name = 'consumibles.kardex.dashboard'
    _description = 'Dashboard Kardex'

    total_stock = fields.Float(readonly=True)
    inventory_value = fields.Float(readonly=True)
    total_entries_month = fields.Float(readonly=True)
    total_outputs_month = fields.Float(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        Kardex = self.env['consumibles.product.kardex']

        # -----------------------------
        # STOCK TOTAL Y VALOR INVENTARIO
        # -----------------------------
        moves = Kardex.search([], order='product_id, product_type_id, date desc, id desc')

        seen = set()
        total_stock = 0.0
        inventory_value = 0.0

        for m in moves:
            key = (m.product_id.id, m.product_type_id.id)
            if key in seen:
                continue

            seen.add(key)
            total_stock += m.balance_qty
            inventory_value += m.balance_qty * m.cost

        # -----------------------------
        # MOVIMIENTOS DEL MES
        # -----------------------------
        today = date.today()
        first_day = today.replace(day=1)

        total_entries = sum(
            Kardex.search([
                ('movement_type', '=', 'in'),
                ('date', '>=', first_day)
            ]).mapped('qty_in')
        )

        total_outputs = sum(
            Kardex.search([
                ('movement_type', '=', 'out'),
                ('date', '>=', first_day)
            ]).mapped('qty_out')
        )

        res.update({
            'total_stock': total_stock,
            'inventory_value': inventory_value,
            'total_entries_month': total_entries,
            'total_outputs_month': total_outputs,
        })

        return res
