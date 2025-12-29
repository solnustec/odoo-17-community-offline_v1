import gc
from datetime import datetime, time, timedelta
import pytz

from odoo import models, fields, api
from collections import defaultdict
import base64
from io import BytesIO
import zipfile
from odoo.exceptions import ValidationError

class HrWorkEntryImport(models.TransientModel):
    _name = 'hr.attendance.import'
    _description = 'Importación de Asistencias'

    file_to_import = fields.Binary(string="Archivo a Importar", required=False)
    file_name = fields.Char(string="Nombre del Archivo")

    def action_redirect_view(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asistencias',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def action_import_attendances(self, *args, **kwargs):
        if not self.file_name or not isinstance(self.file_name, str):
            raise ValidationError("Por favor, sube un archivo válido con la extensión .dat o .zip.")

        if not self.file_to_import or not isinstance(self.file_to_import, bytes):
            raise ValidationError("No se ha subido ningún archivo o el archivo es inválido.")

        if self.file_name.endswith('.zip'):
            try:
                file_content = base64.b64decode(self.file_to_import)
                zip_file = BytesIO(file_content)

                with zipfile.ZipFile(zip_file, 'r') as z:
                    file_names = z.namelist()  # Obtener los nombres de los archivos dentro del ZIP
                    attendances = []

                    for file_name in file_names:
                        if not file_name.endswith('.dat'):
                            continue

                        try:
                            file_data = z.read(file_name).decode('utf-8')
                        except UnicodeDecodeError:
                            file_data = z.read(file_name).decode('latin-1')
                        lines = file_data.splitlines()

                        for line in lines:
                            parts = line.split("\t")
                            if len(parts) >= 2:
                                user_id = parts[0].strip()
                                timestamp_str = parts[1]

                                try:
                                    timestamp = self.parse_timestamp_to_standard(timestamp_str)
                                except ValueError:
                                    raise ValidationError(
                                        f"Formato de fecha inválido en el archivo {file_name}: {line}")

                                attendances.append({
                                    "user_id": user_id,
                                    "timestamp": self.convert_to_utc(timestamp),
                                    "origen": "Importación",
                                })
                    self.env['hr.attendance.general'].create(attendances)
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Importación Exitosa',
                            'message': 'Las marcaciones han sido importadas correctamente.',
                            'type': 'success',
                            'sticky': True,
                        }
                    }

            except zipfile.BadZipFile:
                raise ValidationError("El archivo proporcionado no es un ZIP válido.")
            except Exception as e:
                raise ValidationError(f"Error al procesar el archivo ZIP: {str(e)}")

        # Procesar un archivo individual .dat
        elif self.file_name.endswith('.dat'):
            try:

                file_content = base64.b64decode(self.file_to_import).decode('utf-8')
                lines = file_content.splitlines()
                attendances = []

                for line in lines:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        user_id = parts[0].strip()
                        timestamp_str = parts[1]

                        try:
                            timestamp = self.parse_timestamp_to_standard(timestamp_str)
                        except ValueError:
                            raise ValidationError(f"Formato de fecha inválido en la línea: {line}")

                        attendances.append({
                            "user_id": user_id,
                            "timestamp": self.convert_to_utc(timestamp),
                            "origen": "Importación",
                        })

                self.env['hr.attendance.general'].create(attendances)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Importación Exitosa',
                        'message': 'Las marcaciones han sido importadas correctamente.',
                        'type': 'success',
                        'sticky': True,
                    }
                }
            except Exception as e:
                raise ValidationError(f"Error al procesar el archivo: {str(e)}")

        else:
            raise ValidationError("Solo se permiten archivos con la extensión .dat o .zip.")

    def extract_list_final_from_attendances(self, attendances):
        nips_in_attendances = {attendance['user_id'].strip() for attendance in attendances if 'user_id' in attendance}
        list_final = list(nips_in_attendances)
        return list_final


    def get_range_resource_calendar_massive(self, employee_ids, dates, is_special_shift=False):

        employees = self.env['hr.employee'].sudo().browse(employee_ids)
        employee_dict = {emp.id: emp for emp in employees}

        # calendar_ids = [emp.resource_calendar_id.id for emp in employees if emp.resource_calendar_id]
        calendars = self.env['resource.calendar'].sudo().search_read([],[
            'id', 'attendance_ids'
        ])

        calendar_dict = {cal['id']: cal for cal in calendars}

        attendance_ids = []
        for cal in calendars:
            attendance_ids.extend(cal['attendance_ids'])
        attendances = self.env['resource.calendar.attendance'].sudo().browse(attendance_ids).read([
            'id', 'dayofweek', 'hour_from', 'hour_to', 'duration_days', 'is_extraordinary', 'duration_hours'
        ])
        attendance_dict = {att['id']: att for att in attendances}

        history_dict = {}
        history_records = self.env['employee.schedule.history'].sudo().search([
            ('employee_id', 'in', employee_ids),
            '|', ('end_datetime', '>=', min(dates)),
            ('end_datetime', '=', False)
        ]).read(['employee_id', 'calendar_id', 'start_datetime', 'end_datetime'])

        for record in history_records:
            emp_id = record['employee_id'][0]
            if emp_id not in history_dict:
                history_dict[emp_id] = []
            history_dict[emp_id].append(record)

        shift_changes = self.env['employee.shift.changes'].sudo().search([
            ('employee_id', 'in', employee_ids),
            ('state', '=', 'approve'),
            ('date_from', '<=', max(dates)),
            ('date_to', '>=', min(dates))
        ])

        shift_change_dict = {}
        for shift_change in shift_changes:
            emp_id = shift_change.employee_id.id
            if emp_id not in shift_change_dict:
                shift_change_dict[emp_id] = []
            shift_change_dict[emp_id].append(shift_change)

        max_hours_base = int(self.env['ir.config_parameter'].sudo().get_param(
            'employee_shift_scheduling_app.max_hours_for_shift', 0
        ))

        result = {}
        for emp_id in employee_ids:
            result[emp_id] = {}
            for date in dates:
                # Calcular rangos para 'history'
                history_ranges = self._compute_ranges(
                    emp_id, date, 'history', employee_dict, calendar_dict, attendance_dict,
                    history_dict.get(emp_id, []), shift_change_dict.get(emp_id, []),
                    max_hours_base,  is_special_shift
                )

                # Calcular rangos para 'employee'
                employee_ranges = self._compute_ranges(
                    emp_id, date, 'employee', employee_dict, calendar_dict, attendance_dict,
                    [], shift_change_dict.get(emp_id, []), max_hours_base, is_special_shift
                )

                result[emp_id][date] = {
                    'history': {
                        'ranges': history_ranges[0],
                        'max_hours': history_ranges[1],
                        'is_extraordinary': history_ranges[2],
                        'is_special_shift': history_ranges[3]
                    },
                    'employee': {
                        'ranges': employee_ranges[0],
                        'max_hours': employee_ranges[1],
                        'is_extraordinary': employee_ranges[2],
                        'is_special_shift': employee_ranges[3]
                    }
                }

        return result

    def parse_timestamp_to_standard(self, timestamp_str):

        possible_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
            "%m-%d-%Y %H:%M:%S",
        ]

        for fmt in possible_formats:
            try:
                timestamp = datetime.strptime(timestamp_str, fmt)
                return timestamp
            except ValueError:
                continue

        raise ValueError(f"No se pudo parsear el timestamp: {timestamp_str}")


    def _compute_ranges(self, emp_id, date, type, employee_dict, calendar_dict, attendance_dict,
                        history_records, shift_changes, max_hours_base, is_special_shift):

        ranges_entries = []
        max_hours_supplementary = 0
        is_extraordinary = False
        type_periode = 'resource'

        employee = employee_dict.get(emp_id)
        if not employee:
            return [], 0, False, False

        shift_change = None
        for change in shift_changes:
            date_from = change.date_from if change.date_from else None
            date_to = change.date_to if change.date_to else None
            if date_from and date_to and date_from <= date <= date_to:
                shift_change = change
                break

        if type == 'history':
            history_calendar = None
            for record in history_records:
                start_date = record['start_datetime'].date() if record['start_datetime'] else None
                end_date = record['end_datetime'].date() if record['end_datetime'] else None

                # Si tiene fecha de inicio y la fecha consultada es >= fecha de inicio
                if start_date and start_date <= date:
                    # Si no tiene fecha de fin (activo indefinidamente) O si tiene fecha de fin y aún no ha terminado
                    if end_date is None or end_date >= date:
                        history_calendar = record
                        break

            if history_calendar and history_calendar['calendar_id']:
                calendar = calendar_dict.get(history_calendar['calendar_id'][0])

                if calendar:
                    ranges_entries, max_hours_supplementary, is_special_shift, is_extraordinary = self._get_ranges_from_calendar(
                        calendar, attendance_dict, date, type_periode, is_extraordinary
                    )

                    if not ranges_entries:
                        is_extraordinary = True

            else:
                is_extraordinary = True

        elif type == 'employee':
            calendar_id = employee['resource_calendar_id'][0].id if employee['resource_calendar_id'] else None
            calendar = calendar_dict.get(calendar_id)

            if calendar:
                ranges_entries, max_hours_supplementary,is_special_shift, is_extraordinary = self._get_ranges_from_calendar(
                    calendar, attendance_dict, date, type_periode, is_extraordinary
                )

        aux = False
        if shift_change:
            max_hours_supplementary = max_hours_base + shift_change.max_hours_supplementary
            max_hours_supplementary = max_hours_base + shift_change.max_hours_supplementary
            type_periode = shift_change.type_periode
            if type_periode == 'resource':
                calendar_id = shift_change.resource_calendar_id.id if shift_change.resource_calendar_id else None
                calendar = calendar_dict.get(calendar_id)
                if calendar:
                    ranges_entries, max_hours_supplementary, is_special_shift, aux  = self._get_ranges_from_calendar(
                        calendar, attendance_dict, date, type_periode, aux
                    )
            elif type_periode == 'personalize':
                ranges_entries = self._get_ranges_from_personalized(shift_change.ranges, date)

        return ranges_entries, max_hours_supplementary, is_extraordinary, is_special_shift

    def _get_ranges_from_calendar(self, calendar, attendance_dict, date, type_periode, is_extraordinary):

        ranges_entries = []
        max_hours_supplementary = 0
        is_special_shift = False

        for att_id in calendar['attendance_ids']:
            att = attendance_dict.get(att_id)
            if not att:
                continue
            if type_periode == 'resource' and date.weekday() == int(att['dayofweek']):
                hours_in = int(att['hour_from'])
                minutes_in = int((att['hour_from'] - hours_in) * 60)
                hour_time_in = time(hours_in, minutes_in)
                date_in_contract = datetime.combine(date, hour_time_in)

                hours_out = int(att['hour_to'])
                minutes_out = int((att['hour_to'] - hours_out) * 60)
                if hours_out == 24:
                    is_special_shift = True
                    hours_out = 0
                    date_out_contract = datetime.combine(date + timedelta(days=1), time(hours_out, minutes_out))
                else:
                    date_out_contract = datetime.combine(date, time(hours_out, minutes_out))

                if att['duration_days'] != 0:

                    ranges_entries.append({
                        'start': date_in_contract,
                        'end': date_out_contract,
                        'is_extraordinary': att['is_extraordinary'],
                    })
                    is_extraordinary = att['is_extraordinary']
                    max_hours_supplementary += att.get('duration_hours', 0)

        return ranges_entries, max_hours_supplementary, is_special_shift, is_extraordinary

    def _get_ranges_from_personalized(self, ranges, date):

        ranges_entries = []
        for range_record in ranges:
            if not range_record.date_from or not range_record.date_to:
                continue

            hours_in = int(float(range_record.date_from))
            minutes_in = int((float(range_record.date_from) - hours_in) * 60)
            date_in_contract = datetime.combine(date, time(hours_in, minutes_in))

            hours_out = int(float(range_record.date_to))
            minutes_out = int((float(range_record.date_to) - hours_out) * 60)

            if hours_out == 24:
                hours_out = 0
                date_out_contract = datetime.combine(date + timedelta(days=1), time(hours_out, minutes_out))
            else:
                date_out_contract = datetime.combine(date, time(hours_out, minutes_out))

            ranges_entries.append({
                'start': date_in_contract,
                'end': date_out_contract,
            })
        return ranges_entries


    def process_attendance(self, attendances, list_final, continue_attendance, context):

        list_permits = self.get_permits_attendance_format(context.get('default_date_start'),
                                                          context.get('default_date_end'))

        nips_in_permits = {
            permit['user_id'].strip()
            for permit in list_permits
            if 'user_id' in permit
        }

        list_final = list(set(list_final).union(nips_in_permits))

        # 1. Preparar datos para consulta masiva
        employees = self.env['hr.employee'].with_context(active_test=False).search([('pin', 'in', list_final)])
        user_dict = {employee.pin: employee.id for employee in employees}
        employee_ids = list(user_dict.values())
        dates = list(set(attendance['timestamp'].date() for attendance in attendances))



        ##### ver por aca si se peude validar contratos

        min_d, max_d = dates[0], dates[-1]
        # Validación/obtención de contratos ANTES de los calendarios
        preload = self.env['hr.work.entry']._load_employee_contracts(
            employee_ids,
            [(eid, min_d, max_d) for eid in employee_ids],
            continue_attendance=continue_attendance,
            context=context
        )
        if isinstance(preload, dict) and preload.get('type') == 'ir.actions.act_window' and not continue_attendance:
            return preload


        ### fin

        ranges_by_employee = self.get_range_resource_calendar_massive(employee_ids, dates)


        list_attendances = []
        list_exceptiones = []

        # 3. Procesar asistencias
        for attendance in attendances:
            attendance_timestamp = self.convert_to_ecuador_time(attendance['timestamp'])
            user_id = attendance['user_id'].strip()
            emp_id = user_dict.get(user_id)
            if not emp_id:
                continue

            date = attendance['timestamp'].date()
            # Obtener rangos para 'history'
            emp_ranges = ranges_by_employee.get(emp_id, {}).get(date, {}).get('history', {})
            ranges_contracts = emp_ranges.get('ranges', [])
            max_hours_for_schedule = emp_ranges.get('max_hours', 0)
            is_especial_turn = emp_ranges.get('is_special_shift', False)
            is_extraordinary = emp_ranges.get('is_extraordinary', False)

            # 4. Manejo de turnos especiales
            if is_especial_turn:
                next_day = attendance['timestamp'] + timedelta(days=1)
                next_ranges = ranges_by_employee.get(emp_id, {}).get(next_day.date(), {}).get('history', {})
                ranges_contracts.extend(next_ranges.get('ranges', []))
                ranges_contracts = self.filtrar_turno_especial(ranges_contracts)

            # 5. Si no hay rangos, intentar con modo 'employee' o 'departament'
            if not ranges_contracts:
                type_of_resource = self.env['ir.config_parameter'].sudo().get_param(
                    'hr_payroll.mode_of_attendance')
                if type_of_resource == 'employee':
                    # Usar rangos pre-cargados para 'employee'
                    emp_ranges = ranges_by_employee.get(emp_id, {}).get(date, {}).get('employee', {})
                    ranges_contracts = emp_ranges.get('ranges', [])
                    max_hours_for_schedule = emp_ranges.get('max_hours', 0)
                    is_especial_turn = emp_ranges.get('is_special_shift', False)
                    is_extraordinary = emp_ranges.get('is_extraordinary', False)

                    if is_especial_turn:
                        next_day = attendance['timestamp'] + timedelta(days=1)
                        next_ranges = ranges_by_employee.get(emp_id, {}).get(next_day.date(), {}).get('employee', {})
                        ranges_contracts.extend(next_ranges.get('ranges', []))
                        ranges_contracts = self.filtrar_turno_especial(ranges_contracts)
                elif type_of_resource == 'departament':
                    # Mantener lógica existente para departamentos
                    (
                        ranges_contracts,
                        max_hours_for_schedule,
                        is_especial_turn
                    ) = self.get_range_resource_calendar_for_departament(
                        emp_id, attendance['timestamp'], attendance['timestamp']
                    )

            # 6. Procesar rangos

            if ranges_contracts:
                for ranges_contract in ranges_contracts:
                    possibility_assistances = self.modify_time_ranges(ranges_contract)

                    if possibility_assistances:
                        i = 0
                        for possibility_attendance in possibility_assistances:

                            if (
                                    possibility_attendance['start'] <=
                                    attendance_timestamp <=
                                    possibility_attendance['end']
                            ):
                                if i == 0:
                                    list_attendances.append({
                                        "check_in": attendance['timestamp'],
                                        "user_id": user_id,
                                        "reference": attendance['reference'],
                                        "schedule": ranges_contract,
                                        "permit": False
                                    })
                                else:
                                    list_attendances.append({
                                        "check_out": attendance['timestamp'],
                                        "user_id": user_id,
                                        "reference": attendance['reference'],
                                        "schedule": ranges_contract,
                                        "permit": False
                                    })
                            else:
                                list_exceptiones.append({
                                    "none": attendance['timestamp'],
                                    "user_id": user_id,
                                    "reference": attendance['reference'],
                                    "schedule": None,
                                    "permit": False
                                })
                            i += 1
            else:
                list_exceptiones.append({
                    "none": attendance['timestamp'],
                    "user_id": user_id,
                    "reference": attendance['reference'],
                    "schedule": None,
                    "permit": False
                })

        # 7. Procesamiento final

        final_list = []


        seen = self.add_without_duplicates(list_permits, final_list)
        seen = self.add_without_duplicates(list_attendances, final_list, seen)
        self.add_without_duplicates(list_exceptiones, final_list, seen)

        del seen
        del list_attendances
        del list_exceptiones

        gc.collect()


        sorted_grouped_result = self.group_and_sort_by_user_id(final_list)
        total_vals = self.process_work_entries(sorted_grouped_result, user_dict)
        grouped = self.group_attendances_by_employee_and_date(total_vals)

        del sorted_grouped_result
        del total_vals
        gc.collect()

        result = self.env['hr.attendance']._create_work_entries(grouped, ranges_by_employee, continue_attendance, context)

        return result



    def process_work_entries(self, resultado_agrupado_ordenado, user_dict):
        total_vals = []

        for user_id, entries in resultado_agrupado_ordenado.items():
            employee_id = user_dict.get(user_id)

            # Mantener estados separados para registros con y sin permisos
            pending_check_in_normal = None  # Para permit=False
            pending_schedule_normal = None
            pending_permit_normal = None

            pending_check_in_permit = None  # Para permit=True
            pending_schedule_permit = None
            pending_permit_permit = None

            for index, current in enumerate(entries):
                # Asignación dinámica de 'none' según las reglas
                if 'none' in current:
                    previous = entries[index - 1] if index > 0 else None
                    if previous and 'check_in' in previous:
                        # Si el anterior es un check_in, transformar 'none' en check_out
                        current['check_out'] = current.pop('none')
                    else:
                        # De lo contrario, asumir que es un check_in
                        current['check_in'] = current.pop('none')

                # Determinar si es un registro con permiso o sin permiso
                is_permit_entry = current.get('permit', False)

                # Emparejamiento de check_in y check_out
                if 'check_in' in current:
                    if is_permit_entry:
                        # Manejar check_in con permiso
                        if pending_check_in_permit is not None:
                            # Si ya hay un check_in pendiente con permiso, registrar el anterior sin check_out
                            vals = {
                                'employee_id': employee_id,
                                'check_in': pending_check_in_permit,
                                'schedule': pending_schedule_permit,
                                'permit': pending_permit_permit
                            }
                            total_vals.append(vals)

                        # Guardar el nuevo check_in con permiso
                        pending_check_in_permit = current['check_in']
                        pending_schedule_permit = current['schedule']
                        pending_permit_permit = current['permit']
                    else:
                        # Manejar check_in normal (sin permiso)
                        if pending_check_in_normal is not None:
                            # Si ya hay un check_in pendiente normal, registrar el anterior sin check_out
                            vals = {
                                'employee_id': employee_id,
                                'check_in': pending_check_in_normal,
                                'schedule': pending_schedule_normal,
                                'permit': pending_permit_normal
                            }
                            total_vals.append(vals)

                        # Guardar el nuevo check_in normal
                        pending_check_in_normal = current['check_in']
                        pending_schedule_normal = current['schedule']
                        pending_permit_normal = current['permit']

                elif 'check_out' in current:
                    if is_permit_entry:
                        # Manejar check_out con permiso - solo emparejar con check_in con permiso
                        if pending_check_in_permit:
                            # Emparejar con el último check_in con permiso
                            vals = {
                                'employee_id': employee_id,
                                'check_in': pending_check_in_permit,
                                'check_out': current['check_out'],
                                'schedule': current['schedule'],
                                'permit': current['permit']
                            }
                            total_vals.append(vals)
                            pending_check_in_permit = None
                            pending_schedule_permit = None
                            pending_permit_permit = None
                        else:
                            # Si no hay check_in con permiso pendiente, agregar solo el check_out
                            vals = {
                                'employee_id': employee_id,
                                'check_out': current['check_out'],
                                'schedule': current['schedule'],
                                'permit': current['permit']
                            }
                            total_vals.append(vals)
                    else:
                        # Manejar check_out normal - solo emparejar con check_in normal
                        if pending_check_in_normal:
                            # Emparejar con el último check_in normal
                            vals = {
                                'employee_id': employee_id,
                                'check_in': pending_check_in_normal,
                                'check_out': current['check_out'],
                                'schedule': current['schedule'],
                                'permit': current['permit']
                            }
                            total_vals.append(vals)
                            pending_check_in_normal = None
                            pending_schedule_normal = None
                            pending_permit_normal = None
                        else:
                            # Si no hay check_in normal pendiente, agregar solo el check_out
                            vals = {
                                'employee_id': employee_id,
                                'check_out': current['check_out'],
                                'schedule': current['schedule'],
                                'permit': current['permit']
                            }
                            total_vals.append(vals)

            # Al final, agregar cualquier check_in sin emparejar
            if pending_check_in_normal:
                vals = {
                    'employee_id': employee_id,
                    'check_in': pending_check_in_normal,
                    'schedule': pending_schedule_normal,
                    'permit': pending_permit_normal
                }
                total_vals.append(vals)

            if pending_check_in_permit:
                vals = {
                    'employee_id': employee_id,
                    'check_in': pending_check_in_permit,
                    'schedule': pending_schedule_permit,
                    'permit': pending_permit_permit
                }
                total_vals.append(vals)

        return total_vals

    def get_range_resource_calendar(self, id, date, is_special_shift=False, type=""):

        employee = self.env['hr.employee'].sudo().browse(id)
        if not employee:
            return [], False, False, False, ""

        ranges_entries = []
        resource_calendar = None
        max_hours_exception = 0
        max_hours_supplementary = 0
        is_extraordinary = False
        type_periode = 'resource'

        if type == 'history':
            history_conditions = [('employee_id', '=', id), ('start_datetime', '<=', date)]
            history_calendar = (
                    self.env['employee.schedule.history'].sudo().search([
                        *history_conditions,
                        ('end_datetime', '>=', date)
                    ], limit=1) or
                    self.env['employee.schedule.history'].sudo().search([
                        *history_conditions,
                        ('end_datetime', '=', False)
                    ], limit=1)
            )

            if not history_calendar:
                is_extraordinary = True
            else:

                resource_calendar = history_calendar.calendar_id.attendance_ids
                (
                    ranges_entries,
                    max_hours_supplementary,
                    is_special_shift,
                    is_extraordinary
                ) = self.get_ranges_of_resource(
                    type_periode,
                    resource_calendar,
                    ranges_entries,
                    is_extraordinary,
                    date
                )


        elif type == 'employee':
            resource_calendar = employee.resource_calendar_id.attendance_ids


            (
                ranges_entries,
                max_hours_supplementary,
                is_special_shift,
                is_extraordinary
            ) = self.get_ranges_of_resource(
                type_periode,
                resource_calendar,
                ranges_entries,
                is_extraordinary,
                date
            )


        exception = self.env['employee.shift.changes'].sudo().search([
            ('date_from', '<=', date),
            ('date_to', '>=', date),
            ('employee_id', '=', id),
            ('state', '=', 'approve')
        ], limit=1)

        if exception:
            max_hours_base = int(self.env['ir.config_parameter'].sudo().get_param(
                'employee_shift_scheduling_app.max_hours_for_shift', 0))
            max_hours_exception = max_hours_base + exception.max_hours_supplementary
            resource_calendar = (exception.resource_calendar_id.attendance_ids
                                 if exception.type_periode == 'resource'
                                 else exception.ranges if exception.type_periode == 'personalize' else None)
            type_periode = exception.type_periode

        elif type == 'history' and history_calendar and history_calendar.calendar_id:
            resource_calendar = history_calendar.calendar_id.attendance_ids
        elif type == 'employee':
            resource_calendar = employee.resource_calendar_id.attendance_ids

        if resource_calendar:
            ranges_entries = []
            (
                ranges_entries,
                max_hours_supplementary,
                is_extraordinary,
                is_special_shift
            ) = self.get_ranges_of_resource(
                type_periode,
                resource_calendar,
                ranges_entries,
                is_extraordinary,
                date
            )

            return (
                ranges_entries,
                max_hours_exception or max_hours_supplementary,
                is_extraordinary,
                is_special_shift or False,
            )

        return [], max_hours_exception or max_hours_supplementary, is_extraordinary, is_special_shift or False




    def get_ranges_of_resource(self, type_periode, resource_calendar, ranges_entrys, is_day_extraordinary, date):
        max_hours_supplementary = 0
        is_especial_shift = False
        is_day_extraordinary = False

        if resource_calendar:
            for range in resource_calendar:
                if type_periode == "resource" and date.weekday() == int(range.dayofweek):
                    hours_in = int(range.hour_from)
                    minutes_in = int((range.hour_from - hours_in) * 60)
                    hour_time_in = time(hours_in, minutes_in)
                    date_in_contract = datetime.combine(date, hour_time_in)

                    hours_out = int(range.hour_to)
                    minutes_out = int((range.hour_to - hours_out) * 60)
                    if hours_out == 24:
                        is_especial_shift = True
                        hours_out = 0
                        date_out_contract = datetime.combine(date + timedelta(days=1),
                                                             time(hours_out, minutes_out))
                    else:
                        date_out_contract = datetime.combine(date, time(hours_out, minutes_out))

                    if range.duration_days != 0 and not range.is_extraordinary:
                        values = {
                            'start': date_in_contract,
                            'end': date_out_contract,
                        }
                        ranges_entrys.append(values)
                        is_day_extraordinary = range.is_extraordinary
                        max_hours_supplementary += getattr(range, 'duration_hours', 0)
                elif type_periode == "personalize":
                    for range in resource_calendar:
                        hours_in = int(range.date_from)
                        minutes_in = int((range.date_from - hours_in) * 60)
                        hour_time_in = time(hours_in, minutes_in)
                        date_in_contract = datetime.combine(date, hour_time_in)

                        hours_out = int(range.date_to)
                        minutes_out = int((range.date_to - hours_out) * 60)
                        # hour_time_out = time(hours_out, minutes_out)
                        if hours_out == 24:
                            is_especial_shift = True
                            hours_out = 0
                            date_out_contract = datetime.combine(date + timedelta(days=1),
                                                                 time(hours_out, minutes_out))
                        else:
                            date_out_contract = datetime.combine(date, time(hours_out, minutes_out))

                        values = {
                            'start': date_in_contract,
                            'end': date_out_contract,
                        }
                        ranges_entrys.append(values)


        return ranges_entrys, max_hours_supplementary, is_especial_shift, is_day_extraordinary


    def get_range_resource_calendar_for_departament(self, id, date, datetime):
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
                resource_calendar = None
                resource_calendar_personalized = None

                if have_exception:
                    if have_exception.type_periode == 'resource':
                        resource_calendar = have_exception.resource_calendar_id.attendance_ids
                    elif have_exception.type_periode == 'personalize':
                        resource_calendar_personalized = have_exception.ranges
                else:
                    resource = self.encontrar_horario_aproximado(datetime,
                                                                 empl.horarios_departamento_ids)
                    if resource:
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
                    return ranges_entrys
                else:
                    return False

            else:
                ranges_entrys = []
                resource = self.encontrar_horario_aproximado(datetime,
                                                             empl.horarios_departamento_ids)
                if resource:
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
                    return ranges_entrys
                else:
                    return False
        return False

    def encontrar_horario_aproximado(self, date_time, resource_calendar):
        def calcular_diferencia(date_time, attendance):
            """Calcula la diferencia en segundos entre el datetime y el attendance_id."""
            # Construir las fechas de inicio y fin del attendance
            hours_in = int(attendance.hour_from)
            minutes_in = int((attendance.hour_from - hours_in) * 60)
            start = datetime.combine(date_time.date(), time(hours_in, minutes_in))

            hours_out = int(attendance.hour_to)
            minutes_out = int((attendance.hour_to - hours_out) * 60)
            end = datetime.combine(date_time.date(), time(hours_out, minutes_out))

            # Calcular la diferencia total entre el datetime y los límites del attendance
            inicio_diff = abs((date_time - start).total_seconds())
            fin_diff = abs((date_time - end).total_seconds())
            return inicio_diff + fin_diff

        mejor_recurso = None
        diferencia_minima_total = float('inf')

        # Recorrer cada recurso del calendario
        for recurso in resource_calendar:
            diferencia_acumulada = 0
            mejor_diferencia = float('inf')

            # Revisar los días definidos en `attendance_ids` del recurso
            for attendance in recurso.attendance_ids:
                # Comparar el día de la semana entre el datetime y el attendance
                if date_time.weekday() == int(attendance.dayofweek):
                    # Calcular la diferencia para este attendance
                    diferencia = calcular_diferencia(date_time, attendance)

                    # Guardar la menor diferencia para este recurso
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


    def group_and_sort_by_user_id(self, lista_dicts):
        groups = defaultdict(list)

        for entry in lista_dicts:
            groups[entry['user_id']].append(entry)

        for user_id, items in groups.items():
            for item in items:

                item['timestamp'] = next(
                    (item.get(key) for key in ['check_in', 'check_out', 'none'] if
                     item.get(key) is not None),
                    float('inf')
                )

            items.sort(key=lambda x: x['timestamp'])

        return groups

    def modify_time_ranges(self, original):

        tolerance = float(
            self.env['ir.config_parameter'].sudo().get_param('employee_shift_scheduling_app.range_of_tolerance', 1.5)
        )

        start = original['start']
        end = original['end']

        first_dict = {
            'start': start - timedelta(hours=tolerance),
            'end': start + timedelta(hours=tolerance)
        }
        second_dict = {
            'start': end - timedelta(hours=tolerance),
            'end': end + timedelta(hours=tolerance)
        }

        return first_dict, second_dict

    def add_without_duplicates(self, list, list_merge, seen=None):
        if seen is None:
            seen = set()

        for item in list:
            user_id = item.get("user_id")
            timestamp = (
                    item.get("check_in")
                    or item.get("check_out")
                    or item.get("none")
            )
            if timestamp is None:
                raise ValueError(f"The element {item} must have at least one 'check_in', 'check_out', or 'none'")

            key = (timestamp, user_id)
            if key not in seen:
                list_merge.append(item)
                seen.add(key)

        return seen


    def convert_to_utc(self, hour_ecuador):
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc

        # hour_ecuador = datetime.strptime(hour_ecuador, "%Y-%m-%d %H:%M:%S")

        # Si hora_ecuador no tiene zona horaria (naive), la localizamos
        # print("revisar aca porque no funca ", hour_ecuador)
        if hour_ecuador.tzinfo is None:
            ecuador_time = ecuador_tz.localize(
                hour_ecuador)
        else:
            # Si ya tiene zona horaria, simplemente asumimos que es de Ecuador
            ecuador_time = hour_ecuador.astimezone(ecuador_tz)
        whitout_time_zone = ecuador_time.astimezone(utc_tz)
        return whitout_time_zone.replace(tzinfo=None)


    def convert_to_ecuador_time(self, hora_utc):
        # Zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc
        utc_time = utc_tz.localize(
            hora_utc)
        whitout_time_zone = utc_time.astimezone(ecuador_tz)
        return whitout_time_zone.replace(tzinfo=None)

    def get_shift_date(self, check_in, special_shift=False, special_shift_end=None):
        if special_shift and special_shift_end:
            if check_in.time() < special_shift_end:
                return (check_in - timedelta(days=1)).date()
        else:
            date = self.convert_to_ecuador_time(check_in)
            return date.date()


    def group_attendances_by_employee_and_date(self, attendances, special_shift=False, special_shift_end=None):
        groups = defaultdict(list)
        for entry in attendances:
            check_in = entry.get('check_in') or entry.get('check_out')
            shift_date = self.get_shift_date(check_in, special_shift, special_shift_end)
            key = (entry['employee_id'], shift_date)
            groups[key].append(entry)

        for key, records in groups.items():
            records.sort(key=lambda x: x.get('check_in') or x.get('check_out'))
        return groups

    def filtrar_turno_especial(self, ranges):
        resultado = []
        i = 0
        while i < len(ranges):
            seg = ranges[i]
            if seg['end'].time() == time(0, 0):
                resultado.append(seg)
                if i + 1 < len(ranges) and ranges[i + 1]['start'].time() == time(0, 0):
                    resultado.append(ranges[i + 1])
                    i += 2
                    continue
            i += 1
        return resultado

    def get_permits_attendance_format(self, date_start_min, date_end_max):
        holidays_permits = self.env['resource.calendar.leaves'].sudo().search([
            ('holiday_id', '!=', False),
            ('date_from', '<=', date_end_max),
            ('date_to', '>=', date_start_min),
            ('holiday_id.holiday_status_id.time_type', '=', 'other'),
            ('holiday_id.state', '=', 'validate'),
        ])

        result = []

        for permit in holidays_permits:
            employee = permit.holiday_id.employee_id
            if not employee or not employee.pin:
                continue

            date_from = fields.Datetime.from_string(permit.date_from)
            date_to = fields.Datetime.from_string(permit.date_to)

            time_diff = date_to - date_from
            if time_diff.total_seconds() <= 0 or time_diff.total_seconds() > 86400:
                continue

            pin = str(employee.pin)
            result.extend([
                {
                    "check_in": permit.date_from,
                    "user_id": pin,
                    "reference": None,
                    "schedule": None,
                    "permit": True
                },
                {
                    "check_out": permit.date_to,
                    "user_id": pin,
                    "reference": None,
                    "schedule": None,
                    "permit": True
                }
            ])

        return result



