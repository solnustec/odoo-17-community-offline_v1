# -*- coding: utf-8 -*-
from odoo import models, fields
from collections import defaultdict


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _action_done(self):
        res = super()._action_done()
        self._update_transfer_summary()
        return res

    def _update_transfer_summary(self):
        """
        Crea, actualiza o elimina registros en product.warehouse.sale.summary
        para movimientos de transferencias internas.
        """
        SaleSummary = self.env['product.warehouse.sale.summary']

        # Agrupar: {(product_id, warehouse_id, date): {'qty': X, 'cost': Z}}
        summary_data = defaultdict(lambda: {'quantity': 0.0, 'cost': 0.0})

        for line in self:
            picking = line.picking_id
            if not picking:
                continue

            move = line.move_id
            picking_type_code = picking.picking_type_id.code

            # Determinar si es devolución
            is_return = bool(move.origin_returned_move_id)
            original_move = move.origin_returned_move_id

            # Verificar que sea transferencia interna
            if is_return:
                original_code = original_move.picking_type_id.code if original_move.picking_type_id else None
                if original_code != 'internal':
                    continue
                operation_sign = -1
            else:
                if picking_type_code != 'internal':
                    continue
                operation_sign = 1

            # Obtener warehouse
            # warehouse = picking.picking_type_id.warehouse_id
            # if not warehouse and line.location_id:
            warehouse = line.location_id.warehouse_id or line.location_id.get_warehouse()

            if not warehouse:
                continue

            # Fecha y producto
            summary_date = (picking.date_done and picking.date_done.date()) or fields.Date.today()
            product = line.product_id
            quantity = abs(line.quantity)
            cost = quantity * (product.standard_price or 0.0)

            # Acumular
            key = (product.id, warehouse.id, summary_date)
            summary_data[key]['quantity'] += quantity * operation_sign
            summary_data[key]['cost'] += cost * operation_sign

        if not summary_data:
            return

        # Búsqueda en lote
        search_domain = ['|'] * (len(summary_data) - 1)
        for (product_id, warehouse_id, date) in summary_data.keys():
            search_domain += [
                '&', '&', '&',
                ('product_id', '=', product_id),
                ('warehouse_id', '=', warehouse_id),
                ('date', '=', date),
                ('record_type', '=', 'transfer'),
            ]

        existing_records = SaleSummary.search(search_domain)
        existing_by_key = {
            (r.product_id.id, r.warehouse_id.id, r.date): r
            for r in existing_records
        }

        # Preparar operaciones en lote
        to_create = []
        to_write = {}
        to_delete = SaleSummary

        for key, data in summary_data.items():
            product_id, warehouse_id, date = key
            quantity = data['quantity']
            cost = data['cost']

            existing = existing_by_key.get(key)

            if existing:
                new_qty = existing.quantity_sold + quantity
                new_cost = existing.costo_total + cost

                if new_qty <= 0:
                    to_delete |= existing
                else:
                    to_write[existing] = {
                        'quantity_sold': new_qty,
                        'costo_total': max(new_cost, 0),
                    }
            elif quantity > 0:
                to_create.append({
                    'date': date,
                    'product_id': product_id,
                    'warehouse_id': warehouse_id,
                    'quantity_sold': quantity,
                    'amount_total': 0.0,
                    'costo_total': cost,
                    'record_type': 'transfer',
                    'is_legacy_system': False,
                    'stock_adjusted': False,
                })

        # Ejecutar en lote
        if to_delete:
            to_delete.unlink()
        if to_create:
            SaleSummary.create(to_create)
        for record, vals in to_write.items():
            record.write(vals)