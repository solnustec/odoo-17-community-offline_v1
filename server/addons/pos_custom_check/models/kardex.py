from odoo import models, api
from collections import defaultdict
from datetime import datetime, date, time
import pytz
import calendar


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # SALES
    @api.model
    def get_pos_sales_by_warehouse(self, warehouse_id, product_id, date_str=None):
        ecuador_tz = pytz.timezone('America/Guayaquil')

        if date_str:
            try:
                base_date = datetime.strptime(date_str, '%Y-%m-%d').date()

                # Filtrar solo por ese día
                start_dt = ecuador_tz.localize(datetime.combine(base_date, time.min))
                end_dt = ecuador_tz.localize(datetime.combine(base_date, time.max))
            except ValueError:
                base_date = datetime.now(ecuador_tz).date()
                # Si la fecha no es válida, usar mes actual
                first_day = base_date.replace(day=1)
                last_day = base_date.replace(day=calendar.monthrange(base_date.year, base_date.month)[1])
                start_dt = ecuador_tz.localize(datetime.combine(first_day, time.min))
                end_dt = ecuador_tz.localize(datetime.combine(last_day, time.max))
        else:
            base_date = datetime.now(ecuador_tz).date()
            # Mes actual
            first_day = base_date.replace(day=1)
            last_day = base_date.replace(day=calendar.monthrange(base_date.year, base_date.month)[1])
            start_dt = ecuador_tz.localize(datetime.combine(first_day, time.min))
            end_dt = ecuador_tz.localize(datetime.combine(last_day, time.max))

        date_start = start_dt.astimezone(pytz.utc)
        date_end = end_dt.astimezone(pytz.utc)

        sales_by_warehouse = defaultdict(lambda: {'total_orders': 0, 'sales': []})

        orders = self.env['pos.order'].sudo().search([
            ('config_id.picking_type_id.warehouse_id', '=', warehouse_id),
            ('date_order', '>=', date_start),
            ('date_order', '<=', date_end),
        ])

        for order in orders:
            warehouse_name = 'result'
            order_has_valid_lines = False

            for line in order.lines:
                if line.price_unit < 0 or line.product_id.id != product_id:
                    continue

                order_has_valid_lines = True

                sales_by_warehouse[warehouse_name]['sales'].append({
                    'type': 'VENTA',
                    'product': line.product_id.name,
                    'product_id': line.product_id.id,
                    'stock': line.product_id.pos_stock_available,
                    'quantity': abs(line.qty),
                    'price_unit': line.price_unit,
                    'subtotal': line.price_subtotal,
                    'order_name': order.name,
                    'date_order': self.convertir_a_hora_ecuador(order.date_order),
                    'customer': order.partner_id.name if order.partner_id else '',
                    'seller': order.user_id.name if order.user_id else 'Sin asignar',
                })

            if order_has_valid_lines:
                sales_by_warehouse[warehouse_name]['total_orders'] += 1

        if not sales_by_warehouse:
            return {'result': {'total_orders': 0, 'sales': []}}

        return dict(sales_by_warehouse)

    # TRANSFERS
    @api.model
    def get_product_transfers_by_warehouse(self, warehouse_id, product_id=None, date_str=None):
        ecuador_tz = pytz.timezone('America/Guayaquil')

        # Rango opcional por día (si no se envía, no filtra por fecha)
        if date_str:
            try:
                base_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                start_dt = ecuador_tz.localize(datetime.combine(base_date, time.min))
                end_dt = ecuador_tz.localize(datetime.combine(base_date, time.max))
                date_start = start_dt.astimezone(pytz.utc)
                date_end = end_dt.astimezone(pytz.utc)
            except ValueError:
                date_start = date_end = None
        else:
            date_start = date_end = None

        transfers_by_warehouse = defaultdict(lambda: {'total_transfers': 0, 'transfers': []})
        warehouse_name = 'result'

        # Ubicación "raíz" de la bodega
        warehouse = self.env['stock.warehouse'].sudo().browse(warehouse_id)
        if not warehouse:
            return {'result': {'total_transfers': 0, 'transfers': []}}

        view_location = warehouse.view_location_id
        # Todas las ubicaciones bajo la bodega
        loc_ids = self.env['stock.location'].sudo().search([('id', 'child_of', view_location.id)]).ids
        loc_set = set(loc_ids)

        domain = [
            ('state', '=', 'done'),
            ('picking_type_id.code', '=', 'internal'),
            '|', ('location_id', 'in', loc_ids), ('location_dest_id', 'in', loc_ids),
        ]
        if date_start and date_end:
            domain += [('date_done', '>=', date_start), ('date_done', '<=', date_end)]

        pickings = self.env['stock.picking'].sudo().search(domain)

        for picking in pickings:
            has_lines = False
            for move in picking.move_ids:
                # Filtro por producto (opcional)
                if product_id and move.product_id.id != product_id:
                    continue
                for ml in move.move_line_ids:
                    if product_id and ml.product_id.id != product_id:
                        continue

                    # cantidad hecha (compatibilidad: quantity o qty_done)
                    qty = ml.quantity if hasattr(ml, 'quantity') else getattr(ml, 'qty_done', 0.0)
                    if not qty:
                        continue

                    from_in = ml.location_id.id in loc_set
                    to_in = ml.location_dest_id.id in loc_set

                    # mover dentro de la misma bodega no cambia el neto
                    if from_in and to_in:
                        continue

                    has_lines = True
                    transfers_by_warehouse[warehouse_name]['transfers'].append({
                        'type': 'TRANSFERENCIA',
                        'product': ml.product_id.name,
                        'product_id': ml.product_id.id,
                        'stock': ml.product_id.pos_stock_available,
                        'quantity_in': qty if to_in else 0.0,  # ENTRA a la bodega
                        'quantity_out': qty if from_in else 0.0,  # SALE de la bodega
                        'origin': picking.origin,
                        'picking_name': picking.name,
                        'date_done': self.convertir_a_hora_ecuador(picking.date_done),
                        'from_location': ml.location_id.complete_name or ml.location_id.display_name,
                        'to_location': ml.location_dest_id.complete_name or ml.location_dest_id.display_name,
                        'user': picking.create_uid.name if picking.create_uid else 'Sin asignar',
                    })

            if has_lines:
                transfers_by_warehouse[warehouse_name]['total_transfers'] += 1

        if not transfers_by_warehouse:
            return {'result': {'total_transfers': 0, 'transfers': []}}

        return dict(transfers_by_warehouse)

    # REFUND
    @api.model
    def get_pos_refunds_by_warehouse(self, warehouse_id, product_id=None, date_str=None):
        ecuador_tz = pytz.timezone('America/Guayaquil')
        if date_str:
            try:
                base_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                start_dt = ecuador_tz.localize(datetime.combine(base_date, time.min))
                end_dt = ecuador_tz.localize(datetime.combine(base_date, time.max))
            except ValueError:
                base_date = datetime.now(ecuador_tz).date()
                first_day = base_date.replace(day=1)
                last_day = base_date.replace(day=calendar.monthrange(base_date.year, base_date.month)[1])
                start_dt = ecuador_tz.localize(datetime.combine(first_day, time.min))
                end_dt = ecuador_tz.localize(datetime.combine(last_day, time.max))
        else:
            base_date = datetime.now(ecuador_tz).date()
            first_day = base_date.replace(day=1)
            last_day = base_date.replace(day=calendar.monthrange(base_date.year, base_date.month)[1])
            start_dt = ecuador_tz.localize(datetime.combine(first_day, time.min))
            end_dt = ecuador_tz.localize(datetime.combine(last_day, time.max))

        date_start = start_dt.astimezone(pytz.utc)
        date_end = end_dt.astimezone(pytz.utc)

        refunds_by_warehouse = defaultdict(lambda: {'total_orders': 0, 'refund': []})

        orders = self.env['pos.order'].sudo().search([
            ('config_id.picking_type_id.warehouse_id', '=', warehouse_id),
            ('date_order', '>=', date_start),
            ('date_order', '<=', date_end),
        ])

        for order in orders:
            warehouse_name = 'result'
            order_has_refunds = False

            for line in order.lines:
                if 'REEMBOLSO' in (line.order_id.display_name or '').upper():
                    if product_id and line.product_id.id != product_id:
                        continue

                    order_has_refunds = True

                    refunds_by_warehouse[warehouse_name]['refund'].append({
                        'type': 'REEMBOLSO',
                        'product': line.product_id.name,
                        'stock': line.product_id.pos_stock_available,
                        'product_id': line.product_id.id,
                        'quantity_in':abs( line.qty),
                        'price_unit': line.price_unit,
                        'order_name': order.name,
                        'date_order': self.convertir_a_hora_ecuador(order.date_order),
                        'customer': order.partner_id.name if order.partner_id else '',
                        'seller': order.user_id.name if order.user_id else 'Sin asignar',
                    })

            if order_has_refunds:
                refunds_by_warehouse[warehouse_name]['total_orders'] += 1

        if not refunds_by_warehouse:
            return {'result': {'total_orders': 0, 'refund': []}}

        return dict(refunds_by_warehouse)


    def convertir_a_hora_ecuador(self, hora_utc):
        # Zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc
        utc_time = utc_tz.localize(
            hora_utc)  # Asegurar que la hora esté marcada como UTC
        whitout_time_zone = utc_time.astimezone(ecuador_tz)
        return whitout_time_zone.replace(tzinfo=None)