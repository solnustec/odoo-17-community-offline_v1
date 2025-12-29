#-*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, time, timedelta
from collections import defaultdict
from dateutil.relativedelta import relativedelta
import pytz

from odoo import fields, api, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    is_have_exception = fields.Boolean(string='Have Exception', default=False)

    def _get_employee_calendar(self):
        self.ensure_one()
        contracts = self.employee_id.sudo()._get_contracts(self.check_in, self.check_out, states=['open', 'close'])
        if contracts:
            return contracts[0].resource_calendar_id
        return super()._get_employee_calendar()


    def get_range_resource_calendar_for_departament(self, id, date, attendances):

        empl = self.env['hr.employee'].sudo().browse(id)
        if empl:
            if 'employee.shift.changes' in self.env:
                have_exception = self.env['employee.shift.changes'].sudo().search(
                    [('date_from', '<=', date),
                     ('date_to', '>=', date),
                     ('employee_id', '=', id),
                     ('state', '=', 'approve')
                     ], limit=1
                )
                ranges_entrys = []
                resource_for_supplementary = False
                resource_calendar = None
                resource_calendar_personalized = None

                if have_exception:
                    if have_exception.type_periode == 'resource':
                        resource_calendar = have_exception.resource_calendar_id.attendance_ids
                    elif have_exception.type_periode == 'personalize':
                        resource_calendar_personalized = have_exception.ranges
                else:
                    resource = self.encontrar_horario_aproximado(attendances, empl.horarios_departamento_ids)
                    if resource:
                        resource_for_supplementary = resource.attendance_ids[0].duration_hours
                        resource_calendar = resource.attendance_ids
                    else:
                        resource_calendar = []

                if resource_calendar:
                    for range in resource_calendar:
                        if date.weekday() == int(range.dayofweek):
                            hours_in = int(range.hour_from)
                            minutes_in = int((range.hour_from - hours_in) * 60)
                            hour_time_in = time(hours_in, minutes_in)
                            date_in_contract = datetime.combine(date, hour_time_in)

                            hours_out = int(range.hour_to)
                            minutes_out = int((range.hour_to - hours_out) * 60)
                            hour_time_out = time(hours_out, minutes_out)
                            date_out_contract = datetime.combine(date, hour_time_out)

                            if range.duration_days != 0 and not range.is_extraordinary:
                                values = {
                                    'start': date_in_contract,
                                    'end': date_out_contract,
                                }
                                ranges_entrys.append(values)
                elif resource_calendar_personalized:
                    for range in resource_calendar_personalized:
                        hours_in = int(range.date_from)
                        minutes_in = int((range.date_from - hours_in) * 60)
                        hour_time_in = time(hours_in, minutes_in)
                        date_in_contract = datetime.combine(date, hour_time_in)

                        hours_out = int(range.date_to)
                        minutes_out = int((range.date_to - hours_out) * 60)
                        hour_time_out = time(hours_out, minutes_out)
                        date_out_contract = datetime.combine(date, hour_time_out)

                        values = {
                            'start': date_in_contract,
                            'end': date_out_contract,
                        }
                        ranges_entrys.append(values)

                if ranges_entrys:
                    return ranges_entrys, resource_for_supplementary
                else:
                    return False, False

            else:
                ranges_entrys = []
                resource_for_supplementary = False
                resource = self.encontrar_horario_aproximado(attendances, empl.horarios_departamento_ids)
                if resource:
                    resource_for_supplementary = resource.attendance_ids[0].duration_hours
                    resource_calendar = resource.attendance_ids
                else:
                    resource_calendar = []

                for range in resource_calendar:
                    if date.weekday() == int(range.dayofweek):
                        hours_in = int(range.hour_from)
                        minutes_in = int((range.hour_from - hours_in) * 60)
                        hour_time_in = time(hours_in, minutes_in)
                        date_in_contract = datetime.combine(date, hour_time_in)

                        hours_out = int(range.hour_to)
                        minutes_out = int((range.hour_to - hours_out) * 60)
                        hour_time_out = time(hours_out, minutes_out)
                        date_out_contract = datetime.combine(date, hour_time_out)

                        if range.duration_days != 0 and not range.is_extraordinary:
                            values = {
                                'start': date_in_contract,
                                'end': date_out_contract,
                            }
                            ranges_entrys.append(values)
                if ranges_entrys:
                    return ranges_entrys, resource_for_supplementary
                else:
                    return False, False
        return False, False

    def encontrar_horario_aproximado(self, asistencias, resource_calendar):
        def calcular_diferencia(date_start, date_stop, attendance):
            """Calcula la diferencia en segundos entre la asistencia y el attendance_id."""
            # Construir las fechas de inicio y fin del attendance
            hours_in = int(attendance.hour_from)
            minutes_in = int((attendance.hour_from - hours_in) * 60)
            start = datetime.combine(date_start.date(), time(hours_in, minutes_in))

            hours_out = int(attendance.hour_to)
            minutes_out = int((attendance.hour_to - hours_out) * 60)
            end = datetime.combine(date_stop.date(), time(hours_out, minutes_out))

            # Calcular la diferencia total
            inicio_diff = abs((date_start - start).total_seconds())
            fin_diff = abs((date_stop - end).total_seconds())
            return inicio_diff + fin_diff

        mejor_recurso = None
        diferencia_minima_total = float('inf')

        # Recorrer cada recurso del calendario
        for recurso in resource_calendar:
            diferencia_acumulada = 0  # Para acumular diferencias por recurso

            # Revisar cada asistencia y calcular la diferencia con este recurso
            for asistencia in asistencias:
                mejor_diferencia = float('inf')

                # Revisar los días definidos en `attendance_ids` del recurso
                for attendance in recurso.attendance_ids:
                    # Comparar el día de la semana entre la asistencia y el attendance
                    if self.convertir_a_hora_ecuador(asistencia['date_start']).weekday() == int(attendance.dayofweek):
                        # Calcular la diferencia para este attendance
                        diferencia = calcular_diferencia(
                            self.convertir_a_hora_ecuador(asistencia['date_start']), self.convertir_a_hora_ecuador(asistencia['date_stop']),
                            attendance
                        )
                        # Guardar la menor diferencia para esta asistencia
                        if diferencia < mejor_diferencia:
                            mejor_diferencia = diferencia

                # Acumular la mejor diferencia para este recurso
                diferencia_acumulada += mejor_diferencia

            # Si este recurso tiene la menor diferencia total, lo guardamos
            if diferencia_acumulada < diferencia_minima_total:
                diferencia_minima_total = diferencia_acumulada
                mejor_recurso = recurso

        if not mejor_recurso:
            return False

        return mejor_recurso


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

    def aplicar_convert_to_utc(self, work_entries):

        for entry in work_entries:
            # Aplicar el método self.convert_to_utc al campo date_start y date_stop
            entry['date_start'] = self.convert_to_utc(entry['date_start'])
            entry['date_stop'] = self.convert_to_utc(entry['date_stop'])

        return work_entries

    def convertir_a_hora_ecuador(self, hora_utc):
        # Zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc
        utc_time = utc_tz.localize(
            hora_utc)  # Asegurar que la hora esté marcada como UTC
        whitout_time_zone = utc_time.astimezone(ecuador_tz)
        return whitout_time_zone.replace(tzinfo=None)

    def is_overlapping(self, existing_attendance, new_start, new_stop):

        return not (new_stop <= existing_attendance['date_start'] or
                    new_start >= existing_attendance['date_stop'])



    def calculate_diference(self, attendance_start, attendance_end):

        difference = (attendance_end - attendance_start).total_seconds() / 60
        return difference

    def get_name_employee(self, id, type):

        employee = self.env['hr.employee'].sudo().browse(id)
        return type + employee.name if employee else "Empleado no Identificado"

    def redondear_hora_hacia_arriba(self, fecha):

        if isinstance(fecha, str):
            try:
                fecha = datetime.strptime(fecha, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                raise ValueError(
                    "El formato de fecha no es válido. Se espera '%Y-%m-%d %H:%M:%S'")

        # Si los minutos son mayores que 0, redondeamos la hora hacia arriba
        if fecha.minute > 0:
            fecha = fecha + timedelta(hours=1)
            fecha = fecha.replace(minute=0, second=0, microsecond=0)
        else:
            fecha = fecha.replace(second=0, microsecond=0)

        return fecha

    def redondear_hora_hacia_abajo(self, fecha):

        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, '%Y-%m-%d %H:%M:%S')

        if fecha.minute >= 57:
            fecha = fecha + timedelta(hours=1)
            fecha = fecha.replace(minute=0, second=0, microsecond=0)
        else:
            fecha = fecha.replace(minute=0, second=0, microsecond=0)

        return fecha

    def verificar_secciones(self, rangos, entrada, salida):
        dentro_rangos = []
        fuera_rangos = []

        actual_inicio = entrada

        for rango in rangos:
            start = rango['start']
            end = rango['end']

            if actual_inicio > end:
                continue

            if start > salida:
                break

            if actual_inicio < start:
                fuera_rangos.append({
                    'start': actual_inicio,
                    'end': start
                })
                actual_inicio = start

            seccion_dentro = max(actual_inicio, start), min(salida, end)

            if seccion_dentro[0] <= seccion_dentro[1]:
                dentro_rangos.append({
                    'start': seccion_dentro[0],
                    'end': seccion_dentro[1],
                })
                actual_inicio = seccion_dentro[1]

        if actual_inicio < salida:
            fuera_rangos.append({
                'start': actual_inicio,
                'end': salida
            })

        return {
            'nocturne': dentro_rangos,
            'diurne': fuera_rangos
        }


    def get_schedule(self, employee_id, schedules, attendance, date, model_importation):

        emp_ranges = schedules.get(employee_id, {}).get(date, {}).get('history', {})
        limit_hours_contracts = emp_ranges.get('ranges', [])
        max_hours_for_schedule = emp_ranges.get('max_hours', 0)
        is_especial_turn = emp_ranges.get('is_special_shift', False)
        is_extraordinary = emp_ranges.get('is_extraordinary', False)

        # 4. Manejo de turnos especiales
        if is_especial_turn:
            next_day = attendance['timestamp'] + timedelta(days=1)
            next_ranges = schedules.get(employee_id, {}).get(next_day.date(), {}).get('history', {})
            limit_hours_contracts.extend(next_ranges.get('ranges', []))
            limit_hours_contracts = model_importation.filtrar_turno_especial(limit_hours_contracts)

        # 5. Si no hay rangos, intentar con modo 'employee' o 'departament'
        if not limit_hours_contracts:
            type_of_resource = self.env['ir.config_parameter'].sudo().get_param(
                'hr_payroll.mode_of_attendance')
            if type_of_resource == 'employee':
                # Usar rangos pre-cargados para 'employee'
                emp_ranges = schedules.get(employee_id, {}).get(date, {}).get('employee', {})
                limit_hours_contracts = emp_ranges.get('ranges', [])
                max_hours_for_schedule = emp_ranges.get('max_hours', 0)
                is_especial_turn = emp_ranges.get('is_special_shift', False)
                is_extraordinary = emp_ranges.get('is_extraordinary', False)

                if is_especial_turn:
                    next_day = attendance['timestamp'] + timedelta(days=1)
                    next_ranges = schedules.get(employee_id, {}).get(next_day.date(), {}).get('employee',
                                                                                              {})
                    limit_hours_contracts.extend(next_ranges.get('ranges', []))
                    limit_hours_contracts = model_importation.filtrar_turno_especial(limit_hours_contracts)
            elif type_of_resource == 'departament':
                # Mantener lógica existente para departamentos
                (
                    limit_hours_contracts,
                    max_hours_for_schedule,
                    is_especial_turn
                ) = self.get_range_resource_calendar_for_departament(
                    employee_id, attendance['timestamp'], attendance['timestamp']
                )
        return limit_hours_contracts, max_hours_for_schedule, is_especial_turn, is_extraordinary


    def _create_work_entries(self, attendances=None, schedules=None, continue_attendance=False, context=None, get_values=None):
        # Upon creating or closing an attendance, create the work entry directly if the attendance
        # was created within an already generated period
        # This code assumes that attendances are not created/written in big batches
        grace_period_value = int(self.env['ir.config_parameter'].sudo().get_param(
            'custom_attendance.grace_period_value', 0))
        grace_period_unit = self.env['ir.config_parameter'].sudo().get_param(
            'custom_attendance.grace_period_unit', 'days')
        grace_limit = int(self.env['ir.config_parameter'].sudo().get_param(
            'custom_attendance.grace_limit', 0))

        model_importation = self.env['hr.attendance.import']

        type_of_resource = self.env['ir.config_parameter'].sudo().get_param(
            'hr_payroll.mode_of_attendance')

        max_horas = int(self.env['ir.config_parameter'].sudo().get_param(
            'employee_shift_scheduling_app.max_hours_for_shift')) or 0

        max_horas_lactance = int(self.env['ir.config_parameter'].sudo().get_param(
            'employee_shift_scheduling_app.max_hours_for_lactance')) or 0

        work_entry_type_excedente_id = self.env.ref(
            'hr_payroll.hr_work_entry_type_sumplementary').id

        work_entry_type_delay_id = self.env.ref(
            'hr_payroll.hr_work_entry_type_delays').id

        periodes_lactance = self.env['hr.employee'].load_lactation_periods()


        list_final_attendances = []
        max_hours_for_schedule = 0

        inconsistencies_to_create = {}
        new_inconsistency_counts = {}

        date_to = max(att.get('check_in', datetime.min) for group in attendances.values() for att in group).date()

        if grace_period_value and grace_period_unit:
            if grace_period_unit == 'days':
                period_start = date_to - relativedelta(days=grace_period_value)
            elif grace_period_unit == 'weeks':
                period_start = date_to - relativedelta(weeks=grace_period_value)
            elif grace_period_unit == 'months':
                period_start = date_to - relativedelta(months=grace_period_value)
            elif grace_period_unit == 'years':
                period_start = date_to - relativedelta(years=grace_period_value)
            else:
                period_start = date_to
        else:
            period_start = date_to

        if context != None:

            date_range = [
                context.get('default_date_start') + timedelta(days=x)
                for x in range((context.get('default_date_end') - context.get('default_date_start')).days + 1)
            ]

            date_utc_ranges = [
                (
                    self.convert_to_utc(datetime.combine(date, time.min) + timedelta(minutes=1)),
                    self.convert_to_utc(datetime.combine(date, time.max) - timedelta(minutes=1))
                )
                for date in date_range
            ]

            employee_ids = list({key[0] for key in attendances.keys()})
            holidays_employee_dict = self._prefetch_holidays_employee(employee_ids, date_utc_ranges)

        inconsistencies = self.env['hr.attendance.inconsistencies'].read_group(
            [('date', '>=', period_start), ('date', '<=', date_to)],
            ['employee_id', 'count_inconsistencies'],
            ['employee_id'],
            lazy=False
        )

        inconsistency_counts = {}
        if inconsistencies:
            for rec in inconsistencies:
                if rec and isinstance(rec, dict):
                    employee_id = rec.get('employee_id')
                    count = rec.get('count_inconsistencies', 0)

                    # Verificar que employee_id sea una tupla/lista con al menos un elemento
                    if employee_id and isinstance(employee_id, (list, tuple)) and len(employee_id) > 0:
                        inconsistency_counts[employee_id[0]] = count
                    elif employee_id and isinstance(employee_id, (int, bool)) and employee_id is not False:
                        # Si employee_id es un entero directo o True (que se evalúa como 1)
                        inconsistency_counts[int(employee_id)] = count

        for key, group in attendances.items():

            attedances_totals = []
            extraordinary_list = []
            is_extraordinary = False
            employee_id, date = key

            if employee_id not in new_inconsistency_counts:
                new_inconsistency_counts[employee_id] = 0

            for attendance in group:

                # print("attendance", attendance)

                if 'check_in' not in attendance or 'check_out' not in attendance:
                    # continue  #todo aca esto estooo quitar
                    total_count = inconsistency_counts.get(employee_id, 0) + new_inconsistency_counts[employee_id]

                    if total_count < grace_limit:

                        # Autocompletar
                        attendance = self._autocomplete_attendance(
                            attendance, employee_id, date, schedules
                        )

                        if 'check_in' not in attendance or 'check_out' not in attendance:
                            continue

                        if (employee_id, date) not in inconsistencies_to_create:
                            inconsistencies_to_create[(employee_id, date)] = 0
                        inconsistencies_to_create[(employee_id, date)] += 1
                        new_inconsistency_counts[employee_id] += 1

                        has_overlap = False
                        for other_attendance in group:
                            if other_attendance is attendance:
                                continue

                            if (other_attendance.get('check_in') is not None and
                                    other_attendance.get('check_out') is not None and
                                    attendance.get('check_in') is not None and
                                    attendance.get('check_out') is not None):

                                if (attendance['check_in'] <= other_attendance['check_out'] and
                                        attendance['check_out'] >= other_attendance['check_in']):
                                    has_overlap = True
                                    break

                        if has_overlap:
                            continue

                    else:
                        continue


                holidays_by_employee = holidays_employee_dict.get((attendance['employee_id'], attendance['check_in'].strftime('%Y-%m-%d')), None)

                if holidays_by_employee and holidays_by_employee.get('on_leave'):
                    continue



                attendance_start_ = attendance['check_in']
                attendance_stop_ = attendance['check_out']

                #pasar los valores a zona horaria de ecuador para mejor control de sumas y restas
                attendance_start = self.convertir_a_hora_ecuador(
                    attendance_start_)
                attendance_stop = self.convertir_a_hora_ecuador(
                    attendance_stop_)


                #se le quita la zona horaria o la info por conflicto de naive
                attendance_start = attendance_start.replace(tzinfo=None) #
                attendance_stop = attendance_stop.replace(tzinfo=None) #
                limit_hours_contracts = False

                #Metodo de consummo

                # limit_hours_contracts, max_hours_for_schedule, is_especial_turn, is_extraordinary   = self.get_schedule(employee_id, schedules, attendance, date)

                #se optiene los rangos de los contratos nuevamente basandonos en que dia es y cual le corresponde
                # emp_ranges = schedules.get(employee_id, {}).get(date, {}).get('history', {})
                # limit_hours_contracts = emp_ranges.get('ranges', [])
                # max_hours_for_schedule = emp_ranges.get('max_hours', 0)
                # is_especial_turn = emp_ranges.get('is_special_shift', False)
                # is_extraordinary = emp_ranges.get('is_extraordinary', False)
                #
                # # 4. Manejo de turnos especiales
                # if is_especial_turn:
                #
                #     next_day = attendance['check_in'] + timedelta(days=1)
                #     next_ranges = schedules.get(employee_id, {}).get(next_day.date(), {}).get('history', {})
                #     limit_hours_contracts.extend(next_ranges.get('ranges', []))
                #     limit_hours_contracts = model_importation.filtrar_turno_especial(limit_hours_contracts)



                # 5. Si no hay rangos, intentar con modo 'employee' o 'departament'
                if not limit_hours_contracts:

                    if type_of_resource == 'employee':

                        emp_ranges = schedules.get(employee_id, {}).get(date, {}).get('history', {})
                        limit_hours_contracts = emp_ranges.get('ranges', [])
                        max_hours_for_schedule = emp_ranges.get('max_hours', 0)
                        is_especial_turn = emp_ranges.get('is_special_shift', False)
                        is_extraordinary = emp_ranges.get('is_extraordinary', False)

                        # 4. Manejo de turnos especiales
                        if is_especial_turn:
                            next_day = attendance['check_in'] + timedelta(days=1)
                            next_ranges = schedules.get(employee_id, {}).get(next_day.date(), {}).get('history', {})
                            limit_hours_contracts.extend(next_ranges.get('ranges', []))
                            limit_hours_contracts = model_importation.filtrar_turno_especial(limit_hours_contracts)

                    elif type_of_resource == 'departament':
                        (
                            limit_hours_contracts,
                            max_hours_for_schedule,
                            is_especial_turn
                        ) = self.get_range_resource_calendar_for_departament(
                            employee_id, attendance['timestamp'], attendance['timestamp']
                        )

                work_entry = self.create_work_entry(attendance)


                if limit_hours_contracts and not is_extraordinary:
                    attendance_list = self.check_ranges_intervals_with_delays(
                        limit_hours_contracts,
                        attendance_start,
                        attendance_stop,
                        work_entry
                    )

                    if attendance_list['delays']:

                        for delays in attendance_list['delays']:
                            dict_general = work_entry.copy()
                            dict_general['name'] = self.get_name_employee(
                                dict_general['employee_id'], "Atraso: ")
                            dict_general['date_start'] = delays['start']
                            dict_general['date_stop'] = delays['end']
                            dict_general['work_entry_type_id'] = work_entry_type_delay_id

                            attedances_totals.append(dict_general)

                    if attendance_list['inside']:

                        for diurne in attendance_list['inside']:
                            dict_general = work_entry.copy()
                            dict_general['name'] = self.get_name_employee(
                                dict_general['employee_id'], "Asistencia: ")
                            dict_general['date_start'] = diurne['start']
                            dict_general['date_stop'] = diurne['end']
                            dict_general['work_entry_type_id'] = 1

                            attedances_totals.append(dict_general)
                else:

                    extraordinary_list.append(work_entry)

            if extraordinary_list:
                if (self.is_in_lactation_period(extraordinary_list, periodes_lactance)):
                    have_periode_lactance = True
                    hours_to_work = max_horas_lactance
                else:
                    have_periode_lactance = False
                    hours_to_work = max_horas

                normal_list = self.split_entries_by_total(
                    hours_to_work,
                    have_periode_lactance,
                    work_entry_type_excedente_id,
                    extraordinary_list,
                    max_hours_for_schedule
                )

                extraordinary_list = self.convertir_extraordinarias(normal_list)
                extraordinary_list = self.filter_non_overlapping_autocompleted(extraordinary_list)
                list_final_attendances += extraordinary_list
            else:

                if (self.is_in_lactation_period(attedances_totals, periodes_lactance)):
                    have_periode_lactance = True
                    hours_to_work = max_horas_lactance
                else:
                    have_periode_lactance = False
                    hours_to_work = max_horas

                normal_list = self.split_entries_by_total(
                    hours_to_work,
                    have_periode_lactance,
                    work_entry_type_excedente_id,
                    attedances_totals,
                    max_hours_for_schedule
                )

                normal_list = self.dividir_asistencias_por_turno(normal_list)
                normal_list = self.filter_non_overlapping_delays(normal_list)
                normal_list = self.filter_non_overlapping_autocompleted(normal_list)
                normal_list = self.get_extraordinary_lapse(normal_list)
                normal_list = self.aplicar_convert_to_utc(normal_list)

                list_final_attendances += normal_list

        if not get_values:
            for (emp_id, date), count in inconsistencies_to_create.items():
                inconsistency = self.env['hr.attendance.inconsistencies'].search([
                    ('employee_id', '=', emp_id),
                    ('date', '=', date),
                ], limit=1)
                if inconsistency:
                    inconsistency.count_inconsistencies += count
                else:
                    self.env['hr.attendance.inconsistencies'].create({
                        'employee_id': emp_id,
                        'date': date,
                        'count_inconsistencies': count,
                    })


        self.clean_fields_auxiliary(list_final_attendances)
        if get_values:
            return list_final_attendances

        result = self.env['hr.work.entry'].sudo().create_entrys(list_final_attendances, continue_attendance, context)

        return result


    def clean_fields_auxiliary(self, list_final_attendances):
        for entrada in list_final_attendances:
            entrada.pop('permit', None)

    def check_ranges_intervals_with_delays(self, rangos, entrada, salida, work_entry):
        inside_intervals = []
        outside_intervals = []
        delays = []

        # Determinar si es permiso para omitir redondeos
        is_permit = work_entry.get('permit', False)

        # Helpers condicionales de redondeo
        def round_up(time):
            return time if is_permit else self.redondear_hora_hacia_arriba(time)

        def round_down(time):
            return time if is_permit else self.redondear_hora_hacia_abajo(time)

        def add_interval(interval, target_list):
            """Agrega un intervalo a la lista si no es idéntico al último."""
            if not target_list or target_list[-1] != interval:
                target_list.append(interval)

        # Ordenar rangos por inicio
        sorted_ranges = sorted(rangos, key=lambda r: r['start'])
        current = entrada

        # Caso inicial: Si el intervalo comienza antes del primer rango
        if sorted_ranges and current < sorted_ranges[0]['start']:
            add_interval({
                'start': round_up(current),
                'end': min(round_down(salida), sorted_ranges[0]['start'])
            }, outside_intervals)

        for i, rango in enumerate(sorted_ranges):
            start = rango['start']
            end = rango['end']

            # Caso 1: Todo el intervalo está antes del rango
            if current < start and salida <= start:
                add_interval({
                    'start': round_up(current),
                    'end': round_down(salida)
                }, outside_intervals)
                break

            if current < start:
                add_interval({
                    'start': round_up(current),
                    'end': start
                }, outside_intervals)
                current = start

            if start < current < end:
                delays.append({'start': start, 'end': current})
                interval_end = min(salida, end)
                if current < interval_end:
                    add_interval({
                        'start': current,
                        'end': round_down(interval_end)
                    }, inside_intervals)
                    current = interval_end

            # Caso 4: Inicio sin retraso dentro del rango
            elif current <= start < end:
                interval_end = min(salida, end)
                if start != round_down(interval_end):  # Evitar intervalos vacíos
                    add_interval({
                        'start': start,
                        'end': round_down(interval_end)
                    }, inside_intervals)
                    current = interval_end

            # Caso 5: Intervalo entre rangos (si hay un siguiente rango)
            if i + 1 < len(sorted_ranges) and current < sorted_ranges[i + 1]['start']:
                next_start = sorted_ranges[i + 1]['start']
                if current < salida:
                    add_interval({
                        'start': round_up(current),
                        'end': min(round_down(salida), next_start)
                    }, outside_intervals)
                    current = min(salida, next_start)

            if current >= salida:
                break

        # Caso final: Resto del intervalo después del último rango
        if current < salida:
            add_interval({
                'start': round_up(current),
                'end': round_down(salida)
            }, outside_intervals)

        return {
            'inside': inside_intervals,
            'outside': outside_intervals,
            'delays': delays if not is_permit else []
        }
    def convertir_extraordinarias(self, work_entries):
        for entry in work_entries:
            if "Asistencia" in entry['name']:
                # Redondea las fechas
                entry['date_start'] = self.redondear_hora_hacia_arriba(
                    entry['date_start'])
                entry['date_stop'] = self.redondear_hora_hacia_abajo(entry['date_stop'])

                duration = entry['date_stop'] - entry['date_start']

                # Asegura que la duración sea de al menos una hora
                if duration <= timedelta(hours=1):
                    entry['date_stop'] = entry['date_start'] + timedelta(hours=1)

                # Convertir a horas extraordinarias
                entry['name'] = entry['name'].replace("Asistencia",
                                                      "Horas Extraordinarias")
                entry['work_entry_type_id'] = self.env.ref(
                    'hr_payroll.hr_work_entry_type_extraordinary').id

        return work_entries


    def dividir_asistencias_por_turno(self, asistencias):
        nuevas_asistencias = []
        dict_general = {}
        for registro in asistencias:
            if 'Asistencia' in registro['name']:
                inicio = registro['date_start']
                fin = registro['date_stop']

                rangos = self.ranges_hours_nocturne(inicio)
                vals_dict = self.verificar_secciones(rangos, inicio, fin)
                if vals_dict['nocturne']:
                    for nocturne in vals_dict['nocturne']:
                        if self.calculate_diference(nocturne['start'],
                                                    nocturne['end']) >= 60:
                            dict_general = registro.copy()
                            dict_general['name'] = dict_general['name'].replace("Asistencia",
                                                              "Horas Nocturnas")
                            dict_general['date_start'] =  nocturne['start']
                            dict_general['date_stop'] = self.redondear_hora_hacia_abajo(nocturne['end'])
                            dict_general['work_entry_type_id'] = self.env.ref(
                             'hr_payroll.hr_work_entry_type_nocturne').id

                            nuevas_asistencias.append(dict_general)
                if vals_dict['diurne']:
                    for diurne in vals_dict['diurne']:
                        dict_general = registro.copy()
                        dict_general['date_start'] = diurne['start']
                        dict_general['date_stop'] = diurne['end']
                        nuevas_asistencias.append(dict_general)

            else:
                nuevas_asistencias.append(registro)

        return nuevas_asistencias




    ############## NUEVAS FUCNIONES PARA CALCULAR HORAS EXTRAS EN ASISTENCIAS ##########
    ####################################################################################
    ####################################################################################
    ####################################################################################
    ####################################################################################

    def get_horario_by_attendance (self, attendance):
        pass


    def create_work_entry (self, attendance):
        if attendance:
            return {
                'name': "Asistencia",
                'date_start': attendance['check_in'],
                'date_stop': attendance['check_out'],
                'work_entry_type_id': 1,
                'employee_id': attendance['employee_id'],
                'company_id': 1,
                'state': 'draft',
                'is_credit_time': True,
                'is_autocompleted': attendance.get('is_autocompleted', False),
                'permit': attendance.get('permit', False),
                # 'attendance_ds': attendance_today.id
            }

    def split_entries_by_total(self, max_horas, have_periode_lactance, work_entry_type_excedente_id, entradas,
                               max_hours_supplementary):
        # 1. Preparación inicial y filtrado
        entradas_ordenadas = sorted(entradas, key=lambda x: x['date_start'])

        # Separar entradas normales de permisos
        entradas_normales = [e for e in entradas_ordenadas if not e.get('permit', False)]
        entradas_permisos = [e for e in entradas_ordenadas if e.get('permit', False)]

        # Ajustar límites de horas suplementarias
        max_hours_supplementary = 0 if max_hours_supplementary < max_horas else max_hours_supplementary - max_horas
        if have_periode_lactance:
            max_hours_supplementary = 0

        nueva_lista = []
        horas_acumuladas = 0
        horas_suplementarias_acumuladas = 0


        # 2. Procesar primero las entradas normales
        for entrada in entradas_normales:
            if "Atraso" in entrada['name']:
                nueva_lista.append(entrada)
                continue

            diferencia = entrada['date_stop'] - entrada['date_start']

            horas_entrada = diferencia.total_seconds() / 3600

            if horas_acumuladas < max_horas:
                horas_disponibles = max_horas - horas_acumuladas

                if horas_entrada < horas_disponibles:
                    # Agregar entrada normal completa
                    entrada_limpia = {k: v for k, v in entrada.items() if k != 'permit'}
                    nueva_lista.append(entrada_limpia)
                    horas_acumuladas += horas_entrada
                else:

                    fecha_fin_normal = self.redondear_hora_hacia_abajo(
                        self.redondear_hora_hacia_arriba(entrada['date_start']) + timedelta(hours=horas_disponibles))

                    # Parte normal
                    entrada_normal = entrada.copy()
                    entrada_normal['date_stop'] = fecha_fin_normal
                    entrada_normal.pop('permit', None)
                    nueva_lista.append(entrada_normal)
                    horas_acumuladas = max_horas


                    # Parte suplementaria
                    horas_restantes = horas_entrada - horas_disponibles
                    self._procesar_horas_suplementarias(
                        entrada, fecha_fin_normal, horas_restantes,
                        max_hours_supplementary, horas_suplementarias_acumuladas,
                        work_entry_type_excedente_id, nueva_lista)
            else:
                # Solo procesar como suplementaria
                self._procesar_horas_suplementarias(
                    entrada, entrada['date_start'], horas_entrada,
                    max_hours_supplementary, horas_suplementarias_acumuladas,
                    work_entry_type_excedente_id, nueva_lista)

        # 3. Procesar entradas de permisos solo si no se alcanzó el máximo

        for entrada in entradas_permisos:

            entrada_limpia = {k: v for k, v in entrada.items() if k != 'permit'}
            entrada_limpia['name'] = "Permiso"
            entrada_limpia['work_entry_type_id'] = self.env.ref(
                              'hr_payroll.hr_work_entry_type_permit').id
            nueva_lista.append(entrada_limpia)

        return nueva_lista

    def _procesar_horas_suplementarias(self, entrada, fecha_inicio, horas, max_suplementarias,
                                       acumulador_suplementarias, tipo_entrada_id, lista_resultado):
        if horas <= 0 or acumulador_suplementarias >= max_suplementarias:
            return

        horas_disponibles = max_suplementarias - acumulador_suplementarias
        horas_a_agregar = min(horas, horas_disponibles)

        if horas_a_agregar <= 0:
            return

        nueva_entrada = entrada.copy()
        nueva_entrada['date_start'] = fecha_inicio
        nueva_entrada['date_stop'] = self.redondear_hora_hacia_abajo(
            fecha_inicio + timedelta(hours=horas_a_agregar))
        nueva_entrada['work_entry_type_id'] = tipo_entrada_id
        nueva_entrada['name'] = self.get_name_employee(
            nueva_entrada['employee_id'], 'Horas Suplementarias: ')
        nueva_entrada.pop('permit', None)

        if nueva_entrada['date_start'] < nueva_entrada['date_stop']:
            lista_resultado.append(nueva_entrada)
            acumulador_suplementarias += horas_a_agregar



    def get_extraordinary_lapse(self, normal_list):
        start_minor = normal_list[0][
            'date_start'] if normal_list else None

        date_stop_major = max(entrada['date_stop'] for entrada in
                              normal_list) if normal_list else None
        employee_id = normal_list[0][
            'employee_id'] if normal_list else None

        nuevas_asistencias = []

        if start_minor and date_stop_major and employee_id:
            query_holidays = self.get_holidays_national(start_minor, date_stop_major, employee_id)

            if query_holidays:
                for registro in normal_list:
                    if 'Atraso' in registro['name']:
                        nuevas_asistencias.append(registro)
                        continue

                    inicio = registro['date_start']
                    fin = registro['date_stop']

                    vals_dict = self.verificar_secciones(query_holidays, inicio, fin)
                    if vals_dict['nocturne']:
                        for nocturne in vals_dict['nocturne']:
                            if self.calculate_diference(nocturne['start'],
                                                        nocturne['end']) >= 60:
                                dict_general = registro.copy()
                                dict_general['name'] = dict_general['name'].replace("Asistencia",
                                                                  "Horas Extraordinarias")
                                dict_general['date_start'] =  self.redondear_hora_hacia_arriba(nocturne['start'])
                                dict_general['date_stop'] = self.redondear_hora_hacia_abajo(nocturne['end'])
                                dict_general['work_entry_type_id'] = self.env.ref(
                                 'hr_payroll.hr_work_entry_type_extraordinary').id

                                nuevas_asistencias.append(dict_general)
                            else:
                                dict_general = registro.copy()
                                dict_general['date_start'] = nocturne['start']
                                dict_general['date_stop'] = nocturne['end']
                    if vals_dict['diurne']:
                        for diurne in vals_dict['diurne']:
                            dict_general = registro.copy()
                            dict_general['date_start'] = diurne['start']
                            dict_general['date_stop'] = diurne['end']
                            nuevas_asistencias.append(dict_general)

            else:
                nuevas_asistencias = normal_list
        else:
            nuevas_asistencias = normal_list

        return nuevas_asistencias


    def ranges_hours_nocturne(self, fecha):

        ranges = [
            {
                'start': fecha.replace(hour=19, minute=0, second=0, microsecond=0) - timedelta(days=1),
                'end': fecha.replace(hour=6, minute=0, second=0, microsecond=0)
            },
            {
                'start': fecha.replace(hour=19, minute=0, second=0, microsecond=0),
                'end': fecha.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)
            }
        ]

        return ranges

    def get_holidays_national(self, date_start, date_stop, employee_id):

        date_start_utc = self.convert_to_utc(date_start)
        date_stop_utc = self.convert_to_utc(date_stop)

        if isinstance(employee_id, int):
            employee_id = self.env['hr.employee'].sudo().browse(employee_id)

        national = self.env['resource.calendar.leaves'].sudo().search([
            ('type_of_leave_holiday', '=', 'national'),
            ('date_from', '<=', date_stop_utc),
            ('date_to', '>=', date_start_utc),
            ('holiday_id', '=', False),
        ])



        local = self.env['resource.calendar.leaves'].sudo().search([
            ('type_of_leave_holiday', '=', 'local'),
            ('date_from', '<=', date_stop_utc),
            ('date_to', '>=', date_start_utc),
            ('city_id', '=', employee_id.department_id.city_id.id),
            ('holiday_id', '=', False),
        ])
        def format_holiday(holiday):

            return {
                'start': self.convertir_a_hora_ecuador(holiday.date_from),
                'end': self.convertir_a_hora_ecuador(holiday.date_to),
            }

        national_formatted = [format_holiday(holiday) for holiday in national]
        local_formatted = [format_holiday(holiday) for holiday in local]
        combined_holidays = national_formatted + local_formatted

        return combined_holidays


    def is_in_lactation_period(self, attendance, lactation_dictionary):

        if not attendance:
            return False

        attendance_record = attendance[0]

        attendance_date = attendance_record.get('date_start') or attendance_record.get('date_stop')
        if not attendance_date:
            return False

        if isinstance(attendance_date, datetime):
            attendance_date = attendance_date.date()

        employee_id = attendance_record.get('employee_id')
        if not employee_id:
            return False

        if employee_id not in lactation_dictionary:
            return False

        for start_period, end_period in lactation_dictionary[employee_id]:
            start_date = fields.Date.from_string(start_period)
            end_date = fields.Date.from_string(end_period)
            if start_date <= attendance_date <= end_date:
                return True
        return False

    def _autocomplete_attendance(self, attendance, employee_id, date, schedules):
        schedule = None

        if employee_id in schedules and date in schedules[employee_id]:
            schedule = schedules[employee_id][date]['history']['ranges']

        if not schedule:
            # Si no hay horario, usamos la lógica de 8 horas
            if 'check_in' in attendance and 'check_out' not in attendance:
                attendance['check_out'] = attendance['check_in'] + timedelta(hours=8)
            elif 'check_out' in attendance and 'check_in' not in attendance:
                attendance['check_in'] = attendance['check_out'] - timedelta(hours=8)
        else:
            # Obtener la marcación existente (sea check_in o check_out)
            existing_time = None
            original_field = None
            if 'check_in' in attendance:
                existing_time = attendance['check_in']
                original_field = 'check_in'
            elif 'check_out' in attendance:
                existing_time = attendance['check_out']
                original_field = 'check_out'

            if existing_time:
                # Convertimos la marcación UTC a hora local para comparar con los horarios
                local_time = self.convertir_a_hora_ecuador(existing_time)
                closest_range = None
                min_difference = timedelta.max
                is_check_in = True

                # Determinar si es entrada o salida comparando con todos los rangos
                for range_schedule in schedule:
                    range_start = range_schedule['start']
                    range_end = range_schedule['end']

                    # Si está dentro del rango, comparamos con ambos extremos
                    if range_start <= local_time <= range_end:
                        diff_start = abs(local_time - range_start)
                        diff_end = abs(local_time - range_end)
                        is_check_in = diff_start < diff_end
                        closest_range = range_schedule
                        break
                    else:
                        # Si está fuera del rango, calculamos la diferencia con ambos extremos
                        diff_start = abs(local_time - range_start)
                        diff_end = abs(local_time - range_end)

                        # Actualizamos el rango más cercano
                        if min(diff_start, diff_end) < min_difference:
                            min_difference = min(diff_start, diff_end)
                            closest_range = range_schedule
                            is_check_in = diff_start < diff_end

                if closest_range:
                    # Limpiamos los valores existentes
                    attendance.pop('check_in', None)
                    attendance.pop('check_out', None)

                    if is_check_in:
                        attendance['check_in'] = existing_time
                        attendance['check_out'] = self.convert_to_utc(
                            closest_range['end'])
                    else:
                        # Si determinamos que es una salida
                        attendance['check_in'] = self.convert_to_utc(
                            closest_range['start'])
                        attendance['check_out'] = existing_time

                    attendance['is_autocompleted'] = True

        return attendance

    def _load_all_schedules(self, employee_ids, date_from, date_to):

        employees = self.env['hr.employee'].sudo().browse(employee_ids)
        employee_calendar_map = {emp.id: emp.resource_calendar_id.id for emp in employees if emp.resource_calendar_id}

        # Calendarios base
        calendar_ids = employees.mapped('resource_calendar_id').ids
        calendars = self.env['resource.calendar'].browse(calendar_ids)
        calendar_schedules = {}
        for calendar in calendars:
            # Ordenar attendance_ids por hour_from y combinar contiguos
            attendance_ids = sorted(calendar.attendance_ids, key=lambda att: att.hour_from)
            combined_schedules = self._combine_attendance_ids(attendance_ids)
            for dayofweek, schedule in combined_schedules.items():
                calendar_schedules[(calendar.id, dayofweek)] = schedule

        # Excepciones
        exceptions = self.env['employee.shift.changes'].sudo().search([
            ('employee_id', 'in', employee_ids),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
            ('state', '=', 'approve')
        ])
        exception_schedules = {}
        for exc in exceptions:
            date_range = [exc.date_from + timedelta(days=i) for i in range((exc.date_to - exc.date_from).days + 1)]
            for d in date_range:
                if exc.type_periode == 'resource' and exc.resource_calendar_id:
                    attendance_ids = sorted(exc.resource_calendar_id.attendance_ids, key=lambda att: att.hour_from)
                    combined_schedules = self._combine_attendance_ids(attendance_ids)
                    dayofweek = d.weekday()
                    if dayofweek in combined_schedules:
                        exception_schedules[(exc.employee_id.id, d)] = combined_schedules[dayofweek]
                elif exc.type_periode == 'personalize' and exc.ranges and exc.ranges[0].date_from and exc.ranges[
                    0].date_to:
                    exception_schedules[(exc.employee_id.id, d)] = {
                        'hour_from': float(exc.ranges[0].date_from / 60.0),
                        'hour_to': float(exc.ranges[0].date_to / 60.0),
                        'type': 'personalize'
                    }

        # Historial
        history = self.env['employee.schedule.history'].sudo().search([
            ('employee_id', 'in', employee_ids),
            '|', ('end_datetime', '>=', date_from), ('end_datetime', '=', False),
            ('start_datetime', '<=', date_to)
        ])
        history_schedules = {}
        for hist in history:
            start = hist.start_datetime.date()
            end = hist.end_datetime.date() if hist.end_datetime else date_to
            date_range = [start + timedelta(days=i) for i in range((end - start).days + 1)]
            for d in date_range:
                if d >= date_from and d <= date_to and hist.calendar_id:
                    attendance_ids = sorted(hist.calendar_id.attendance_ids, key=lambda att: att.hour_from)
                    combined_schedules = self._combine_attendance_ids(attendance_ids)
                    dayofweek = d.weekday()
                    if dayofweek in combined_schedules:
                        history_schedules[(hist.employee_id.id, d)] = combined_schedules[dayofweek]

        return calendar_schedules, employee_calendar_map, exception_schedules, history_schedules

    def _combine_attendance_ids(self, attendance_ids):

        schedules = {}
        for att in attendance_ids:
            dayofweek = int(att.dayofweek)
            if dayofweek not in schedules:
                schedules[dayofweek] = {'hour_from': att.hour_from, 'hour_to': att.hour_to}
            else:
                current = schedules[dayofweek]
                if abs(current['hour_to'] - att.hour_from) < 0.01:
                    current['hour_to'] = att.hour_to
                elif abs(att.hour_to - current['hour_from']) < 0.01:
                    current['hour_from'] = att.hour_from
                else:
                    # Si no son contiguos, sobrescribimos (o podrías manejar múltiples turnos)
                    schedules[dayofweek] = {'hour_from': att.hour_from, 'hour_to': att.hour_to}
        return schedules

    def filter_non_overlapping_delays(self, work_entries):
        def is_overlapping(period1, period2):
            return not (period1['date_stop'] <= period2['date_start'] or period1['date_start'] >=
                        period2['date_stop'])

        delays = [entry for entry in work_entries if 'Atraso:' in entry['name']]
        other_entries = [entry for entry in work_entries if
                         'Atraso:' not in entry['name']]

        non_overlapping_delays = []

        for delay in delays:
            overlapping = False
            for entry in other_entries:
                if is_overlapping(delay, entry):
                    overlapping = True
                    break

            if not overlapping:
                non_overlapping_delays.append(delay)
        return other_entries + non_overlapping_delays

    def filter_non_overlapping_autocompleted(self, work_entries):
        def is_overlapping(period1, period2):
            return not (period1['date_stop'] <= period2['date_start'] or
                        period1['date_start'] >= period2['date_stop'])

        autocompleted_entries = [
            entry for entry in work_entries
            if entry.get('is_autocompleted') is True
        ]

        last_problematic_entry = None
        for auto_entry in autocompleted_entries:
            other_entries = [e for e in work_entries if e != auto_entry]
            if any(is_overlapping(auto_entry, other) for other in other_entries):
                last_problematic_entry = auto_entry

        filtered_work_entries = [
            entry for entry in work_entries
            if entry != last_problematic_entry
        ]

        return [
            {k: v for k, v in entry.items() if k != 'is_autocompleted'}
            for entry in filtered_work_entries
        ]

    @api.model
    def _prefetch_holidays_employee(self, employee_ids, date_utc_ranges):
        holidays_dict = defaultdict(lambda: {'on_leave': False})

        employees = self.env['hr.employee'].sudo().browse(employee_ids)

        employee_resource_map = {emp.id: emp.resource_id.id for emp in employees if emp.resource_id}

        date_start_min = min(date_start for date_start, _ in date_utc_ranges)
        date_end_max = max(date_end for _, date_end in date_utc_ranges)

        holidays = self.env['resource.calendar.leaves'].sudo().search([
            ('holiday_id', '!=', False),
            ('date_from', '<=', date_end_max),
            ('date_to', '>=', date_start_min),
            ('holiday_id.holiday_status_id.time_type', '=', 'leave'),
            ('holiday_id.state', '=', 'validate'),
        ])

        for employee_id in employee_ids:
            resource_id = employee_resource_map.get(employee_id)
            if not resource_id:
                for date_start, _ in date_utc_ranges:
                    holidays_dict[(employee_id, date_start.date().isoformat())] = {'on_leave': False}
                continue

            for date_start, date_end in date_utc_ranges:
                relevant_holidays = holidays.filtered(
                    lambda h: (
                            h.resource_id.id == resource_id and
                            h.date_from <= date_end and
                            h.date_to.date() >= date_start.date()
                    )
                )

                holidays_dict[(employee_id, date_start.date().isoformat())] = {
                    'on_leave': bool(relevant_holidays)
                }

        return holidays_dict