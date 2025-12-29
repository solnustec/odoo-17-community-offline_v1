from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import pandas as pd
import numpy as np
import re
import base64
import io
import logging

_logger = logging.getLogger(__name__)

class HrWorkEntryImport(models.TransientModel):
    _name = 'hr.payroll.discounts.import'
    _description = 'Importación de Descuentos Normalizado'

    file_to_import = fields.Binary(string="Archivo a Importar", required=False)
    file_name = fields.Char(string="Nombre del Archivo")
    header_row = fields.Integer(string="Fila de Encabezados", default=1,
                                help="Fila donde están los encabezados (0=primera fila)")
    date_import = fields.Date(string="Fecha de Importación",
                              default=fields.Date.today, required=True)

    # Campos para mostrar resultados
    preview_data = fields.Html(string="Vista Previa", readonly=True)
    import_summary = fields.Text(string="Resumen", readonly=True)

    def es_cedula_valida(self, cedula):
        if pd.isna(cedula) or cedula == '':
            return False

        cedula_str = str(cedula).strip().lower()

        frases_invalidas = [
            'no tiene', 'sin cedula', 'sin cédula', 'n/a', 'na', 'null',
            'none', 'vacio', 'vacío', 'no aplica', 'no disponible',
            'pendiente', 'falta', 'sin datos', 'sin documento'
        ]

        for frase in frases_invalidas:
            if frase in cedula_str:
                return False

        # Limpiar y validar que sea numérico
        cedula_limpia = re.sub(r'[^\d\-\.]', '', str(cedula))
        cedula_solo_numeros = re.sub(r'[\-\.]', '', cedula_limpia)

        if not cedula_solo_numeros.isdigit():
            return False

        if len(cedula_solo_numeros) < 6:
            return False

        return True

    def validar_monto(self, monto):

        if pd.isna(monto) or monto is None:
            return None

        # Convertir a string para limpiar
        monto_str = str(monto).strip()

        # Si está vacío
        if monto_str == '' or monto_str == ' ':
            return None

        # Frases que indican monto inválido
        frases_invalidas = ['n/a', 'na', 'null', 'none', 'no aplica']
        if monto_str.lower() in frases_invalidas:
            return None

        try:
            # Limpiar el monto de caracteres no numéricos excepto punto y coma
            monto_limpio = re.sub(r'[^\d\.\-,]', '', monto_str)

            # Reemplazar coma por punto (formato decimal)
            monto_limpio = monto_limpio.replace(',', '.')

            # Convertir a float
            valor_float = float(monto_limpio)

            # Redondear a 2 decimales para evitar problemas de precisión
            valor_redondeado = round(valor_float, 2)

            return valor_redondeado

        except (ValueError, TypeError):
            _logger.warning(f"No se pudo convertir monto: '{monto}' -> '{monto_str}'")
            return None

    def limpiar_cedula(self, cedula):
        """Limpia y formatea la cédula para que sea solo números"""
        cedula_str = str(cedula).strip()
        cedula_limpia = re.sub(r'[^\d]', '', cedula_str)
        return cedula_limpia

    def procesar_excel(self, file_content):
        try:
            # Decodificar el archivo
            file_data = base64.b64decode(file_content)
            df = pd.read_excel(io.BytesIO(file_data), header=self.header_row)

            _logger.info(f"Excel leído: {df.shape} - Columnas: {list(df.columns)}")

            # Buscar columna de cédula
            columna_cedula = None
            posibles_cedulas = ['cedula', 'cédula', 'ci', 'identificacion', 'id', 'documento']

            for col in df.columns:
                if any(cedula_term in str(col).lower() for cedula_term in posibles_cedulas):
                    columna_cedula = col
                    break

            if not columna_cedula:
                raise UserError(f"No se encontró columna de cédula. Columnas disponibles: {list(df.columns)}")

            # Encontrar columnas D-
            columnas_d = [col for col in df.columns if str(col).startswith('D-')]

            if not columnas_d:
                raise UserError("No se encontraron columnas que empiecen con 'D-'")

            # Procesar datos
            datos_transformados = []
            cedulas_invalidas = 0
            montos_invalidos = 0

            for idx, fila in df.iterrows():
                cedula = fila[columna_cedula]

                if not self.es_cedula_valida(cedula):
                    cedulas_invalidas += 1
                    continue

                cedula_limpia = self.limpiar_cedula(cedula)

                for col_d in columnas_d:
                    monto = fila[col_d]

                    # Validar y limpiar el monto
                    monto_limpio = self.validar_monto(monto)

                    if monto_limpio is None:
                        montos_invalidos += 1
                        continue

                    if monto_limpio != 0:
                        categoria = col_d[2:].strip()  # Quitar 'D-'

                        datos_transformados.append({
                            'cedula': cedula_limpia,
                            'categoria': categoria,
                            'monto': monto_limpio
                        })

            summary = {
                'total_filas_originales': len(df),
                'cedulas_invalidas': cedulas_invalidas,
                'montos_invalidos': montos_invalidos,
                'registros_procesados': len(datos_transformados),
                'columnas_d_encontradas': columnas_d,
                'columna_cedula_usada': columna_cedula
            }

            return datos_transformados, summary

        except Exception as e:
            _logger.error(f"Error procesando Excel: {str(e)}")
            raise UserError(f"Error procesando archivo Excel: {str(e)}")

    def action_preview(self):
        if not self.file_to_import:
            raise UserError("Debe seleccionar un archivo para importar")

        datos, summary = self.procesar_excel(self.file_to_import)

        # Crear vista previa HTML
        preview_html = self._create_preview_html(datos[:20])

        # Crear resumen
        summary_text = f"""
    Resumen de Importación:
    - Filas originales en Excel: {summary['total_filas_originales']}
    - Cédulas inválidas filtradas: {summary['cedulas_invalidas']}
    - Montos inválidos filtrados: {summary['montos_invalidos']}
    - Registros a procesar: {summary['registros_procesados']}
    - Columna de cédula usada: {summary['columna_cedula_usada']}
    - Categorías encontradas: {', '.join(summary['columnas_d_encontradas'])}
            """

        self.write({
            'preview_data': preview_html,
            'import_summary': summary_text
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payroll.discounts.import',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'preview_mode': True}
        }

    def _create_preview_html(self, datos):
        html = """
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Cédula</th>
                        <th>Categoría</th>
                        <th>Monto</th>
                        <th>Empleado Encontrado</th>
                    </tr>
                </thead>
                <tbody>
            """

        for dato in datos:
            employee = self.env['hr.employee'].sudo().with_context(active_test=False).search([
                ('identification_id', '=', dato['cedula'])
            ], limit=1)

            employee_name = employee.name if employee else "❌ No encontrado"
            row_class = "table-success" if employee else "table-warning"

            html += f"""
                    <tr class="{row_class}">
                        <td>{dato['cedula']}</td>
                        <td>{dato['categoria']}</td>
                        <td>${dato['monto']:,.2f}</td>
                        <td>{employee_name}</td>
                    </tr>
                """

        html += "</tbody></table>"

        if len(datos) > 20:
            html += f"<p><em>Mostrando solo los primeros 20 registros de {len(datos)} totales</em></p>"

        return html

    def action_import(self):
        if not self.file_to_import:
            raise UserError("Debe seleccionar un archivo para importar")

        datos, summary = self.procesar_excel(self.file_to_import)

        if not datos:
            raise UserError("No hay datos válidos para importar")

        # Procesar importación
        registros_creados = 0
        registros_error = 0
        errores = []

        for dato in datos:
            try:
                # Buscar empleado
                employee = self.env['hr.employee'].sudo().with_context(active_test=False).search([
                    ('identification_id', '=', dato['cedula'])
                ], limit=1)

                if not employee:
                    errores.append(f"Empleado con cédula {dato['cedula']} no encontrado")
                    registros_error += 1
                    continue

                # Buscar o crear categoría
                category = self.env['hr.payroll.discounts.category'].sudo().search([
                    ('name', '=', dato['categoria'])
                ], limit=1)

                if not category:
                    category = self.env['hr.payroll.discounts.category'].sudo().create({
                        'name': dato['categoria']
                    })

                self.env['hr.payroll.discounts'].sudo().create({
                    'employee_id': employee.id,
                    'category_id': category.id,
                    'amount': dato['monto'],
                    'date': self.date_import,
                    'description': f"Importado desde Excel - {self.file_name or 'archivo'}"
                })

                registros_creados += 1

            except Exception as e:
                errores.append(f"Error con cédula {dato['cedula']}: {str(e)}")
                registros_error += 1

        # Mensaje final
        mensaje = f"""
    Importación completada:
    ✅ Registros creados: {registros_creados}
    ❌ Registros con error: {registros_error}
            """

        if errores:
            mensaje += f"\n\nErrores encontrados:\n" + "\n".join(errores[:10])
            if len(errores) > 10:
                mensaje += f"\n... y {len(errores) - 10} errores más"

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Importación Completada',
                'message': mensaje,
                'type': 'success' if registros_creados > 0 else 'warning',
                'sticky': True
            }
        }


