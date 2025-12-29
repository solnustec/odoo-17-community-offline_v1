from datetime import timedelta, datetime, time, date
import calendar
import pytz
from odoo import models, fields, api, _


class ReportAttendancesGeneral(models.TransientModel):
    _name = "autocomplete.attendance.hours"
    _description = "Reporte General de Asistencia"

    check_in_1 = fields.Boolean(string="Entrada", help="Entrada correspondiente a su horario")
    check_out_1 = fields.Boolean(string="Salida", help="Salida correspondiente a su horario")
    tolerance = fields.Float(string="Tiempo de tolerancia", help="Tiempo que servira para ajustar la marcaciones")


    def make_autocomplete_attendances(self):
        # Accedemos a los IDs de los registros seleccionados
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            attendances = self.env['hr.attendance'].browse(active_ids)
            # Lógica para procesar los registros seleccionados
            for attendance in attendances:
                employee = attendance.employee_id
                attendance_date = attendance.check_in or attendance.check_out
                ranges_entrys = False

                type_of_resource = self.env['ir.config_parameter'].sudo().get_param(
                    'hr_payroll.mode_of_attendance')

                if type_of_resource == 'employee':
                    ranges_entrys = self.get_range_resource_calendar_for_employee(employee.id, self.convertir_a_hora_ecuador(attendance_date))
                elif type_of_resource == 'departament':
                    ranges_entrys = self.get_range_resource_calendar_for_departament(employee.id, self.convertir_a_hora_ecuador(attendance_date), self.convertir_a_hora_ecuador(attendance_date))

                if ranges_entrys:
                    self._adjust_attendance(attendance, ranges_entrys, self.tolerance, self.check_in_1, self.check_out_1)
                else:
                    continue

    def get_range_resource_calendar_for_employee(self, id, date):
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
                    resource_calendar = empl.resource_calendar_id.attendance_ids
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
                resource_calendar = empl.resource_calendar_id.attendance_ids

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
                        resource_for_supplementary = resource
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
                    resource_for_supplementary = resource
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
        return False


    def convertir_a_hora_ecuador(self, hora_utc):
        # Zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc
        utc_time = utc_tz.localize(
            hora_utc)  # Asegurar que la hora esté marcada como UTC
        whitout_time_zone = utc_time.astimezone(ecuador_tz)
        return whitout_time_zone.replace(tzinfo=None)

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

    def _adjust_attendance(self, attendance, ranges_entrys, tolerance, h_check_in, h_check_out):
        """
        Ajusta las horas de check_in y check_out de acuerdo a los rangos de trabajo proporcionados.
        """
        check_in = attendance.check_in
        check_out = attendance.check_out
        margen_tolerancia = timedelta(hours=tolerance)  # Ejemplo de margen de corrección

        # Ajustar el check_in
        if h_check_in and check_in:
            for range in ranges_entrys:
                if range['start'] - margen_tolerancia <= self.convertir_a_hora_ecuador(check_in) <= range[
                    'start'] + margen_tolerancia:
                    attendance.check_in = self.convert_to_utc(range['start'])
                    attendance.is_generated = True
                    attendance.in_mode = 'sistem'
                    break

        # Ajustar el check_out
        if h_check_out and check_out:
            for range in ranges_entrys:
                if range['end'] - margen_tolerancia <= self.convertir_a_hora_ecuador(check_out) <= range[
                    'end'] + margen_tolerancia:
                    attendance.check_out = self.convert_to_utc(range['end'])
                    attendance.is_generated = True
                    attendance.out_mode = 'sistem'
                    break
