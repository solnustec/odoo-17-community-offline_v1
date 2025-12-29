# -*- coding: utf-8 -*-
import io
import xlsxwriter
from odoo import models


class ConsumiblesKardex(models.Model):
    _inherit = 'consumibles.product.kardex'

    def export_kardex_page_1_excel(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('KARDEX - Página 1')

        # FORMATS
        header = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        cell = workbook.add_format({'border': 1})
        number = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})

        # HEADERS
        headers = [
            'Fecha',
            'Documento',
            'Movimiento',
            'Entrada',
            'Salida',
            'Saldo',
            'Costo Unitario',
            'Total'
        ]

        for col, title in enumerate(headers):
            sheet.write(0, col, title, header)
            sheet.set_column(col, col, 18)

        # DATA
        row = 1
        for rec in self.sorted('date'):
            sheet.write(row, 0, str(rec.date), cell)
            sheet.write(row, 1, rec.reference or '', cell)
            sheet.write(row, 2, rec.movement_type, cell)
            sheet.write(row, 3, rec.qty_in or 0, number)
            sheet.write(row, 4, rec.qty_out or 0, number)
            sheet.write(row, 5, rec.balance_qty or 0, number)
            sheet.write(row, 6, rec.cost or 0, number)
            sheet.write(row, 7, rec.total or 0, number)
            row += 1

        workbook.close()
        output.seek(0)
        return output.read()
