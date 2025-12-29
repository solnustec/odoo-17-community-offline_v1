import json

from odoo.exceptions import UserError, ValidationError
from odoo import models, fields, api
import base64
import time
import io
from xlrd import open_workbook
import logging
import re


_logger = logging.getLogger(__name__)
class HrPayslipImport(models.TransientModel):
    _name = 'hr.payslip.import'
    _description = 'Importación de Recibo General'

    file_to_import = fields.Binary(string="Archivo a Importar", required=False)
    file_name = fields.Char(string="Nombre del Archivo")
    struct_id = fields.Many2one(
        'hr.payroll.structure',
        string='Structure',
        required=True,
        help='Defines the rules that have to be applied to this payslip, according '
             'to the contract chosen. If the contract is empty, this field isn\'t '
             'mandatory anymore and all the valid rules of the structures '
             'of the employee\'s contracts will be applied.'
    )
    is_history_payslip = fields.Boolean(string='Es una nómina de historicos', default=False)

    def limpiar_cedula(self, cell_value):
        if cell_value is None or cell_value == '':
            return ''

        cedula = str(cell_value).strip()

        if cedula.endswith('.0'):
            cedula = cedula[:-2]

        cedula = cedula.zfill(10)

        return cedula

    def action_import_payslip(self):
        if not self.file_name or not self.file_to_import:
            raise ValidationError("Por favor, sube un archivo para continuar.")

        if not self.file_name.endswith('.xlsx'):
            raise ValidationError("El archivo debe tener la extensión .xlsx.")

        start_time = time.time()

        # Leer el archivo Excel
        try:
            file_content = base64.b64decode(self.file_to_import)
            file_stream = io.BytesIO(file_content)
            workbook = open_workbook(file_contents=file_stream.getvalue())
            sheet = workbook.sheet_by_index(0)
        except Exception as e:
            raise ValidationError(f"Error al leer el archivo: {str(e)}")

        # Validar contexto activo
        payslip_run = self.env['hr.payslip.run'].sudo()
        active_ids = self.env.context.get('active_ids', [])
        if not active_ids:
            raise ValidationError("No se encontró ninguna nómina activa para procesar.")

        payslip_general = payslip_run.browse(active_ids)

        # Validar estructura del archivo
        header_row = 4
        if sheet.nrows <= header_row:
            raise ValidationError("El archivo no tiene datos suficientes.")

        headers = [sheet.cell(header_row, col).value.strip() if sheet.cell(header_row, col).value else ''
                   for col in range(sheet.ncols)]

        # Validar columnas requeridas
        expected_columns = ["NRO DE CEDULA"]
        if not all(col in headers for col in expected_columns):
            raise ValidationError(
                f"El archivo no tiene las columnas requeridas: {expected_columns}"
            )

        cedula_col_idx = headers.index("NRO DE CEDULA")

        # PASO 1: Recopilar identificaciones de empleados del Excel
        employee_identifications = set()
        for row_idx in range(header_row + 1, sheet.nrows):
            cell_value = sheet.cell(row_idx, cedula_col_idx).value
            employee_identification = self.limpiar_cedula(sheet.cell(row_idx, cedula_col_idx).value)

            if employee_identification and employee_identification != '':
                employee_identifications.add(employee_identification)

        if not employee_identifications:
            raise ValidationError("No se encontraron identificaciones de empleados válidas en el archivo.")

        # PASO 2: Buscar empleados en el sistema basado en las identificaciones del Excel
        employees = self.env['hr.employee'].sudo().with_context(active_test=False).search([
            ('identification_id', 'in', list(employee_identifications))
        ])

        if not employees:
            raise ValidationError(
                "No se encontraron empleados registrados en el sistema con las identificaciones del archivo.")

        # Verificar cuáles identificaciones no se encontraron
        found_identifications = set(employees.mapped('identification_id'))
        employees_not_found = employee_identifications - found_identifications

        # PASO 3: Eliminar slip_ids existentes del payslip_general
        if payslip_general.slip_ids:
            payslip_general.slip_ids.write({'state': 'draft'})
            payslip_general.slip_ids.unlink()

        # PASO 4: Regenerar payslips usando la función específica
        try:
            payslip_employees = self.env['hr.payslip.employees'].sudo()
            employees_witout_contract = payslip_employees._generate_payslips(payslip_general, employees,
                                                                             self.struct_id.id, self.is_history_payslip)

            employees_without_contracts_data = [
                {
                    'id': emp.id,
                    'identification_id': emp.identification_id,
                    'name': emp.name
                } for emp in employees_witout_contract
            ]

            missing_identifications_list = list(employees_not_found)

        except Exception as e:
            raise ValidationError(f"Error al generar los payslips: {str(e)}")

        # PASO 5: Crear mapeo actualizado después de la regeneración
        employee_payslip_map = {}
        for payslip in payslip_general.slip_ids:
            if payslip.employee_id and payslip.employee_id.identification_id:
                employee_payslip_map[payslip.employee_id.identification_id] = payslip.id

        if not employee_payslip_map:
            raise ValidationError("No se pudieron generar payslips válidos.")

        # PASO 6: Limpiar registros de importación existentes
        self.env['hr.payslip.import.save.lines'].sudo().search([
            ('payslip_id', 'in', list(employee_payslip_map.values()))
        ]).unlink()

        # PASO 7: Procesar e importar datos del Excel - VERSIÓN ULTRA-OPTIMIZADA
        values_to_create = []
        batch_size = 600
        processed_count = 0

        # Pre-compilar patrones para validación numérica ultra-rápida
        numeric_pattern = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)$')

        # Cache para conversiones - evita reconvertir valores repetidos
        conversion_cache = {}

        def ultra_fast_convert(cell_value):
            if cell_value is None:
                return 0.0

            # Si ya es numérico, retornar directamente
            if isinstance(cell_value, (int, float)):
                return float(cell_value)

            # Usar cache para strings ya procesados
            if cell_value in conversion_cache:
                return conversion_cache[cell_value]

            # Procesamiento optimizado para strings
            str_value = str(cell_value).strip()
            if not str_value:
                conversion_cache[cell_value] = None
                return 0.0

            # Reemplazar coma por punto una sola vez
            clean_value = str_value.replace(',', '.')

            # Validación ultra-rápida con regex
            if numeric_pattern.match(clean_value):
                result = float(clean_value)
                conversion_cache[cell_value] = result
                return result

            # Cachear strings no numéricos
            conversion_cache[cell_value] = str_value
            return str_value

        # Pre-filtrar columnas válidas para evitar verificaciones repetidas
        valid_columns = [(col_idx, rule_name) for col_idx, rule_name in enumerate(headers)
                         if col_idx != cedula_col_idx and rule_name]

        # Procesar filas con optimización máxima
        for row_idx in range(header_row + 1, sheet.nrows):
            # Obtener identificación del empleado
            employee_identification = self.limpiar_cedula(sheet.cell(row_idx, cedula_col_idx).value)
            payslip_id = employee_payslip_map.get(employee_identification)

            # Saltar si no hay payslip_id
            if not payslip_id:
                continue

            # Procesar solo columnas válidas pre-filtradas
            for col_idx, rule_name in valid_columns:
                # Obtener y convertir valor de celda
                cell_value = sheet.cell(row_idx, col_idx).value
                converted_value = ultra_fast_convert(cell_value)

                if converted_value is None:
                    converted_value = 0.0

                values_to_create.append({
                    'name': rule_name,
                    'value': converted_value,
                    'payslip_id': payslip_id,
                    'employee_id': employee_identification,
                })

            processed_count += 1

            # Crear registros en lotes más grandes
            if len(values_to_create) >= batch_size:
                self.env['hr.payslip.import.save.lines'].sudo().create(values_to_create)
                values_to_create = []

                # Limpiar cache periódicamente para evitar uso excesivo de memoria
                if processed_count % 600 == 0:
                    conversion_cache.clear()

        # Crear registros restantes
        if values_to_create:
            self.env['hr.payslip.import.save.lines'].sudo().create(values_to_create)

        if processed_count == 0:
            raise ValidationError("No se procesaron datos válidos del archivo.")

        # PASO 8: Recalcular payslips
        try:
            payslip_general.slip_ids.compute_sheet()

            employees_encoded = base64.b64encode(json.dumps(employees_without_contracts_data).encode('utf-8')).decode(
                'utf-8')
            missing_encoded = base64.b64encode(json.dumps(missing_identifications_list).encode('utf-8')).decode('utf-8')

            # Construir URL
            download_url = f'/reporte_empleados_sin_contrato/download_xlsx?employees_data={employees_encoded}&missing_data={missing_encoded}&report_name=reporte_asistencias'
            has_excel_data = bool(employees_without_contracts_data or missing_identifications_list)

            self.env['hr.payslip.import.save.lines'].sudo().search([
                ('payslip_id', 'in', list(employee_payslip_map.values()))
            ]).unlink()

            end_time = time.time()
            execution_time = end_time - start_time
            _logger.info("Tiempo de ejecucion para compute_sheet: %.2f seconds", execution_time)

            if has_excel_data:
                return {
                    'type': 'ir.actions.act_url',
                    'url': download_url,
                    'target': 'new',
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'Importación completada. Regenerados y procesados {processed_count} empleados.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
        except Exception as e:
            raise ValidationError(f"Error al recalcular nóminas: {str(e)}")


class HrPayslipImportSave(models.Model):
    _name = 'hr.payslip.import.save.lines'
    _description = 'Importación de Recibo General'

    name = fields.Char(string="Nombre la Regla Salarial")
    value = fields.Char(string="Valor o Total")
    payslip_id = fields.Many2one('hr.payslip')
    employee_id = fields.Char('Empleado Nombre')





