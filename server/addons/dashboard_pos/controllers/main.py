import json
from odoo import http
import io
import xlsxwriter
from odoo.http import request, content_disposition
import logging
from odoo.exceptions import UserError
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime


_logger = logging.getLogger(__name__)


class PosDashboardController(http.Controller):

    @http.route('/dashboard_pos/export_excel', type='http', auth='user', methods=['POST'], csrf=False)
    def export_excel(self, **post):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        headers = data.get('headers', [])
        rows = data.get('data', [])
        filters = data.get('filters', {})
        

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("Cierre de Caja POS Export")

        # Definir formatos
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#D3D3D3'
        })
        border_format = workbook.add_format({
            'border': 1
        })

        # Escribir los encabezados
        for col_idx, header in enumerate(headers):
            worksheet.write(0, col_idx, header, header_format)

        # Escribir los datos
        for row_idx, row in enumerate(rows):
            for col_idx, header in enumerate(headers):
                worksheet.write(row_idx + 1, col_idx, row.get(header, ''), border_format)

        for col_idx, header in enumerate(headers):
            max_length = len(str(header))
            for row in rows:
                cell_value = str(row.get(header, ''))
                max_length = max(max_length, len(cell_value))
            worksheet.set_column(col_idx, col_idx, max_length + 2)

        workbook.close()
        output.seek(0)
        xlsx_data = output.read()
        output.close()

        return request.make_response(
            xlsx_data,
            headers=[
                ("Content-Type", "application/vnd.ms-excel"),
                ("Content-Disposition", content_disposition("pos_dashboard_export.xlsx")),
            ],
        )



class PosDashboardPDFController(http.Controller):

    @staticmethod
    def get_sequence_from_warehouse(bodega_name):
        # Busca la bodega y obtiene su secuencia para ordenar las bodegas según la ubicación
        warehouse = request.env['stock.warehouse'].sudo().search([('name', '=', bodega_name)], limit=1)
        _logger.info(f"Buscando secuencia para bodega: {bodega_name} -> Secuencia: {warehouse.sequence if warehouse else 'NO ENCONTRADA'}")
        return warehouse.sequence or 999  # Si no tiene secuencia, lo mandamos al final

    @http.route('/pos_dashboard/simple_pdf_report', type='http', auth='user', methods=['POST'], csrf=False)
    def simple_pdf_report(self, **post):
        try:
            # Acceder al cuerpo de la solicitud como JSON
            data = request.httprequest.get_json()
            headers = data.get('headers', [])
            rows = data.get('data', [])
            report_date = data.get('filters', {}).get('start_date', "")  # Obtener la fecha del reporte
            totals = data.get('totals', {})  # Totales de las columnas
            col_width = 43  # Ancho de las columnas en el PDF

           
            
            # Excluir algunos encabezados del reporte
            excluded_headers = ["Bodega", "Usuario", "Fecha", "Alc.TC", "(-) Alc.CH/TR", "Ant.EF", "(-) Alc.CR"]
            filtered_headers = [header for header in headers if header not in excluded_headers]
            mapped_headers = filtered_headers

            # Verificar si se recibió la fecha
            if not report_date:
                raise UserError("No se recibió la fecha en los datos del reporte.")

            # Ordenar las filas por la secuencia de las bodegas
            rows.sort(key=lambda r: (self.get_sequence_from_warehouse(r.get('Bodega', '')), r.get('Bodega', '').lower()))

            # Crear un objeto BytesIO para generar el PDF en memoria
            output = BytesIO()
            pdf = canvas.Canvas(output, pagesize=(841.89, 595.27))  # Tamaño A4 Landscape
            pdf.setFont("Helvetica", 10)
            y_position = 550  # Posición inicial para los encabezados

            # Función para dibujar el encabezado de la página
            def draw_header(pdf, report_date):
                pdf.setFont("Helvetica-Bold", 12)
                pdf.drawString(20, 570, "Farmacias Cuxibamba")
                pdf.setFont("Helvetica", 12)
                pdf.drawString(20, 555, "Reporte de Cierre de Caja Consolidado")
                today_str = datetime.today().strftime("%d/%m/%Y")
                pdf.drawRightString(820, 570, f"Fecha impresión: {today_str}")
                if report_date:
                    pdf.drawRightString(820, 555, f"Fecha de reporte: {report_date}")
                pdf.line(20, 545, 820, 545)

            # Llamada para escribir el encabezado
            draw_header(pdf, report_date)
            y_position -= 20

            previous_bodega = ""
            previous_cashier = ""
            headers_written = False  # Asegura que los encabezados solo se escriban una vez
            row_counter = 0  # Contador para filas, para alternar colores
            previous_date = ""  # Variable para almacenar la fecha anterior

            # Escribir los valores de Bodega, Usuario y Fecha, y aumentar el margen superior
            for row in rows:
                bodega = row.get('Bodega', '')  # Obtener el valor de la bodega
                cashier = row.get('Usuario', '')  # Obtener el valor del cajero

                # Si la posición Y es muy baja, crear una nueva página
                if y_position < 50:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 8)
                    y_position = 550
                    draw_header(pdf, report_date)  # Vuelvo a escribir el encabezado
                    y_position -= 15
                    pdf.setFont("Helvetica-Bold", 7)
                    pdf.setFillColorRGB(0.8, 0.9, 1)  # Fondo azul para encabezados
                    for col_idx, header in enumerate(mapped_headers):
                        x = 10 + (col_idx * col_width)
                        # Dibuja un rectángulo en el PDF
                        # Parámetros:
                        # - x - 2: La posición horizontal inicial del rectángulo. Se le resta 2 para moverlo ligeramente a la izquierda.
                        # - y_position - 5: La posición vertical inicial del rectángulo. Se le resta 5 para moverlo ligeramente hacia arriba, alineando mejor el rectángulo con el texto o las celdas.
                        # - 44: El **ancho** del rectángulo. Define cuánto espacio ocupará el rectángulo horizontalmente en la página.
                        # - 20: La **altura** del rectángulo. Define la longitud vertical del rectángulo.
                        # - fill=1: Indica que el rectángulo debe ser **rellenado con color**. El color de relleno fue establecido previamente (en este caso, un color azul pálido).
                        # - stroke=0: Indica que el rectángulo no tendrá **borde**. Si fuera 1, tendría un borde visible alrededor del rectángulo.

                        pdf.rect(x - 2, y_position - 5, col_width, 20, fill=1, stroke=0)
                    pdf.setFillColorRGB(0, 0, 0)
                    for col_idx, header in enumerate(mapped_headers):
                        pdf.drawString(10 + (col_idx * col_width), y_position, header)
                    y_position -= 20  # Baja para la siguiente fila

                # Si el nombre de la bodega cambia, lo escribimos en el PDF
                if bodega != previous_bodega:
                    pdf.setFont("Helvetica-Bold", 10)
                    pdf.drawString(20, y_position, f"Bodega: {bodega}")
                    previous_bodega = bodega
                    y_position -= 15

                # Si el nombre del cajero cambia, lo escribimos en el PDF
                if cashier != previous_cashier:
                    pdf.setFont("Helvetica", 10)
                    pdf.drawString(20, y_position, f"Cajero: {cashier}")
                    previous_cashier = cashier
                    y_position -= 15
                y_position -= 10

                # # Escribir la fecha si es diferente
                # if report_date != previous_date:
                #     pdf.setFont("Helvetica", 8)
                #     pdf.drawString(20, y_position, f"Fecha del reporte: {report_date}")
                #     previous_date = report_date
                #     y_position -= 15

                # Escribir los encabezados si no han sido escritos
                if not headers_written:
                    pdf.setFont("Helvetica-Bold", 7)
                    pdf.setFillColorRGB(0.8, 0.9, 1)  # Azul pálido
                    header_height = 20
                    
                    
                    for col_idx, header in enumerate(mapped_headers):
                        x_pos = 10 + (col_idx * col_width)
                        pdf.rect(x_pos - 2, y_position - 5, col_width, header_height, fill=1, stroke=0)
                    pdf.setFillColorRGB(0, 0, 0)
                    for col_idx, header in enumerate(mapped_headers):
                        pdf.drawString(10 + (col_idx * col_width), y_position, header)
                    y_position -= 20  # Baja para empezar a escribir los datos de las filas
                    headers_written = True

                # Alternar colores entre azul y amarillo pálido
                if row_counter % 2 == 0:
                    pdf.setFillColorRGB(0.9, 0.95, 1)  # Azul pálido
                else:
                    pdf.setFillColorRGB(1, 1, 0.85)  # Amarillo pálido
                pdf.rect(8, y_position - 5, 820, 20, fill=1, stroke=0)

                pdf.setFillColorRGB(0, 0, 0)  # Texto en negro
                pdf.setFont("Helvetica", 7)

                # Escribir los valores de las filas, usando el mapeo de encabezados
                for col_idx, header in enumerate(mapped_headers):
                    cell_value = row.get(header, '')
                    if isinstance(cell_value, (int, float)):
                        cell_value = "{:,.2f}".format(cell_value)
                    pdf.drawString(13 + (col_idx * col_width), y_position, str(cell_value))
                y_position -= 15
                row_counter += 1  # Incrementar contador para alternar el color de fondo

            # Escribir los totales si están presentes
            if totals:
                table_width = col_width * len(mapped_headers)  # ancho total de la tabla

                y_position -= 15

                pdf.setFont("Helvetica-Bold", 9)
                pdf.setFillColorRGB(0, 0, 0)
                pdf.drawString(10, y_position, "TOTALES:")
                
                # Dibujar el rectángulo de fondo (azul) antes de escribir los totales
                y_position -= 20  # Baja un poco para que no quede pegado a la palabra "TOTALES:"
                pdf.setFillColorRGB(0.8, 0.9, 1)  # Azul pálido
                pdf.rect(8, y_position - 5, table_width, 20, fill=1, stroke=0)  # Fondo azul

                # Escribir los totales encima del rectángulo
                pdf.setFillColorRGB(0, 0, 0)  # Volver a poner el texto en negro
                for col_idx, header in enumerate(mapped_headers):
                    total_value = totals.get(header, '')
                    if total_value != '':
                        if isinstance(total_value, (int, float)):
                            total_value = "{:,.2f}".format(total_value)  # Formato con separador de miles
                        pdf.drawString(13 + (col_idx * col_width), y_position, str(total_value))  # Escribir los totales

            # Función para agregar el footer con el nombre del usuario
            def draw_footer(pdf, y_position):
                # Obtener el nombre del usuario autenticado en Odoo
                user_name = request.env.user.name  # Obtener el nombre del usuario

                # Dibujar una línea negra en la parte inferior de la página
                pdf.setStrokeColorRGB(0, 0, 0)  # Color negro
                pdf.setLineWidth(1)  # Grosor de la línea
                pdf.line(20, y_position, 820, y_position)  # Dibujar la línea de izquierda a derecha
                y_position -= 20

                # Escribir el nombre del usuario debajo de la línea
                pdf.setFont("Helvetica", 8)  # Fuente para el texto
                pdf.drawString(20, y_position - 15, f"Elaborado por: {user_name} ______________________")

            # Llamada para agregar el footer con el nombre del usuario
           
            draw_footer(pdf, y_position - 30)

            pdf.save()
            output.seek(0)
            return request.make_response(
                output.read(),
                headers=[
                    ('Content-Type', 'application/pdf'),
                    ('Content-Disposition', 'attachment; filename="generated_report.pdf"')
                ]
            )

        except Exception as e:
            return request.make_response(f"Error al generar el PDF: {str(e)}", status=400)
