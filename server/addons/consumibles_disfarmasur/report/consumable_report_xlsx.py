from odoo import models
from collections import defaultdict


class ConsumableReportXlsx(models.AbstractModel):
    _name = 'report.allocations_consumable_products.consumable_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Reporte de Costos de Consumibles en Excel'

    def _get_selected_intake_lines(self, active_ids):
        IntakeLine = self.env['allocations.consumable.intake.line']
        domain = []
        if active_ids:
            domain = [('intake_id', 'in', active_ids)]
        return IntakeLine.search(domain)

    def generate_xlsx_report(self, workbook, data, records):
        # ========= 🎨 ESTILOS =========
        title_format = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center',
            'valign': 'vcenter', 'bg_color': '#DDEBF7'
        })
        header_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#4472C4', 'font_color': 'white', 'border': 1
        })
        total_format = workbook.add_format({
            'bold': True, 'bg_color': '#FFF2CC', 'border': 1
        })
        money = workbook.add_format({'num_format': '$#,##0.00', 'border': 1})
        normal = workbook.add_format({'border': 1})
        center = workbook.add_format({'align': 'center', 'border': 1})
        bold_center = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
        bold = workbook.add_format({'bold': True})

        active_ids = (self.env.context.get('active_ids') or []) if records else []
        intake_lines = self._get_selected_intake_lines(active_ids)
        MoveAlloc = self.env['allocations.consumable.move.alloc'].sudo()

        # ================================
        # TOTAL DE FACTURAS SELECCIONADAS
        # ================================
        intakes = intake_lines.mapped('intake_id')
        total_facturas = sum(intakes.mapped('amount_total'))

        # =========================================================
        # 🧾 HOJA 1: Detalle por factura
        # =========================================================
        sheet = workbook.add_worksheet('Reporte de Consumibles')
        sheet.merge_range('A1:H1', 'Reporte de Costos de Consumibles', title_format)

        headers = [
            'Producto', 'Factura', 'Costo Unitario',
            'Ingresos/Compras', 'Salidas', 'Disponible',
            'Costo Compra', 'Costo Despachos'
        ]
        row = 2
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        row += 1

        product_groups = defaultdict(lambda: defaultdict(list))
        for line in intake_lines:
            product = line.product_id.display_name
            bill = line.bill_number or '-'
            unit_cost = line.unit_cost
            qty_in = line.qty
            qty_out = sum(MoveAlloc.sudo().search([('intake_line_id', '=', line.id)]).mapped('qty_taken'))
            qty_disp = max(qty_in - qty_out, 0.0)
            cost_in = qty_in * unit_cost
            cost_out = qty_out * unit_cost
            product_groups[product][bill].append({
                'unit_cost': unit_cost,
                'qty_in': qty_in,
                'qty_out': qty_out,
                'qty_disp': qty_disp,
                'cost_in': cost_in,
                'cost_out': cost_out,
            })

        total_cost_in = total_cost_out = 0.0
        for product, bills in product_groups.items():
            product_total_in = product_total_out = product_total_disp = 0.0
            product_total_cost_in = product_total_cost_out = 0.0

            for bill, lines in bills.items():
                for item in lines:
                    sheet.write(row, 0, product, normal)
                    sheet.write(row, 1, bill, normal)
                    sheet.write_number(row, 2, item['unit_cost'], normal)
                    sheet.write_number(row, 3, item['qty_in'], center)
                    sheet.write_number(row, 4, item['qty_out'], center)
                    sheet.write_number(row, 5, item['qty_disp'], center)
                    sheet.write_number(row, 6, item['cost_in'], money)
                    sheet.write_number(row, 7, item['cost_out'], money)
                    row += 1

                    product_total_in += item['qty_in']
                    product_total_out += item['qty_out']
                    product_total_disp += item['qty_disp']
                    product_total_cost_in += item['cost_in']
                    product_total_cost_out += item['cost_out']

            # Totales por producto
            sheet.write(row, 0, f"Totales {product}", total_format)
            sheet.write(row, 3, product_total_in, total_format)
            sheet.write(row, 4, product_total_out, total_format)
            sheet.write(row, 5, product_total_disp, total_format)
            sheet.write_number(row, 6, product_total_cost_in, total_format)
            sheet.write_number(row, 7, product_total_cost_out, total_format)
            row += 2

            total_cost_in += product_total_cost_in
            total_cost_out += product_total_cost_out

        # Totales generales
        sheet.write(row, 0, "TOTAL GENERAL", total_format)
        sheet.write_number(row, 6, total_cost_in, total_format)
        sheet.write_number(row, 7, total_cost_out, total_format)
        sheet.set_column('A:A', 25)
        sheet.set_column('B:H', 15)

        # Totales generales (COSTOS)
        sheet.write(row, 0, "TOTAL GENERAL (COSTOS)", total_format)
        sheet.write_number(row, 6, total_cost_in, total_format)
        sheet.write_number(row, 7, total_cost_out, total_format)

        # 👉 TOTAL FACTURAS (DOCUMENTOS CONTABLES)
        row += 2
        sheet.write(row, 0, "TOTAL FACTURAS SELECCIONADAS", total_format)
        sheet.write_number(row, 6, total_facturas, money)

        sheet.set_column('A:A', 25)
        sheet.set_column('B:H', 15)

        # =========================================================
        # 📊 HOJA 2: Resumen por producto
        # =========================================================
        summary = workbook.add_worksheet('Resumen por producto')
        summary.merge_range('A1:K1', 'Resumen por producto (selección actual)', title_format)

        headers2 = [
            'Producto', 'Stock', 'Costo Inic', 'Ingresos/Com', 'Salidas Entreg',
            'Disponible', 'Costo Unit Cor', 'Costo Compra', 'Costo Despachos',
            'Saldos ($)', 'Stock (qty)'
        ]
        r = 2
        for c, h in enumerate(headers2):
            summary.write(r, c, h, header_format)
        r += 1

        prod_acc = {}
        sorted_lines = intake_lines.sorted(key=lambda l: (l.date_purchase or l.create_date, l.id))
        for line in sorted_lines:
            key = line.product_id.id
            entry = prod_acc.setdefault(key, {
                'name': line.product_id.display_name,
                'first_cost': None,
                'lines': [],
            })
            if entry['first_cost'] is None:
                entry['first_cost'] = float(line.unit_cost or 0.0)
            entry['lines'].append(line)

        total_in_cost = total_out_cost = 0.0
        for entry in prod_acc.values():
            name = entry['name']
            cost_init = entry['first_cost']
            related_lines = entry['lines']

            in_qty = sum(l.qty for l in related_lines)
            out_qty = 0.0
            cost_purchase = 0.0
            cost_dispatch = 0.0

            for l in related_lines:
                allocs = MoveAlloc.sudo().search([('intake_line_id', '=', l.id)])
                qty_taken = sum(allocs.mapped('qty_taken'))
                out_qty += qty_taken
                cost_purchase += l.qty * l.unit_cost
                cost_dispatch += qty_taken * l.unit_cost

            available = max(in_qty - out_qty, 0.0)
            last_cost = related_lines[-1].unit_cost if related_lines else cost_init
            saldo_money = available * last_cost

            summary.write(r, 0, name, normal)
            summary.write_number(r, 1, 1, center)
            summary.write_number(r, 2, cost_init, normal)
            summary.write_number(r, 3, in_qty, center)
            summary.write_number(r, 4, out_qty, center)
            summary.write_number(r, 5, available, center)
            summary.write_number(r, 6, last_cost, normal)
            summary.write_number(r, 7, cost_purchase, money)
            summary.write_number(r, 8, cost_dispatch, money)
            summary.write_number(r, 9, saldo_money, money)
            summary.write_number(r, 10, available, center)
            r += 1

            total_in_cost += cost_purchase
            total_out_cost += cost_dispatch

        # Totales
        summary.write(r + 1, 0, 'TOTALES', total_format)
        summary.write_number(r + 1, 7, total_in_cost, total_format)
        summary.write_number(r + 1, 8, total_out_cost, total_format)

        summary.set_column('A:A', 25)
        summary.set_column('B:K', 15)

        # =========================================================
        # 📈 HOJA 3: Resumen Global con gráficos
        # =========================================================
        chart_sheet = workbook.add_worksheet('Resumen global')
        chart_sheet.merge_range('A1:D1', 'Gráficos de Costos de Consumibles', title_format)

        # Datos base
        chart_sheet.write(3, 0, 'Producto', header_format)
        chart_sheet.write(3, 1, 'Costo Compra', header_format)
        chart_sheet.write(3, 2, 'Costo Despachos', header_format)
        chart_sheet.write(3, 3, 'Disponible (Unidades)', header_format)

        row_chart = 4
        for entry in prod_acc.values():
            name = entry['name']
            related_lines = entry['lines']
            total_in = sum(l.qty * l.unit_cost for l in related_lines)
            total_out = sum(
                sum(MoveAlloc.search(
                    [('intake_line_id', '=', l.id)]).mapped('qty_taken')) * l.unit_cost
                for l in related_lines
            )
            available = max(
                sum(l.qty for l in related_lines) -
                sum(sum(MoveAlloc.search(
                    [('intake_line_id', '=', l.id)]).mapped('qty_taken')) for l in related_lines),
                0
            )

            chart_sheet.write(row_chart, 0, name, normal)
            chart_sheet.write_number(row_chart, 1, total_in, money)
            chart_sheet.write_number(row_chart, 2, total_out, money)
            chart_sheet.write_number(row_chart, 3, available, center)
            row_chart += 1

        # Gráfico 1: Barras de Costos
        chart1 = workbook.add_chart({'type': 'column'})
        chart1.add_series({
            'name': 'Costo Compra',
            'categories': f'=Resumen global!$A$5:$A${row_chart}',
            'values': f'=Resumen global!$B$5:$B${row_chart}',
            'fill': {'color': '#5B9BD5'}
        })

        chart1.add_series({
            'name': 'Costo Despachos',
            'categories': f'=Resumen global!$A$5:$A${row_chart}',
            'values': f'=Resumen global!$C$5:$C${row_chart}',
            'fill': {'color': '#ED7D31'}
        })
        chart1.set_title({'name': 'Comparativo de Costos'})
        chart1.set_x_axis({'name': 'Productos'})
        chart1.set_y_axis({'name': 'Valor ($)'})
        chart_sheet.insert_chart('E4', chart1, {'x_scale': 1.2, 'y_scale': 1.3})

        # Gráfico 2: Pastel de Costos Totales
        chart2 = workbook.add_chart({'type': 'pie'})
        chart2.add_series({
            'name': 'Distribución de Costo Compra',
            'categories': f'=Resumen global!$A$5:$A${row_chart}',
            'values': f'=Resumen global!$B$5:$B${row_chart}',
        })
        chart2.set_title({'name': 'Distribución del Costo Compra'})
        chart_sheet.insert_chart('E25', chart2, {'x_scale': 1.2, 'y_scale': 1.3})