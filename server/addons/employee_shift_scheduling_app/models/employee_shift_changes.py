# -*- coding: utf-8 -*-
import base64
from datetime import datetime, time, timedelta
import pytz

from odoo import api, fields, models, _, exceptions
from odoo.exceptions import ValidationError

class EmployeeShiftChanges(models.Model):
    _name = "employee.shift.changes"
    _description = "Employee Shift Changes"
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nombre', tracking=True)
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', tracking=True, required=True)
    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.user.company_id)
    total_days = fields.Integer('Total de Días', compute='_compute_total_days', store=True, tracking=True)
    sustitute_employee_id = fields.Many2one('hr.employee', string='Empleado sustituido', tracking=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, string='Responsable', tracking=True)
    employee_user = fields.Many2one('hr.employee', compute='_compute_employee_user', string='Empl/User',
                                    tracking=True, store=False)
    state = fields.Selection(
        [('draft', 'Borrador'), ('process', 'Procesar'), ('approv-zonal', 'Aprobar'), ('approve', 'Validar'),
         ('cancel', 'Cancelar')],
        default='draft', tracking=True, string="Estado", compute='_compute_validate', store=True
    )
    type_periode = fields.Selection(
        [('resource', 'Horario Definido'), ('personalize', 'Horario Personalizado')],
        default='resource', required=True, tracking=True, string='Tipo de Horario'
    )
    reason_for_the_exception = fields.Text(string='Motivo de la excepción', tracking=True)
    total_hours = fields.Integer(string='Horas', compute='_compute_total_hours', store=True, tracking=True)
    zonal_responsible = fields.Many2one('res.users', string='Cordinador Zonal Responsable',
                                        compute='_compute_zonal_responsible', store=True)
    note = fields.Text(string='Note', tracking=True)
    resource_calendar_id = fields.Many2one('resource.calendar', check_company=True, string='Horarios',
                                           required=False, tracking=True)
    type_change = fields.Char(default='Cambio de Turno', string='Tipo', tracking=True)
    date_from = fields.Date(string='Desde', required=True, tracking=True)
    date_to = fields.Date(string='Hasta', required=True, tracking=True)
    ranges = fields.One2many('employee.shift.changes.periode', 'shift_change',
                             string='Periodos de Horario')
    email_that_sender = fields.Char(string="Email That Sender", compute='_compute_email_that_sender', store=False)
    coordinador_approve = fields.Many2one('res.users', string='Coordinador Aprobador', tracking=True)
    is_final_validator = fields.Boolean(string='Es Validador Final', compute='_compute_permiss', store=False)
    is_zonal_farm_group = fields.Boolean(string="Es coordinador de farmacia", compute='_compute_permiss',
                                         store=False)
    is_zonal_cord_group = fields.Boolean(string="Es coordinador zonal", compute='_compute_permiss', store=False)
    is_validate = fields.Boolean(string="Validar", default=False, tracking=True)
    departament_for_employee_id = fields.Many2one('hr.department', string='Departamento',
                                                  compute='_compute_departament_for_employee', store=True)
    max_hours_supplementary = fields.Float(string='Cantidad maxima de Horas Sumplementarias',
                                           compute='_compute_max_hours_supplementary', store=True, tracking=True)
    max_hours_extraordinary = fields.Float(string='Cantidad maxima de Horas Extraordinarias',
                                           compute='_compute_max_hours_extraordinary', store=True, tracking=True)
    messages = fields.Char(string='Mensajes', compute='_compute_max_hours_supplementary', store=False)

    @api.depends('create_uid')
    def _compute_permiss(self):
        for record in self:
            record.is_final_validator = record.env.user.has_group(
                'employee_shift_scheduling_app.group_validators_entry_works_admin')
            record.is_zonal_farm_group = record.env.user.has_group(
                'employee_shift_scheduling_app.group_validators_entry_works_zonal_super')
            record.is_zonal_cord_group = record.env.user.has_group(
                'employee_shift_scheduling_app.group_validators_entry_works_zonal_admin')

    @api.depends('employee_id', 'total_days', 'resource_calendar_id', 'type_periode')
    def _compute_max_hours_supplementary(self):
        for record in self:
            total_hours = 0.0
            messages = record.messages or ""  # Asumiendo que messages es un campo de texto

            # Prioridad 1: Verificar si hay solapamiento con lactancia
            if record.employee_id.is_lactation and record.date_from and record.date_to:
                lactation_overlap = False
                for periode in record.employee_id.lactance_ids:
                    if (record.date_from <= periode.end_periode and
                            record.date_to >= periode.start_periode):
                        lactation_overlap = True
                        break  # Detener la verificación de más períodos de lactancia

                if lactation_overlap:
                    total_hours = 0.0
                    messages += "\nEl valor de horas puede variar debido a que el empleado se encuentra en lactancia"
                    # Asignar valores al record actual
                    record.max_hours_supplementary = total_hours
                    record.messages = messages
                    return  # Terminar la función completamente

            # Si no hay lactancia, proceder con los cálculos
            # Caso 2: type_periode == 'resource'
            if record.type_periode == 'resource':
                if record.total_days and record.total_days > 1:
                    total_hours = 0.0
                    messages += "\nLa cantidad es variable debido al tipo de horario"
                elif record.total_days and record.total_days == 1:
                    date = record.date_from
                    total_hours = 0.0
                    resource_calendar = record.resource_calendar_id
                    for range_record in resource_calendar.attendance_ids:
                        if int(range_record.dayofweek) == date.weekday():  # Coincidencia con el día de la semana
                            hours_in = int(range_record.hour_from)
                            minutes_in = int((range_record.hour_from - hours_in) * 60)
                            date_in_contract = datetime.combine(date, time(hours_in, minutes_in))

                            hours_out = int(range_record.hour_to)
                            minutes_out = int((range_record.hour_to - hours_out) * 60)
                            if hours_out == 24:
                                hours_out = 0
                                date_out_contract = datetime.combine(date + timedelta(days=1),
                                                                     time(hours_out, minutes_out))
                            else:
                                date_out_contract = datetime.combine(date,
                                                                     time(hours_out, minutes_out))

                            if range_record.duration_days == 0:
                                continue
                            delta = date_out_contract - date_in_contract
                            total_hours += delta.total_seconds() / 3600.0

            # Caso 3: type_periode == 'personalize'
            elif record.type_periode == 'personalize' and record.ranges:
                total_hours = 0.0
                for range_record in record.ranges:
                    if range_record.date_from and range_record.date_to:
                        # Ensure we're working with datetime objects
                        date_from = fields.Datetime.from_string(range_record.date_from) if isinstance(
                            range_record.date_from, str) else range_record.date_from
                        date_to = fields.Datetime.from_string(range_record.date_to) if isinstance(
                            range_record.date_to, str) else range_record.date_to

                        if date_from and date_to:
                            if isinstance(date_from, datetime) and isinstance(date_to, datetime):
                                delta = date_to - date_from
                                total_hours += delta.total_seconds() / 3600.0
                            else:
                                try:
                                    delta = float(date_to) - float(date_from)
                                    total_hours += delta
                                except (ValueError, TypeError):
                                    continue

            # Asignar resultados

            max_horas = int(self.env['ir.config_parameter'].sudo().get_param(
                'employee_shift_scheduling_app.max_hours_for_shift')) or 0
            total_suplementary = total_hours - max_horas

            record.max_hours_supplementary = max(total_suplementary, 0.0)
            record.messages = messages

    @api.constrains('ranges', 'type_periode')
    def _check_ranges_required(self):
        for record in self:
            if record.type_periode == 'personalize' and not record.ranges:
                raise exceptions.ValidationError(
                    _("Debe especificar al menos un período de horario.")
                )

    @api.depends('employee_id', 'type_periode', 'resource_calendar_id', 'ranges')
    def _compute_max_hours_extraordinary(self):
        pass
        # for record in self:
            # if record.type_periode == 'resource':
            #     if total_days > 1:
            #         star_day = record.attendance_ids[0].hour_from
            #
            #         for range in resource_calendar:
            #             if date.weekday() == int(range.dayofweek):
            #                 hours_in = int(range.hour_from)
            #                 minutes_in = int((range.hour_from - hours_in) * 60)
            #                 hour_time_in = time(hours_in, minutes_in)
            #                 date_in_contract = datetime.combine(date, hour_time_in)
            #
            #                 hours_out = int(range.hour_to)
            #                 minutes_out = int((range.hour_to - hours_out) * 60)
            #                 if hours_out == 24:
            #                     is_especial_shift = True
            #                     hours_out = 0
            #                     date_out_contract = datetime.combine(date + timedelta(days=1),
            #                                                          time(hours_out, minutes_out))
            #                 else:
            #                     date_out_contract = datetime.combine(date, time(hours_out, minutes_out))
            #     else:
            #         record.messages += "\n La cantidad es variable debido al tipo de horario"
            #
            # elif record.type_periode == 'personalize':
            #     record.ranges
            #     or range in resource_calendar:
            #     if date.weekday() == int(range.dayofweek):
            #         hours_in = int(range.hour_from)
            #         minutes_in = int((range.hour_from - hours_in) * 60)
            #         hour_time_in = time(hours_in, minutes_in)
            #         date_in_contract = datetime.combine(date, hour_time_in)
            #
            #         hours_out = int(range.hour_to)
            #         minutes_out = int((range.hour_to - hours_out) * 60)
            #         if hours_out == 24:
            #             is_especial_shift = True
            #             hours_out = 0
            #             date_out_contract = datetime.combine(date + timedelta(days=1),
            #                                                  time(hours_out, minutes_out))
            #         else:
            #             date_out_contract = datetime.combine(date, time(hours_out, minutes_out))


    @api.depends('employee_id')
    def _compute_messages(self):
        for record in self:
            is_overlapping = False
            if record.employee_id.is_lactation:
                for periode in record.employee_id.lactance_ids:
                    if (record.date_from <= periode.end_periode and
                            record.date_to >= periode.start_periode):
                        is_overlapping = True
                        break
            if is_overlapping:
                record.messages += "\n La cantidad puede varia debido a que el empleado se encuentra en lactancia"



    @api.depends('create_uid')
    def _compute_zonal_responsible(self):
        for record in self:
            if record.employee_id:
                if record.employee_id.department_id.parent_id.manager_id.user_id:
                    record.zonal_responsible = record.employee_id.department_id.parent_id.manager_id.user_id


    @api.depends('is_validate')
    def _compute_validate(self):
        for record in self:
            if record.is_validate:
                if record.state != 'approve':
                    record.state = 'approve'
            else:
                if record.state == 'approve':
                    record.state = 'draft'
            # self.get_attendance_today_with_inconsistency(record.date_from, record.date_to,
            #                                              record.employee_id, True)
        # self.bulk_attednaces_ejecuted()

    @api.depends('employee_id')
    def _compute_departament_for_employee(self):
        for record in self:
            if record.employee_id and record.employee_id.department_id:
                record.departament_for_employee_id = record.employee_id.department_id.id
            else:
                record.departament_for_employee_id = None

    @api.depends('ranges', 'type_periode', 'date_from', 'date_to')
    def _compute_total_hours(self):
        for rec in self:
            sum_total_hours = 0
            if rec.type_periode == 'personalize':
                current_day = rec.date_from
                while current_day <= rec.date_to:
                    for range_one in rec.ranges:
                        sum_total_hours += range_one.date_to - range_one.date_from
                        rec.total_hours += sum_total_hours
                    current_day += timedelta(days=1)
                rec.total_hours = sum_total_hours
            elif rec.type_periode == 'resource':
                current_day = rec.date_from
                while current_day <= rec.date_to:
                    for range_one in rec.resource_calendar_id.attendance_ids:
                        if current_day.weekday() == int(range_one.dayofweek):
                            if range_one.duration_days != 0:
                                sum_total_hours += range_one.hour_to - range_one.hour_from
                    current_day += timedelta(days=1)
                rec.total_hours = sum_total_hours

    @api.constrains('employee_id', 'date_from', 'date_to')
    def _check_duplicate_shift_changes(self):
        for record in self:
            overlapping_shifts = self.env['employee.shift.changes'].search([
                ('employee_id', '=', record.employee_id.id),
                ('id', '!=', record.id),
                ('date_from', '<=', record.date_to),
                ('date_to', '>=', record.date_from)
            ])
            if overlapping_shifts:
                raise ValidationError(
                    'Ya existe una asignacion para este empleado en el rango de fechas seleccionado.')

    @api.depends('date_from', 'date_to')
    def _compute_total_days(self):
        for record in self:
            if record.date_from and record.date_to:
                total = record.date_to - record.date_from
                record.total_days = total.days + 1
            else:
                record.total_days = 0

    @api.model
    def get_email_to(self):
        """Determina los destinatarios del correo electrónico según el usuario, su departamento y el encargado."""

        if self.is_zonal_farm_group:
            if not self.employee_user:
                return []

            department = self.employee_user.department_id

            if not department:
                return []  # Si no hay departamento, retorna vacío

            manager = department.parent_id.manager_id.user_id

            if manager and manager.work_email:
                return [manager.work_email]

        elif self.is_zonal_cord_group:
            if self.env.user and self.env.user.work_email:
                return [self.env.user.work_email]
            else:
                return []
        else:
            return []

    @api.model
    def create(self, vals):
        sustitute_employee_id = vals.get('sustitute_employee_id')
        if sustitute_employee_id:
            vals['type_change'] = 'Excepción'
        if vals.get('date_from') and vals.get('date_to'):
            if vals.get('date_from') > vals.get('date_to'):
                raise ValidationError(
                    _("La fecha 'Hasta' no puede ser anterior que la de 'Desde'"))
        res = super(EmployeeShiftChanges, self).create(vals)

        res['name'] = self.env['ir.sequence'].next_by_code(
            'employee.shift.changes') or 'New'
        return res

    def write(self, vals):
        for rec in self:
            sustitute_employee_id = vals.get('sustitute_employee_id',
                                             rec.sustitute_employee_id)
            if sustitute_employee_id:
                vals['type_change'] = 'Excepción'
            else:
                vals['type_change'] = 'Cambio de Turno'

        res = super(EmployeeShiftChanges, self).write(vals)
        return res

    def unlink(self):
        raise ValidationError(
            _("No se puede borrar este registro. Solo puedes archivarlo."))


    def _compute_email_that_sender(self):
        for record in self:
            email_server_id = self.env['ir.config_parameter'].sudo().get_param(
                'employee_shift_scheduling_app.email_that_sender')
            if email_server_id:
                mail_server = self.env['ir.mail_server'].browse(int(email_server_id))
                record.email_that_sender = mail_server.smtp_user  #el correo desde el servidor
            else:
                record.email_that_sender = False

    def _compute_employee_user(self):
        for record in self:
            record.employee_user = self.env['hr.employee'].search(
                [('user_id', '=', self.env.user.id)], limit=1)

    def get_group_emails(self, group_xml_id):
        """
        Obtiene los correos electrónicos de todos los usuarios en un grupo específico.
        """
        group = self.env.ref(group_xml_id)
        if not group:
            return []  # Retorna una lista vacía si no encuentra el grupo
        emails = group.users.mapped('email')
        return [email for email in emails if email]


    def pdf_attachment(self):
        # Generar el informe en PDF utilizando la acción de reporte
        pdf_content, content_type = self.env[
            'ir.actions.report'].sudo()._render_qweb_pdf(
            'employee_shift_scheduling_app.action_shift_change_report',  # accion
            [self.id]  # objeto
        )

        attachment = self.env['ir.attachment'].create({
            'name': 'Excepción Generada- %s.pdf' % self.name,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),  # pasamos a 64
            'res_model': 'employee.shift.changes',
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })

        return attachment


    def get_attendance_today_with_inconsistency(self, date_start, date_end, employee, state):
        start = datetime.combine(date_start, datetime.min.time())
        end = datetime.combine(date_end, datetime.max.time())

        start = self.convert_to_utc(start)
        end = self.convert_to_utc(end)

        attendance_check_in_only = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
            ('is_active', '=', True),
            ('check_in', '>=', start),
            ('check_in', '<=', end),
            ('check_out', '=', None),  # Sin check_out
        ])

        attendance_check_out_only = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
            ('is_active', '=', True),
            ('check_out', '>=', start),
            ('check_out', '<=', end),
            ('check_in', '=', None),  # Sin check_in
        ])

        attendance_todays = self.env['hr.attendance'].search(
            [('check_in', '>=', start),
             ('check_out', '<=', end),
             ('employee_id', '=', employee.id)])

        if attendance_todays:
            for attendance_today in attendance_todays:
                attendance_today.is_have_exception = state

        if attendance_check_in_only:
            for attendance in attendance_check_in_only:
                attendance.is_have_exception = state

        if attendance_check_out_only:
            for attendance in attendance_check_out_only:
                attendance.is_have_exception = state


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



    def action_cancel(self):
        for rec in self:
            rec.action_approve('cancel')

    def action_draft(self):
        for rec in self:
            rec.state = 'draft'

    def action_appr_zonal(self):
        for rec in self:
            rec.coordinador_approve = self.env.user
            rec.state = 'approv-zonal'

    def action_can_zonal(self):
        for rec in self:
            rec.state = 'canc-zonal'

    def action_process(self):
        for rec in self:
            if self.env['ir.config_parameter'].sudo().get_param(
                'employee_shift_scheduling_app.enable_email'):
                template_id = self.env.ref(
                    "employee_shift_scheduling_app.employee_shift_changes_mail_template").id
                template = self.env['mail.template'].browse(template_id)

                template.sudo().send_mail(rec.id, force_send=True, email_values={
                    'attachment_ids': [(4, self.pdf_attachment().id)]
                })
            rec.state = 'process'

    def action_approve(self, state=None):
        for rec in self:
            if not state:
                rec.state = 'approve'
                rec.is_validate = True
            else:
                if state != 'approve':
                    rec.state = state
                    rec.is_validate = False
                else:
                    rec.state = state
                    rec.is_validate = True

    def bulk_attednaces_ejecuted(self):
        employees = self.mapped('employee_id')
        date_ranges = [(rec.date_from, rec.date_to) for rec in self]

        # Recrear asistencias en lote
        self.recreate_attendances_bulk(employees, date_ranges)

    def recreate_attendances_bulk(self, employees, date_ranges):
        """
        Recrude asistencias en bloque para un grupo de empleados y rangos de fechas.
        """
        get_module_for_convert = self.env['autocomplete.attendance.hours']

        employee_ids = employees.ids
        date_from = datetime.combine(min(date[0] for date in date_ranges), time.min)
        date_to = datetime.combine(max(date[1] for date in date_ranges), time.max)
        date_from = get_module_for_convert.convert_to_utc(date_from)
        date_to = get_module_for_convert.convert_to_utc(date_to)

        attendances = self.env['hr.attendance'].search(
            ['&',
             ('employee_id', 'in', employee_ids),
             '|',
             '&', ('check_in', '>=', date_from), ('check_in', '<=', date_to),
             '&', ('check_out', '>=', date_from), ('check_out', '<=', date_to)
             ],
        )

        normalized_attendances = []
        for att in attendances:
            if att['check_in']:
                normalized_attendances.append({
                    "employee_id": att['employee_id'][0].id,
                    "timestamp": att['check_in'],
                })
            if att['check_out']:
                normalized_attendances.append({
                    "employee_id": att['employee_id'][0].id,
                    "timestamp": att['check_out'],
                })
        attendances.unlink()

        self.recreate_attendances_from_list(normalized_attendances, employees)


    def recreate_attendances_from_list(self,attendances=None, employees=None):
        list_attendances, list_exceptiones, ranges_contracts = [], [], False
        get_module_for_schedule = self.env['hr.attendance.import']
        get_module_for_convert = self.env['autocomplete.attendance.hours']
        for attendance in attendances:

            timestamp = get_module_for_convert.convertir_a_hora_ecuador(attendance['timestamp'])

            type_of_resource = self.env['ir.config_parameter'].sudo().get_param(
                'hr_payroll.mode_of_attendance')

            if type_of_resource == 'employee':
                ranges_contracts = get_module_for_schedule.get_range_resource_calendar_for_employee(attendance['employee_id'], timestamp)
            elif type_of_resource == 'departament':
                ranges_contracts = get_module_for_schedule.get_range_resource_calendar_for_departament(attendance['employee_id'], timestamp, timestamp)


            if ranges_contracts:
                for ranges_contract in ranges_contracts:
                    possibility_assistances = get_module_for_schedule.modify_time_ranges(ranges_contract)

                    if possibility_assistances:
                        i = 0

                        for possibility_attendance in possibility_assistances:
                            if (
                                    possibility_attendance['start'] <=
                                    timestamp <=
                                    possibility_attendance['end']
                            ):

                                if i == 0:

                                    list_attendances.append(
                                        {"check_in": attendance['timestamp'],
                                         "user_id": attendance['employee_id'] })
                                else:

                                    list_attendances.append(
                                        {"check_out": attendance['timestamp'],
                                         "user_id": attendance['employee_id'] })
                            else:

                                list_exceptiones.append( {"none": attendance['timestamp'],
                                         "user_id": attendance['employee_id'] })
                            i += 1

            else:

                list_exceptiones.append({"none": attendance['timestamp'],
                                         "user_id": attendance['employee_id'] })


        list_final = []
        get_module_for_schedule.agregar_sin_duplicados(list_attendances, list_final)
        get_module_for_schedule.agregar_sin_duplicados(list_exceptiones, list_final)

        resultado_agrupado_ordenado = get_module_for_schedule.agrupar_y_ordenar_por_user_id(list_final)
        total_vals = self.procesar_entradas(resultado_agrupado_ordenado)
        if total_vals:
            self.env['hr.attendance'].create(total_vals)


    def procesar_entradas(self, resultado_agrupado_ordenado):
        total_vals = []

        for user_id, entries in resultado_agrupado_ordenado.items():
            employee_id = user_id
            pending_check_in = None

            for index, current in enumerate(entries):
                # next_entry = entries[index + 1] if index + 1 < len(entries) else None

                # Asignación dinámica de 'none' según las reglas
                if 'none' in current:
                    previous = entries[index - 1] if index > 0 else None
                    if previous and 'check_in' in previous:
                        # Si el anterior es un check_in, transformar 'none' en check_out
                        current['check_out'] = current.pop('none')
                    else:
                        # De lo contrario, asumir que es un check_in
                        current['check_in'] = current.pop('none')


                if 'check_in' in current:
                    # Guardar el check_in pendiente para un futuro check_out
                    if pending_check_in is not None:
                        # Si ya hay un check_in pendiente, registrar el anterior sin un check_out
                        vals = {
                            'employee_id': employee_id,
                            'check_in': pending_check_in,
                        }
                        total_vals.append(vals)

                        # Guardar el nuevo check_in pendiente
                    pending_check_in = current['check_in']

                elif 'check_out' in current:
                    if pending_check_in:
                        # Emparejar con el último check_in pendiente
                        vals = {
                            'employee_id': employee_id,
                            'check_in': pending_check_in,
                            'check_out': current['check_out'],
                        }
                        total_vals.append(vals)
                        pending_check_in = None  # Limpiar el estado pendiente
                    else:
                        # Si no hay check_in pendiente, agregar solo el check_out
                        vals = {
                            'employee_id': employee_id,
                            'check_out': current['check_out'],
                        }
                        total_vals.append(vals)

            # Si al final queda un check_in sin emparejar, lo agregamos solo
            if pending_check_in:
                vals = {
                    'employee_id': employee_id,
                    'check_in': pending_check_in,
                }
                total_vals.append(vals)

        return total_vals





class EmployeeShiftChangesPeriodes(models.Model):
    _name = "employee.shift.changes.periode"
    _description = "Employee Shift Changes Periodes"
    _rec_name = 'name'

    name = fields.Char(string='Nombre',compute='_compute_name_periode', store=True)
    shift_change = fields.Many2one('employee.shift.changes', string='Excepción')
    date_from = fields.Float(string='Desde', required=True)
    date_to = fields.Float(string='Hasta', required=True)

    @api.depends('date_from', 'date_to')
    def _compute_name_periode(self):
        for record in self:
            if record.date_from and record.date_to:
                record.name = str(self.float_to_time(record.date_from)) + " a " + str(self.float_to_time(record.date_to))
            else:
                if record.date_from and not record.date_to :
                    record.name = str(self.float_to_time(record.date_from)) + " a " + "00:00"
                if record.date_to and not record.date_from:
                    record.name = "00:00" + " a " + str(self.float_to_time(record.date_to))
                if not record.date_from and not record.date_to:
                    record.name = "00:00 a 00:00"

    def float_to_time(self, float_value):
        hours, minutes = divmod(float_value * 60, 60)
        return "%02d:%02d" % (int(hours), int(minutes))

    def create(self, vals_list):
        periodes = super().create(vals_list)
        periodes._check_validity_hours()
        return periodes

    def _check_validity_hours(self):
        for record in self:
            if record.date_from and record.date_from > 23.59 and record.date_from < 0:
                raise ValidationError(_("El valor de Periodos de Horario no es valido, el rango permitido es de '0,00' a '23,59'"))
            if record.date_to and record.date_to > 23.59 and record.date_to < 0:
                raise ValidationError(_("El valor de Periodos de Horario no es valido, el rango permitido es de '0,00' a '23,59'"))
            if record.date_from == record.date_to:
                raise ValidationError(_(
                    "Los valores de Periodos de Horario no pueden ser iguales"))
            if record.date_from > record.date_to:
                raise ValidationError(_(
                    "El valor en Periodos de Horario: 'Desde', no puede ser mayor que el valor 'Hasta'"))









