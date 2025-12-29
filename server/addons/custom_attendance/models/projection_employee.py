from odoo import models, fields, api
from datetime import datetime, timedelta, time
import pytz

import logging

_logger = logging.getLogger(__name__)

class EmployeeWorkEntryProjection(models.TransientModel):
    _name = 'employee.work.entry.projection'
    _description = 'Proyección de Horas Extras'

    employee_id = fields.Many2many('hr.employee', string='Empleados', required=True)
    start_date = fields.Date(string='Fecha de Inicio', required=True, default=fields.Date.today)
    end_date = fields.Date(string='Fecha de Fin', required=True)
    total_hours = fields.Float(string='Horas Totales Proyectadas')
    normal_hours = fields.Float(string='Horas Normales Proyectadas')
    extra_hours = fields.Float(string='Horas Extras Proyectadas')
    overtime_type = fields.Char(string='Tipo de Hora Extra')
    hour_value = fields.Float(string='Valor por Hora', digits=(16, 2))
    total_value = fields.Float(string='Valor Total', digits=(16, 2))

    def generate_perfect_attendances(self, employees, start_date, end_date):
        # 1. Preparar datos
        employee_ids = employees.ids
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date)
            current_date += timedelta(days=1)

        model_basic = self.env['hr.attendance.import'].sudo()

        # 2. Obtener todos los rangos de una vez
        ranges_by_employee = model_basic.get_range_resource_calendar_massive(employee_ids, dates)

        # 3. Configuración del sistema
        type_of_resource = self.env['ir.config_parameter'].sudo().get_param(
            'hr_payroll.mode_of_attendance', 'history'  # default a 'history'
        )

        attendances = {}

        # 4. Generar asistencias por empleado y fecha
        for emp_id in employee_ids:
            for date in dates:
                date_key = (emp_id, date)

                # 5. Obtener rangos según prioridad
                ranges_contracts = []
                is_especial_turn = False

                # Priorizar 'history' sobre 'employee'
                for source_type in ['history', 'employee']:
                    if ranges_contracts:  # Si ya encontramos rangos, no buscar más
                        break

                    # Verificar si debemos usar este tipo de fuente
                    if source_type == 'employee' and type_of_resource != 'employee':
                        continue

                    emp_ranges = ranges_by_employee.get(emp_id, {}).get(date, {}).get(source_type, {})
                    ranges_contracts = emp_ranges.get('ranges', [])
                    is_especial_turn = emp_ranges.get('is_special_shift', False)

                    # 6. Manejo de turnos especiales (extender al día siguiente)
                    if is_especial_turn and ranges_contracts:
                        next_day = date + timedelta(days=1)
                        if next_day in dates:  # Solo si el día siguiente está en nuestro rango
                            next_ranges = ranges_by_employee.get(emp_id, {}).get(next_day, {}).get(source_type, {})
                            ranges_contracts.extend(next_ranges.get('ranges', []))
                            ranges_contracts = model_basic.filtrar_turno_especial(ranges_contracts)

                # 7. Generar asistencias desde los rangos
                if ranges_contracts:
                    attendances_for_day = self._create_attendances_from_ranges(
                        emp_id, date, ranges_contracts, is_especial_turn
                    )

                    if attendances_for_day:
                        attendances[date_key] = attendances_for_day


        return attendances, ranges_by_employee

    def _create_attendances_from_ranges(self, emp_id, date, ranges_contracts, is_especial_turn):
        attendances_for_day = []

        for range_info in ranges_contracts:
            try:
                # Los rangos vienen como diccionarios con 'start', 'end', 'is_extraordinary'
                if isinstance(range_info, dict):
                    if 'start' in range_info and 'end' in range_info:
                        start_time = range_info['start']
                        end_time = range_info['end']

                        # Verificar que sean datetime objects
                        if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
                            _logger.warning(f"Tiempos no son datetime: start={type(start_time)}, end={type(end_time)}")
                            continue

                    else:
                        _logger.warning(f"Diccionario sin claves 'start'/'end': {range_info}")
                        continue

                # Fallback: Si vienen como tuplas (hora_inicio, hora_fin) - formato anterior
                elif isinstance(range_info, (list, tuple)) and len(range_info) >= 2:
                    hour_from, hour_to = range_info[0], range_info[1]

                    # Convertir horas float a datetime
                    start_time = self._convert_float_to_datetime(date, hour_from)
                    end_time = self._convert_float_to_datetime(date, hour_to)

                    # Manejar turnos que cruzan medianoche
                    if end_time <= start_time or is_especial_turn:
                        if hour_to < hour_from:  # Definitivamente cruza medianoche
                            end_time += timedelta(days=1)
                else:
                    _logger.warning(f"Formato de rango no reconocido: {range_info} (tipo: {type(range_info)})")
                    continue

                # Validar que end_time > start_time (excepto para turnos nocturnos ya manejados)
                if end_time <= start_time and not is_especial_turn:
                    _logger.warning(
                        f"Tiempo fin <= tiempo inicio para empleado {emp_id} en {date}: {start_time} -> {end_time}")
                    # Para turnos nocturnos, agregar un día al end_time
                    end_time += timedelta(days=1)

                attendance = {
                    'employee_id': emp_id,
                    'check_in': self.convert_to_utc(start_time),
                    'check_out': self.convert_to_utc(end_time),
                }

                attendances_for_day.append(attendance)
                _logger.debug(f"Asistencia creada: empleado {emp_id}, {start_time} -> {end_time}")

            except (ValueError, TypeError, IndexError, KeyError) as e:
                # Log del error y continuar
                _logger.warning(
                    f"Error creando asistencia para empleado {emp_id} en {date} con rango {range_info}: {e}")
                continue

        return attendances_for_day

    def _convert_float_to_datetime(self, date, hour_float):

        if not isinstance(hour_float, (int, float)):
            raise ValueError(f"hour_float debe ser numérico, recibido: {type(hour_float)}")

        normalized_hour = hour_float % 24
        days_offset = int(hour_float // 24)

        hours = int(normalized_hour)
        minutes = int((normalized_hour - hours) * 60)
        seconds = int(((normalized_hour - hours) * 60 - minutes) * 60)

        target_date = date + timedelta(days=days_offset)
        return datetime.combine(target_date, time(hour=hours, minute=minutes, second=seconds))

    def calculate_hour_value(self, employee_id, overtime_type, hours):

        # Obtener el empleado y su contrato activo
        employee = self.env['hr.employee'].browse(employee_id)
        contract = employee.contract_id or employee.contract_ids.filtered(
            lambda c: c.state == 'open'
        )[:1]

        if not contract:
            return 0.0, 0.0

        # Salario base del empleado
        base_salary = contract.wage

        # Valor por hora base (asumiendo 240 horas mensuales como en tu fórmula)
        base_hour_value = base_salary / 240

        # Multiplicadores según el tipo de hora
        multipliers = {
            'Normales': 1.0,
            'Nocturnas': 0.25,  # 25% adicional
            'Suplementarias': 1.5,  # 150% (50% adicional)
            'Extraordinarias': 2.0,  # 200% (100% adicional)
            'Atraso': 1.0,  # Mismo valor que normales
        }

        multiplier = multipliers.get(overtime_type, 1.0)
        hour_value = base_hour_value * multiplier
        total_value = hour_value * hours

        return hour_value, total_value

    def generate_projection(self):
        self.ensure_one()
        records = self.env['employee.work.entry.projection']
        employees = self.employee_id or self.env['hr.employee'].search([])
        employee_ids = employees.ids

        context = {
            'default_date_start': self.start_date,
            'default_date_end': self.end_date,
        }

        # Generar asistencias perfectas
        attendances, schedules = self.generate_perfect_attendances(employees, self.start_date, self.end_date)

        hr_attendance = self.env['hr.attendance'].sudo()
        get_values = True
        processed_attendances = hr_attendance._create_work_entries(
            attendances=attendances,
            schedules=schedules,
            context=context,
            get_values=get_values
        )

        # Agrupar por empleado y calcular totales
        employee_data = {}
        work_entry_type_normal_id = 1
        work_entry_type_nocturne_id = self.env.ref('hr_payroll.hr_work_entry_type_nocturne').id
        work_entry_type_suplementary_id = self.env.ref('hr_payroll.hr_work_entry_type_sumplementary').id
        work_entry_type_extraordinary_id = self.env.ref('hr_payroll.hr_work_entry_type_extraordinary').id
        work_entry_type_delay_id = self.env.ref('hr_payroll.hr_work_entry_type_delays').id

        if not isinstance(processed_attendances, (list, tuple)):
            if isinstance(processed_attendances, dict):
                processed_attendances = [processed_attendances]

        for attendance in processed_attendances:
            emp_id = attendance['employee_id']

            # Inicializar datos del empleado si no existe
            if emp_id not in employee_data:
                employee_data[emp_id] = {
                    'total_hours': 0.0,
                    'hours_by_type': {}
                }

            # Validar datos esenciales
            if 'date_start' not in attendance or 'date_stop' not in attendance:
                continue

            start = attendance['date_start']
            stop = attendance['date_stop']
            hours = (stop - start).total_seconds() / 3600

            # Acumular horas totales
            employee_data[emp_id]['total_hours'] += hours

            work_type_id = attendance.get('work_entry_type_id')

            # Determinar el tipo de trabajo y acumular horas específicas
            work_type = None
            if work_type_id == work_entry_type_normal_id:
                work_type = 'Normales'
            elif work_type_id == work_entry_type_nocturne_id:
                work_type = 'Nocturnas'
            elif work_type_id == work_entry_type_suplementary_id:
                work_type = 'Suplementarias'
            elif work_type_id == work_entry_type_extraordinary_id:
                work_type = 'Extraordinarias'
            elif work_type_id == work_entry_type_delay_id:
                work_type = 'Atraso'

            # Acumular horas por tipo específico
            if work_type:
                if work_type not in employee_data[emp_id]['hours_by_type']:
                    employee_data[emp_id]['hours_by_type'][work_type] = 0.0
                employee_data[emp_id]['hours_by_type'][work_type] += hours

        # Crear registros usando los campos existentes del modelo
        for emp_id, data in employee_data.items():
            if data['hours_by_type']:
                # Crear un registro por cada tipo de overtime
                for overtime_type, type_hours in data['hours_by_type'].items():
                    # Determinar si es hora normal o extra
                    is_normal_type = (overtime_type == 'Normales')

                    # Calcular valores monetarios
                    hour_value, total_value = self.calculate_hour_value(emp_id, overtime_type, type_hours)

                    records |= self.create({
                        'employee_id': [(6, 0, [emp_id])],  # Comando Many2many para reemplazar con emp_id
                        'start_date': self.start_date,
                        'end_date': self.end_date,
                        'total_hours': type_hours,
                        'normal_hours': type_hours if is_normal_type else 0.0,
                        'extra_hours': type_hours if not is_normal_type else 0.0,
                        'overtime_type': overtime_type,
                        'hour_value': hour_value,
                        'total_value': total_value,
                    })
            else:

                records |= self.create({
                    'employee_id': [(6, 0, [emp_id])],
                    'start_date': self.start_date,
                    'end_date': self.end_date,
                    'total_hours': data['total_hours'],
                    'normal_hours': 0.0,
                    'extra_hours': 0.0,
                    'overtime_type': 'N/A',
                    'hour_value': 0.0,
                    'total_value': 0.0,
                })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Proyección de Horas Extras',
            'res_model': 'employee.work.entry.projection',
            'view_mode': 'pivot',
            'view_id': self.env.ref('custom_attendance.view_employee_work_entry_projection_pivot').id,
            'domain': [('id', 'in', records.ids)],
        }



    def convert_to_utc(self, hour_ecuador):
        # Zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc

        # Si hora_ecuador no tiene zona horaria (naive), la localizamos
        if hour_ecuador.tzinfo is None:
            ecuador_time = ecuador_tz.localize(
                hour_ecuador)
        else:
            # Si ya tiene zona horaria, simplemente asumimos que es de Ecuador
            ecuador_time = hour_ecuador.astimezone(ecuador_tz)
        whitout_time_zone = ecuador_time.astimezone(utc_tz)
        return whitout_time_zone.replace(tzinfo=None)