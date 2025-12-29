from odoo import models
import io
import base64
import xlsxwriter

class ConsumiblesProductKardex(models.Model):
    _inherit = 'consumibles.product.kardex'

    def action_export_kardex_page_1_excel(self):
        records = self.search(self.env.context.get('active_domain', []))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet('KARDEX')

        # FORMATOS
        header = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'center'
        })
        cell = workbook.add_format({'border': 1})

        headers = [
            'Fecha', 'Producto', 'Tipo Producto', 'Documento',
            'Entrada', 'Salida', 'Saldo', 'Costo Unitario', 'Total'
        ]

        for col, h in enumerate(headers):
            sheet.write(0, col, h, header)

        row = 1
        for r in records:
            sheet.write(row, 0, r.date.strftime('%d/%m/%Y %H:%M'), cell)
            sheet.write(row, 1, r.product_id.display_name, cell)
            sheet.write(row, 2, r.product_type_id.display_name, cell)
            sheet.write(row, 3, r.reference or '', cell)
            sheet.write(row, 4, r.qty_in, cell)
            sheet.write(row, 5, r.qty_out, cell)
            sheet.write(row, 6, r.balance_qty, cell)
            sheet.write(row, 7, r.cost, cell)
            sheet.write(row, 8, r.total, cell)
            row += 1

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'Kardex_Pagina_1.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': 'consumibles.product.kardex',
            'res_id': 0,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self'
        }
