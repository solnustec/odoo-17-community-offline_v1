from datetime import timedelta, datetime, time, date
import calendar
from collections import defaultdict

import math
import pytz
from odoo import models, fields, api, _


class ReportAttendancesGeneral(models.TransientModel):
    _name = "report.attendance.general"
    _description = "Reporte General de Asistencia"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    date_from = fields.Date(string='Desde', required=True,
                            default=lambda self: self._get_default_date_from())
    date_to = fields.Date(string='Hasta', required=True,
                          default=lambda self: self._get_default_date_to())
    employee_ids = fields.Many2many('hr.employee', string='Empleados', required=True)


    def download_pdf_report(self):
        # Cache system parameter
        type_of_resource = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.mode_of_attendance')
        model_import = self.env['hr.attendance.import'].sudo()
        work_entry_env = self.env['hr.work.entry'].sudo()
        leave_type_id = self.env.ref('hr_payroll.hr_work_entry_type_leaves').id

        for record in self:
            # Early validation
            if not record.employee_ids:
                continue

            # Precompute date range and UTC conversions
            date_from = datetime.combine(record.date_from, time.min)
            date_to = datetime.combine(record.date_to, time.max)
            date_range = [
                date_from + timedelta(days=x)
                for x in range((record.date_to - record.date_from).days + 1)
            ]
            date_utc_ranges = [
                (
                    self.convert_to_utc(datetime.combine(date, time.min) + timedelta(minutes=1)),
                    self.convert_to_utc(datetime.combine(date, time.max) - timedelta(minutes=1))
                )
                for date in date_range
            ]

            # Bulk unlink existing leave entries
            self.update_and_unlink(
                record.employee_ids.ids,
                date_from,
                date_to,
                leave_type_id
            )

            # Prefetch work entries
            work_entries = work_entry_env.search([
                ('employee_id', 'in', record.employee_ids.ids),
                ('date_start', '>=', date_utc_ranges[0][0]),
                ('date_stop', '<=', date_utc_ranges[-1][1]),
            ])
            work_entries_dict = defaultdict(list)
            for entry in work_entries:
                datetime_entry = self.convertir_a_hora_ecuador(entry.date_start)
                date_str = datetime_entry.date().isoformat()

                work_entries_dict[(entry.employee_id.id, date_str)].append(entry)

            # Prefetch calendar and holiday data
            calendar_dict = self._prefetch_calendar(record.employee_ids.ids, date_range, type_of_resource)
            holidays_dict = self._prefetch_holidays(record.employee_ids.ids, date_utc_ranges)
            holidays_employee_dict = self._prefetch_holidays_employee(record.employee_ids.ids, date_utc_ranges)
            holidays_employee_permits_dict = self._prefetch_holidays_employee_permits(record.employee_ids.ids,
                                                                                      date_utc_ranges)
            lactation_employee_dict = self.prefetch_lactation_employee(record.employee_ids.ids, date_utc_ranges)

            # print("Revisar como andan los prmisos  ")
            # print("Revisar como andan los prmisos  ", holidays_employee_permits_dict)
            # print("Revisar como andan los prmisos  ")

            list_vals_general = []
            for idx, current_date in enumerate(date_range):
                current_date_start, current_date_stop = date_utc_ranges[idx]
                next_date = current_date + timedelta(days=1)

                for employee in record.employee_ids:
                    work_entry_date = work_entries_dict.get((employee.id, current_date.date().isoformat()), [])

                    calendar_data = calendar_dict.get((employee.id, current_date.isoformat()), None)

                    holidays = holidays_dict.get((employee.id, current_date.strftime('%Y-%m-%d')), None)
                    holidays_by_employee = holidays_employee_dict.get((employee.id, current_date.strftime('%Y-%m-%d')),
                                                                      {})
                    holidays_employee_permits = holidays_employee_permits_dict.get(
                        (employee.id, current_date.strftime('%Y-%m-%d')),
                        {})
                    lactation_employee = lactation_employee_dict.get(
                        (employee.id, current_date.strftime('%Y-%m-%d')),
                        {})

                    # print("++++++++++++++++++++++++++++")
                    # print("valores aca holidays", current_date)
                    # print("valores aca holidays_by_employee", holidays_by_employee)
                    # print("valores aca employee.name", employee.name)
                    # print("valores aca employee.id", employee.id)
                    # print("valores aca get aca", (employee.id, current_date.strftime('%Y-%m-%d')))
                    # print("++++++++++++++++++++++++++++")

                    ranges_to_day = calendar_data['ranges'] if calendar_data else []
                    is_special_turn = calendar_data['is_special_turn'] if calendar_data else False
                    max_hours_for_schedule = calendar_data['max_hours'] if calendar_data else 0
                    is_extraordinary = calendar_data['is_extraordinary'] if calendar_data else False

                    # Handle special turns
                    if is_special_turn and calendar_dict.get((employee.id, next_date.isoformat())):
                        next_calendar = calendar_dict[(employee.id, next_date.isoformat())]
                        ranges_to_day = ranges_to_day + next_calendar['ranges']
                        ranges_to_day = model_import.filtrar_turno_especial(ranges_to_day)

                    # Skip if no ranges or holidays exist
                    has_national_holidays = bool(holidays.get('national', False))
                    has_province_holidays = bool(holidays.get('province', False))

                    if (
                            not ranges_to_day
                            or has_national_holidays
                            or has_province_holidays
                            or holidays_by_employee.get('on_leave', False)
                            or holidays_employee_permits.get('on_leave', False)
                    ):
                        continue

                    # Generate work entries
                    if ranges_to_day:
                        vals_to_save = self.must_hours(work_entry_date, ranges_to_day[0]['start'], employee,
                                                       lactation_employee)
                        list_vals_general.extend(vals_to_save)

            # Bulk create work entries
            if list_vals_general:
                list_final = self.aplicar_convert_to_utc(list_vals_general)
                if list_final and isinstance(list_final, list):
                    work_entry_env.create(list_final)

            # Return download URL
            return {
                'type': 'ir.actions.act_url',
                'url': f'/reporte_asistencias/download_pdf/{record.id}',
                'target': 'new',
            }

    def download_xlsx_report(self):
        # Cache system parameter
        type_of_resource = self.env['ir.config_parameter'].sudo().get_param('hr_payroll.mode_of_attendance')
        model_import = self.env['hr.attendance.import'].sudo()
        work_entry_env = self.env['hr.work.entry'].sudo()
        leave_type_id = self.env.ref('hr_payroll.hr_work_entry_type_leaves').id

        for record in self:
            # Early validation
            if not record.employee_ids:
                continue

            # Precompute date range and UTC conversions
            date_from = datetime.combine(record.date_from, time.min)
            date_to = datetime.combine(record.date_to, time.max)
            date_range = [
                date_from + timedelta(days=x)
                for x in range((record.date_to - record.date_from).days + 1)
            ]
            date_utc_ranges = [
                (
                    self.convert_to_utc(datetime.combine(date, time.min) + timedelta(minutes=1)),
                    self.convert_to_utc(datetime.combine(date, time.max) - timedelta(minutes=1))
                )
                for date in date_range
            ]

            # Bulk unlink existing leave entries
            self.update_and_unlink(
                record.employee_ids.ids,
                date_from,
                date_to,
                leave_type_id
            )

            # Prefetch work entries
            work_entries = work_entry_env.search([
                ('employee_id', 'in', record.employee_ids.ids),
                ('date_start', '>=', date_utc_ranges[0][0]),
                ('date_stop', '<=', date_utc_ranges[-1][1]),
            ])
            work_entries_dict = defaultdict(list)
            for entry in work_entries:
                datetime_entry = self.convertir_a_hora_ecuador(entry.date_start)
                date_str = datetime_entry.date().isoformat()

                work_entries_dict[(entry.employee_id.id, date_str)].append(entry)

            # Prefetch calendar and holiday data
            calendar_dict = self._prefetch_calendar(record.employee_ids.ids, date_range, type_of_resource)
            holidays_dict = self._prefetch_holidays(record.employee_ids.ids, date_utc_ranges)
            holidays_employee_dict = self._prefetch_holidays_employee(record.employee_ids.ids, date_utc_ranges)
            holidays_employee_permits_dict = self._prefetch_holidays_employee_permits(record.employee_ids.ids, date_utc_ranges)
            lactation_employee_dict = self.prefetch_lactation_employee(record.employee_ids.ids, date_utc_ranges)

            list_vals_general = []
            for idx, current_date in enumerate(date_range):
                current_date_start, current_date_stop = date_utc_ranges[idx]
                next_date = current_date + timedelta(days=1)

                for employee in record.employee_ids:
                    work_entry_date = work_entries_dict.get((employee.id, current_date.date().isoformat()), [])

                    calendar_data = calendar_dict.get((employee.id, current_date.isoformat()), None)

                    holidays = holidays_dict.get((employee.id, current_date.strftime('%Y-%m-%d')), None)
                    holidays_by_employee = holidays_employee_dict.get((employee.id, current_date.strftime('%Y-%m-%d')), {})
                    holidays_employee_permits = holidays_employee_permits_dict.get((employee.id, current_date.strftime('%Y-%m-%d')),
                                                                                   {})
                    lactation_employee = lactation_employee_dict.get(
                        (employee.id, current_date.strftime('%Y-%m-%d')),
                        {})



                    # print("++++++++++++++++++++++++++++")
                    # print("valores aca holidays", current_date)
                    # print("valores aca holidays_by_employee", holidays_by_employee)
                    # print("valores aca employee.name", employee.name)
                    # print("valores aca employee.id", employee.id)
                    # print("valores aca get aca", (employee.id, current_date.strftime('%Y-%m-%d')))
                    # print("++++++++++++++++++++++++++++")

                    ranges_to_day = calendar_data['ranges'] if calendar_data else []
                    is_special_turn = calendar_data['is_special_turn'] if calendar_data else False
                    max_hours_for_schedule = calendar_data['max_hours'] if calendar_data else 0
                    is_extraordinary = calendar_data['is_extraordinary'] if calendar_data else False

                    # Handle special turns
                    if is_special_turn and calendar_dict.get((employee.id, next_date.isoformat())):
                        next_calendar = calendar_dict[(employee.id, next_date.isoformat())]
                        ranges_to_day = ranges_to_day + next_calendar['ranges']
                        ranges_to_day = model_import.filtrar_turno_especial(ranges_to_day)

                    # Skip if no ranges or holidays exist
                    has_national_holidays = bool(holidays.get('national', False))
                    has_province_holidays = bool(holidays.get('province', False))

                    if (
                        not ranges_to_day
                        or has_national_holidays
                        or has_province_holidays
                        or holidays_by_employee.get('on_leave', False)
                        or holidays_employee_permits.get('on_leave', False)
                    ):
                        continue

                    # Generate work entries
                    if ranges_to_day:
                        vals_to_save = self.must_hours(work_entry_date, ranges_to_day[0]['start'], employee, lactation_employee)
                        list_vals_general.extend(vals_to_save)

            # Bulk create work entries
            if list_vals_general:
                list_final = self.aplicar_convert_to_utc(list_vals_general)
                if list_final and isinstance(list_final, list):
                    work_entry_env.create(list_final)

            # Return download URL
            return {
                'type': 'ir.actions.act_url',
                'url': f'/reporte_asistencias/download_xlsx/{record.id}',
                'target': 'new',
            }

    @api.model
    def _prefetch_holidays(self, employee_ids, date_utc_ranges):
        holidays_dict = defaultdict(lambda: {'national': False, 'province': False})
        for employee_id in employee_ids:
            for date_start, date_end in date_utc_ranges:
                national, province = self.get_holidays_national(date_start, date_end, employee_id)
                holidays_dict[(employee_id, date_start.date().isoformat())] = {
                    'national': national,
                    'province': province
                }
        return holidays_dict

    @api.model
    def _prefetch_holidays_employee(self, employee_ids, date_utc_ranges):

        holidays_dict = defaultdict(lambda: {'on_leave': False})

        if not employee_ids or not date_utc_ranges:
            return holidays_dict

        # Preparar datos
        date_start_min = min(date_start for date_start, _ in date_utc_ranges)
        date_end_max = max(date_end for _, date_end in date_utc_ranges)

        query = """
                SELECT DISTINCT 
                    he.id as employee_id,
                    rcl.date_from,
                    rcl.date_to
                FROM hr_employee he
                JOIN resource_resource rr ON he.resource_id = rr.id
                JOIN resource_calendar_leaves rcl ON rcl.resource_id = rr.id
                JOIN hr_leave hl ON rcl.holiday_id = hl.id
                JOIN hr_leave_type hlt ON hl.holiday_status_id = hlt.id
                WHERE he.id = ANY(%s)
                  AND rcl.holiday_id IS NOT NULL
                  AND rcl.date_from <= %s
                  AND rcl.date_to >= %s
                  AND hlt.time_type = 'leave'
                  AND hl.state = 'validate'
            """

        self.env.cr.execute(query, [employee_ids, date_end_max, date_start_min])
        holidays_data = self.env.cr.fetchall()

        employee_holidays = defaultdict(list)
        for emp_id, date_from, date_to in holidays_data:
            employee_holidays[emp_id].append((date_from, date_to))

        for employee_id in employee_ids:
            emp_holidays = employee_holidays.get(employee_id, [])

            for date_start, date_end in date_utc_ranges:
                date_start_date = date_start.date()

                has_relevant_holiday = any(
                    h_date_from <= date_end and h_date_to.date() >= date_start_date
                    for h_date_from, h_date_to in emp_holidays
                )

                holidays_dict[(employee_id, date_start_date.isoformat())] = {
                    'on_leave': has_relevant_holiday
                }

        return holidays_dict

    @api.model
    def _prefetch_holidays_employee_permits(self, employee_ids, date_utc_ranges):

        holidays_dict = defaultdict(lambda: {'on_leave': False})

        if not employee_ids or not date_utc_ranges:
            return holidays_dict

        # Preparar datos
        date_start_min = min(date_start for date_start, _ in date_utc_ranges)
        date_end_max = max(date_end for _, date_end in date_utc_ranges)

        query = """
            SELECT DISTINCT 
                he.id as employee_id,
                rcl.date_from,
                rcl.date_to
            FROM hr_employee he
            JOIN resource_resource rr ON he.resource_id = rr.id
            JOIN resource_calendar_leaves rcl ON rcl.resource_id = rr.id
            JOIN hr_leave hl ON rcl.holiday_id = hl.id
            JOIN hr_leave_type hlt ON hl.holiday_status_id = hlt.id
            WHERE he.id = ANY(%s)
              AND rcl.holiday_id IS NOT NULL
              AND rcl.date_from <= %s
              AND rcl.date_to >= %s
              AND hlt.time_type = 'other'
              AND hl.state = 'validate'
        """

        self.env.cr.execute(query, [employee_ids, date_end_max, date_start_min])
        holidays_data = self.env.cr.fetchall()

        # Pre-filtrar holidays de múltiples días usando la misma lógica original
        filtered_holidays = []
        for emp_id, date_from, date_to in holidays_data:
            if (date_to.date() - date_from.date()).days >= 1:
                filtered_holidays.append((emp_id, date_from, date_to))

        # Crear estructura de datos optimizada
        employee_holidays = defaultdict(list)
        for emp_id, date_from, date_to in filtered_holidays:
            employee_holidays[emp_id].append((date_from, date_to))

        for employee_id in employee_ids:
            emp_holidays = employee_holidays.get(employee_id, [])

            for date_start, date_end in date_utc_ranges:
                date_start_date = date_start.date()

                has_relevant_holiday = any(
                    h_date_from <= date_end and h_date_to.date() >= date_start_date
                    for h_date_from, h_date_to in emp_holidays
                )

                holidays_dict[(employee_id, date_start_date.isoformat())] = {
                    'on_leave': has_relevant_holiday
                }

        return holidays_dict


    @api.model
    def _prefetch_holidays_employee_permits_all(self, employee_ids, date_utc_ranges):

        holidays_dict = defaultdict(lambda: {'on_leave': False})

        if not employee_ids or not date_utc_ranges:
            return holidays_dict

        # Preparar datos
        date_start_min = min(date_start for date_start, _ in date_utc_ranges)
        date_end_max = max(date_end for _, date_end in date_utc_ranges)

        query = """
                SELECT DISTINCT 
                    he.id as employee_id,
                    rcl.date_from,
                    rcl.date_to
                FROM hr_employee he
                JOIN resource_resource rr ON he.resource_id = rr.id
                JOIN resource_calendar_leaves rcl ON rcl.resource_id = rr.id
                JOIN hr_leave hl ON rcl.holiday_id = hl.id
                JOIN hr_leave_type hlt ON hl.holiday_status_id = hlt.id
                WHERE he.id = ANY(%s)
                  AND rcl.holiday_id IS NOT NULL
                  AND rcl.date_from <= %s
                  AND rcl.date_to >= %s
                  AND hlt.time_type = 'other'
                  AND hl.state = 'validate'
            """

        self.env.cr.execute(query, [employee_ids, date_end_max, date_start_min])
        holidays_data = self.env.cr.fetchall()

        # Crear estructura de datos optimizada
        employee_holidays = defaultdict(list)
        for emp_id, date_from, date_to in holidays_data:
            employee_holidays[emp_id].append((date_from, date_to))

        for employee_id in employee_ids:
            emp_holidays = employee_holidays.get(employee_id, [])

            for date_start, date_end in date_utc_ranges:
                date_start_date = date_start.date()

                has_relevant_holiday = any(
                    h_date_from <= date_end and h_date_to.date() >= date_start_date
                    for h_date_from, h_date_to in emp_holidays
                )

                holidays_dict[(employee_id, date_start_date.isoformat())] = {
                    'on_leave': has_relevant_holiday
                }

        return holidays_dict

    @api.model
    def prefetch_lactation_employee(self, employee_ids, date_utc_ranges):

        lactation_dict = defaultdict(lambda: {'on_lactation': False})

        if not employee_ids or not date_utc_ranges:
            return lactation_dict

        # Preparar datos - calcular rango mínimo y máximo
        date_start_min = min(date_start for date_start, _ in date_utc_ranges)
        date_end_max = max(date_end for _, date_end in date_utc_ranges)

        # Consulta SQL optimizada
        query = """
                SELECT DISTINCT 
                    he.id as employee_id,
                    lp.start_periode,
                    lp.end_periode
                FROM hr_employee he
                JOIN hr_employee_lactance lp ON he.id = lp.employee_id
                WHERE he.id = ANY(%s)
                  AND he.is_lactation = TRUE
                  AND lp.start_periode <= %s
                  AND lp.end_periode >= %s
                  AND lp.start_periode IS NOT NULL
                  AND lp.end_periode IS NOT NULL
            """

        self.env.cr.execute(query, [employee_ids, date_end_max, date_start_min])
        lactation_data = self.env.cr.fetchall()

        # Agrupar períodos de lactancia por empleado
        employee_lactation = defaultdict(list)
        for emp_id, start_periode, end_periode in lactation_data:
            employee_lactation[emp_id].append((start_periode, end_periode))

        # Evaluar cada combinación empleado-fecha
        for employee_id in employee_ids:
            emp_lactation = employee_lactation.get(employee_id, [])

            for date_start, date_end in date_utc_ranges:
                date_start_date = date_start.date()

                # Verificar si hay solapamiento con algún período de lactancia
                has_relevant_lactation = any(
                    l_start_periode <= date_end.date() and l_end_periode >= date_start_date
                    for l_start_periode, l_end_periode in emp_lactation
                )

                lactation_dict[(employee_id, date_start_date.isoformat())] = {
                    'on_lactation': has_relevant_lactation
                }

        return lactation_dict

    @api.model
    def _prefetch_calendar(self, employee_ids, date_range, type_of_resource):
        calendar_dict = {}
        model_importation = self.env['hr.attendance.import']

        for employee_id in employee_ids:
            for date in date_range:
                schedule_data = self._get_schedule_for_prefetch(
                    model_importation, employee_id, date, type_of_resource
                )

                calendar_dict[(employee_id, date.isoformat())] = schedule_data

        return calendar_dict

    @api.model
    def prefetch_calendar_names(self, employee_ids, start_date, end_date):
        calendar_dict = {}


        domain = [
            ('employee_id', 'in', employee_ids),
            ('start_datetime', '<=', end_date),
            '|',
            ('end_datetime', '>=', start_date),
            ('end_datetime', '=', False)
        ]

        schedule_records = self.env['employee.schedule.history'].sudo().search(domain)

        # Procesar cada empleado
        for employee_id in employee_ids:
            employee_schedules = schedule_records.filtered(
                lambda s: s.employee_id.id == employee_id
            )

            if employee_schedules:
                # Obtener nombres de calendarios únicos
                calendar_names = []
                for schedule in employee_schedules:
                    if schedule.calendar_id and schedule.calendar_id.name:
                        if schedule.calendar_id.name not in calendar_names:
                            calendar_names.append(schedule.calendar_id.name)

                calendar_dict[employee_id] = calendar_names
            else:
                # Buscar calendario por defecto del empleado
                employee = self.env['hr.employee'].browse(employee_id)
                if employee.resource_calendar_id:
                    calendar_dict[employee_id] = [employee.resource_calendar_id.name]
                else:
                    calendar_dict[employee_id] = []

        return calendar_dict


    def _get_schedule_for_prefetch(self, model_importation, employee_id, date, type_of_resource):
        # 1. Obtener horario según la configuración del sistema
        if type_of_resource == 'employee':
            # Si la config es 'employee', buscar en 'history'
            ranges_to_day, max_hours, is_extraordinary, is_special_turn = \
                model_importation.get_range_resource_calendar(
                    employee_id, date, False, "history"
                )

        elif type_of_resource == 'department':
            # Usar lógica de departamento
            ranges_to_day, max_hours, is_special_turn = \
                model_importation.get_range_resource_calendar_for_departament(
                    employee_id, date
                )
            is_extraordinary = False

        else:
            # Comportamiento por defecto: usar 'history'
            ranges_to_day, max_hours, is_extraordinary, is_special_turn = \
                model_importation.get_range_resource_calendar(
                    employee_id, date, False, "history"
                )

        # 2. Manejo de turnos especiales
        if is_special_turn:
            ranges_to_day = self._handle_special_turn_prefetch(
                model_importation, employee_id, date, ranges_to_day, type_of_resource
            )

        return {
            'ranges': ranges_to_day,
            'max_hours': max_hours,
            'is_extraordinary': is_extraordinary,
            'is_special_turn': is_special_turn
        }

    def _handle_special_turn_prefetch(self, model_importation, employee_id, date, ranges_to_day, type_of_resource):

        next_date = date + timedelta(days=1)

        if type_of_resource == 'employee':
            # Si config es 'employee', buscar día siguiente en 'history'
            next_ranges, _, _, _ = model_importation.get_range_resource_calendar(
                employee_id, next_date, False, "history"
            )

        elif type_of_resource == 'department':
            # Usar lógica de departamento para día siguiente
            next_ranges, _, _ = model_importation.get_range_resource_calendar_for_departament(
                employee_id, next_date
            )

        else:
            # Por defecto: usar 'history' para día siguiente
            next_ranges, _, _, _ = model_importation.get_range_resource_calendar(
                employee_id, next_date, False, "history"
            )

        if next_ranges:
            ranges_to_day.extend(next_ranges)

        return model_importation.filtrar_turno_especial(ranges_to_day)


    # def _prefetch_calendar(self, employee_ids, date_range, type_of_resource):
    #     calendar_dict = {}
    #     model_importation = self.env['hr.attendance.import']
    #     for employee_id in employee_ids:
    #         for date in date_range:
    #             next_date = date + timedelta(days=1)
    #             ranges_to_day, max_hours, is_extraordinary, is_special_turn = (
    #                 model_importation.get_range_resource_calendar(
    #                     employee_id, date, False, "history"
    #                 )
    #             )
    #
    #             if not ranges_to_day and type_of_resource == 'employee':
    #                 ranges_to_day, max_hours, is_extraordinary, is_special_turn = (
    #                     model_importation.get_range_resource_calendar(
    #                         employee_id, date, False, "employee"
    #                     )
    #                 )
    #             elif not ranges_to_day and type_of_resource == 'departament':
    #                 ranges_to_day, max_hours, is_special_turn = (
    #                     model_importation.get_range_resource_calendar_for_departament(
    #                         employee_id, date
    #                     )
    #                 )
    #
    #             # Handle special turns
    #             if is_special_turn:
    #                 next_ranges, next_max_hours, next_extraordinary, next_special_turn = (
    #                     model_importation.get_range_resource_calendar(
    #                         employee_id, next_date, False, "history"
    #                     ) if type_of_resource == 'history' else
    #                     model_importation.get_range_resource_calendar(
    #                         employee_id, next_date, False, "employee"
    #                     ) if type_of_resource == 'employee' else
    #                     model_importation.get_range_resource_calendar_for_departament(
    #                         employee_id, next_date
    #                     )
    #                 )
    #                 ranges_to_day.extend(next_ranges)
    #                 ranges_to_day = model_importation.filtrar_turno_especial(ranges_to_day)
    #
    #             calendar_dict[(employee_id, date.isoformat())] = {
    #                 'ranges': ranges_to_day,
    #                 'max_hours': max_hours,
    #                 'is_extraordinary': is_extraordinary,
    #                 'is_special_turn': is_special_turn
    #             }
    #     return calendar_dict

    def _check_attendance_exist(
            self,
            work_entries,
            work_entries_date,
            employee_id,
            date,
            date_start,
            date_end,
            sum_days,
            sum_hours,
            holidays,
            holidays_employee,
            holidays_employee_permits_all,
            calendar
    ):
        text_to_return = []

        # Check for holidays
        national = holidays['national']
        province = holidays['province']

        if holidays_employee.get('on_leave'):
            text_to_return.append(self.text_for_observation('vc'))

        if holidays_employee_permits_all.get('on_leave'):
            text_to_return.append(self.text_for_observation('vp'))

        if len(calendar['ranges']) > 0:
            if not work_entries and not national and not province and not self.work_entry_not_debited(work_entries_date):
                text_to_return.append(self.text_for_observation('fnj'))
            if province:
                text_to_return.append(province.name)
            if national:
                text_to_return.append(national.name)
            if not province and not national:
                sum_days += 1
                sum_hours += self.calcular_horas(calendar)
        else:
            if national and province:
                text_to_return.append(f"{national.name}, {province.name}")
            elif national:
                text_to_return.append(national.name)
            elif province:
                text_to_return.append(province.name)

        return ', '.join(text_to_return) if text_to_return else '', sum_days, sum_hours


    def calcular_horas(self, calendar):

        if not isinstance(calendar, dict) or 'ranges' not in calendar:
            return 0

        total_seconds = 0
        for lapso in calendar['ranges']:
            if not isinstance(lapso, dict) or 'start' not in lapso or 'end' not in lapso:
                continue
            inicio = lapso['start']
            fin = lapso['end']
            # Assume inicio and fin are datetime objects; calculate duration
            if isinstance(inicio, datetime) and isinstance(fin, datetime):
                duration = (fin - inicio).total_seconds()
                total_seconds += duration
        return total_seconds



    def text_for_observation(self, code):

        if code == "fnj":
            return "Falta no justificada"
        if code == "dg":
            return "Asis. generada por no marcación"
        if code == "fr":
            return "Correc. atomática por el sis."
        if code == "vc":
            return "Vacaciones"
        if code == "vp":
            return "Tiene Permiso"



    def work_entry_not_debited(self, work_entries):

        is_debited = False
        if work_entries:
            for entry in work_entries:
                if entry['work_entry_type_id'].id == self.env.ref(
                                 'hr_payroll.hr_work_entry_type_leaves').id:
                    continue
                else:
                    is_debited = True
                    break
        return is_debited



    def get_holidays_national(self, date_start, date_stop, employee_id):

        if isinstance(employee_id, int):
            employee_id = self.env['hr.employee'].sudo().browse(employee_id)

        national = self.env['resource.calendar.leaves'].sudo().search([
            ('type_of_leave_holiday', '=', 'national'),
            ('date_from', '<=', date_stop),
            ('date_to', '>=', date_start),
            ('holiday_id', '=', False),
        ])

        local = self.env['resource.calendar.leaves'].sudo().search([
            ('type_of_leave_holiday', '=', 'local'),
            ('date_from', '<=', date_stop),
            ('date_to', '>=', date_start),
            ('city_id', '=', employee_id.department_id.city_id.id),
            ('holiday_id', '=', False),
        ])

        return national, local

    def calculate_total_hour(self, work_entries, sum):

        if not work_entries:
            return '', sum + 0

        total_hours = 0

        for entry in work_entries:
            if (
                    entry['work_entry_type_id'].id != self.env.ref(
                             'hr_payroll.hr_work_entry_type_leaves').id
                    and
                    entry['work_entry_type_id'].id != self.env.ref(
                              'hr_payroll.hr_work_entry_type_delays').id
            ):
                duration = self.convertir_a_hora_ecuador(entry['date_stop']) - self.convertir_a_hora_ecuador(entry['date_start'])
                hours = duration.total_seconds()
                total_hours += hours
        if total_hours:
            sum += total_hours
            hours = int(total_hours // 3600)
            minutes = int(
                (total_hours % 3600) // 60)

            formatted_time = f"{str(hours).zfill(2)}:{str(minutes).zfill(2)}"


            return formatted_time, sum
        else:
            return '', sum


    def _calculate_total_hours(self, work_entries, total_seconds, work_entry_type_ref):

        if not work_entries:
            return '', total_seconds

        type_id = self.env.ref(work_entry_type_ref).id
        accumulated_seconds = 0

        for entry in work_entries or []:
            if not (entry.work_entry_type_id and entry.date_start and entry.date_stop):
                continue
            if entry['work_entry_type_id'].id != type_id:
                continue

            duration = (self.convertir_a_hora_ecuador(entry['date_stop']) -
                        self.convertir_a_hora_ecuador(entry['date_start']))
            if duration.total_seconds() > 0:
                accumulated_seconds += duration.total_seconds()

        total_seconds += accumulated_seconds
        return self._format_seconds_to_hhmm(accumulated_seconds), total_seconds


    def _check_is_leave(self, work_entry , index):

        if (work_entry and (len(work_entry) - 1)  >= index):
            if work_entry[index].timestamp:
                return self.convertir_a_hora_ecuador(work_entry[index].timestamp).strftime("%H:%M")
        else:
            return ''


    def _format_seconds_to_hhmm(self, seconds):

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours == 0 and minutes == 0:
            return ""
        return f"{hours:02d}:{minutes:02d}"


    def convert_in_hour_format(self, total_hours):

        if total_hours:
            hours = int(total_hours // 3600)
            minutes = int(
                (total_hours % 3600) // 60)

            formatted_time = f"{str(hours).zfill(2)}:{str(minutes).zfill(2)}"
            return formatted_time
        else:
            return '00:00'

    def calculate_total_hours_extra(self, debit_seconds, supplementary_seconds, extraordinary_seconds):
        if debit_seconds <= 0:
            supplementary_hours = self.convert_in_hour_format(supplementary_seconds)
            extraordinary_hours = self.convert_in_hour_format(extraordinary_seconds)
            return supplementary_hours, extraordinary_hours

        # Restamos el débito de los suplementarios primero
        remaining_debit = debit_seconds - supplementary_seconds

        if remaining_debit <= 0:
            remaining_supplementary = supplementary_seconds - debit_seconds
            supplementary_hours = self.convert_in_hour_format(remaining_supplementary)
            extraordinary_hours = self.convert_in_hour_format(extraordinary_seconds)
            return supplementary_hours, extraordinary_hours

        # Si queda débito restante, lo restamos de los extraordinarios
        remaining_extraordinary = extraordinary_seconds - remaining_debit

        if remaining_extraordinary >= 0:
            supplementary_hours = "00:00"
            extraordinary_hours = self.convert_in_hour_format(remaining_extraordinary)
            return supplementary_hours, extraordinary_hours

        # Si aún queda débito sin cubrir, devolvemos 00:00 para ambas
        return "00:00", "00:00"


    def get_references(self, attendances):

        references_set = set()

        for entry in attendances:
            if isinstance(entry.reference, str):
                references_set.add(entry.reference)

        referencias_concatenadas = "\n".join(references_set)

        return referencias_concatenadas


    def get_attendances_with_incosistencies(self, start, end, employee):

        all_attendances = self.env['hr.attendance.general'].sudo().search([
            ('user_id', '=', employee.pin),
            ('timestamp', '>=', start),
            ('timestamp', '<=', end),
        ])

        if all_attendances:
            all_attendances = sorted(all_attendances,
                                     key=lambda att: att.timestamp)

        return all_attendances

    def verificar_suma(self, work_entries):

        total_horas = 0

        for entry in work_entries:
            check_in = entry['date_start']
            check_out = entry['date_stop']

            if isinstance(check_in, str):
                check_in = datetime.strptime(check_in, '%Y-%m-%d %H:%M:%S')
            if isinstance(check_out, str):
                check_out = datetime.strptime(check_out, '%Y-%m-%d %H:%M:%S')

            total_horas += (check_out - check_in).total_seconds() / 3600

        return total_horas

    def aplicar_convert_to_utc(self, work_entries):

        for entry in work_entries:
            entry['date_start'] = self.convert_to_utc(entry['date_start'])
            entry['date_stop'] = self.convert_to_utc(entry['date_stop'])

        return work_entries

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


    def convertir_a_hora_ecuador(self, hora_utc):
        # Zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        utc_tz = pytz.utc
        utc_time = utc_tz.localize(
            hora_utc)
        whitout_time_zone = utc_time.astimezone(ecuador_tz)
        return whitout_time_zone.replace(tzinfo=None)


    def get_name_employee(self, id, type):
        name = self.env['hr.employee'].sudo().search([('id', '=', id)], limit=1)
        return type + name.name if name else "Empleado no Identificado"



    def update_and_unlink(self, ids, date_from, date_to,type):
        start = self.convert_to_utc(date_from)
        end = self.convert_to_utc(date_to)
        works_entrys = self.env['hr.work.entry'].sudo().search([
            ('employee_id', 'in', ids),
            ('date_start', '>=', start),
            ('date_stop', '<=', end),
            ('work_entry_type_id', '=', type),
        ])
        if works_entrys:
            works_entrys.sudo().unlink()

    def must_hours(self, work_entries, start_range, employee, lactation_employee):

        total_hours = 0
        new_entries = []
        if lactation_employee.get('on_lactation', False):
            max_hours_shift = int(self.env['ir.config_parameter'].sudo().get_param(
            'employee_shift_scheduling_app.max_hours_for_lactance')) or 0
        else:
            max_hours_shift = int(self.env['ir.config_parameter'].sudo().get_param(
                'employee_shift_scheduling_app.max_hours_for_shift') or 0)

        leave_type = self.env.ref('hr_payroll.hr_work_entry_type_leaves').id
        delay_type = self.env.ref('hr_payroll.hr_work_entry_type_delays').id
        # leave_permit = self.env.ref('hr_payroll.hr_work_entry_type_permit').id

        for entry in work_entries or []:
            if entry.work_entry_type_id.id not in (leave_type, delay_type):
                time_difference = entry.date_stop - entry.date_start
                hours = round(time_difference.total_seconds() / 3600, 2)
                total_hours += hours

        total_hours = round(total_hours, 2)

        if total_hours < max_hours_shift:
            missing_hours = max_hours_shift - total_hours
            rounded_hours = math.floor(missing_hours * 2) / 2
            if rounded_hours >= 1:
                if work_entries:
                    last_entry = work_entries[-1]
                    new_start_date = last_entry.date_stop
                else:
                    new_start_date = start_range

                # Use rounded_hours instead of missing_hours
                new_stop_date = new_start_date + timedelta(hours=rounded_hours)
                new_start_date = self.convertir_a_hora_ecuador(new_start_date)
                new_stop_date = self.convertir_a_hora_ecuador(new_stop_date)

                # Create new entry
                new_entry = {
                    'name': self.get_name_employee(employee.id, 'Horas Faltantes: '),
                    'date_start': new_start_date,
                    'date_stop': new_stop_date,
                    'work_entry_type_id': self.env.ref('hr_payroll.hr_work_entry_type_leaves').id,
                    'employee_id': employee.id,
                    'company_id': employee.company_id.id,
                    'state': 'draft',
                    'is_credit_time': True
                }

                new_entries.append(new_entry)

        return new_entries

    def get_holidays_all(self, date_start, date_stop, employee_id):
        if isinstance(employee_id, int):
            employee_id = self.env['hr.employee'].sudo().browse(employee_id)

        national = self.env['resource.calendar.leaves'].sudo().search([
            ('type_of_leave_holiday', '=', 'national'),
            ('date_from', '<=', date_start + timedelta(minutes=1)),
            ('date_to', '>=', date_stop -  timedelta(minutes=1)),
        ])
        local = self.env['resource.calendar.leaves'].sudo().search([
            ('type_of_leave_holiday', '=', 'local'),
            ('date_from', '<=', date_start + timedelta(minutes=1)),
            ('date_to', '>=', date_stop - timedelta(minutes=1)),
            ('city_id', '=', employee_id.department_id.city_id.id),
        ])

        if not national and not local:
            return False
        if not local and national:
            return national
        if not national and local:
            return local

        return national, local

    @api.model
    def _get_default_date_from(self):
        # Fecha de inicio del mes actual (primer día del mes)
        today = date.today()
        first_day = today.replace(day=1)
        return first_day

    @api.model
    def _get_default_date_to(self):
        # Fecha de fin del mes actual (último día del mes)
        today = date.today()
        last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        return last_day
