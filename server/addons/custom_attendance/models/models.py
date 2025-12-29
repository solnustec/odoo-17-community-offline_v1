

from odoo import models, fields, api, exceptions, _
from datetime import datetime, timedelta, time
import pytz

from odoo import api, http, models, tools, SUPERUSER_ID
from odoo.exceptions import ValidationError

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from pytz import timezone, UTC


class CustomAttendance(models.Model):
    _inherit = 'hr.attendance'
    _description = 'custom_attendance.custom_attendance'

    reference = fields.Char()
    check_in = fields.Datetime(string="Entrada",
                               required=False, tracking=True, default=None)
    is_active = fields.Boolean(string="Activo", default=True ,store=True)
    is_generated = fields.Boolean(string="Generado", store=True, default=False)
    out_mode = fields.Selection(
        selection=[
        ('kiosk', 'Quiosco'),
        ('systray', 'Systray'),
        ('manual', 'Manual'),
        ('biome', 'Biométrico'),
        ('sistem', 'Ajustado con el Sistema'),
        ],
        string='Modo',tracking=True,
        store=True, readonly=True)
    in_mode = fields.Selection(
        selection=[
            ('kiosk', 'Quiosco'),
            ('systray', 'Systray'),
            ('manual', 'Manual'),
            ('biome', 'Biométrico'),
            ('sistem', 'Ajustado con el Sistema'),
        ],
        string='Modo', tracking=True,
        store=True, readonly=True)


    def _compute_color(self):
        for attendance in self:
            if attendance.check_out:
                attendance.color = 1 if attendance.worked_hours > 13 else 0
            else:
                attendance.color = 1 if attendance.check_in < (datetime.today() - timedelta(days=1)) else 10
            if not attendance.check_in:
                attendance.color = 1


    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        pass
        """ Verifies the validity of the attendance record compared to the others from the same employee.
            For the same employee we must have :
                * maximum 1 "open" attendance record (without check_out)
                * no overlapping time slices with previous employee records
        """

    @api.constrains('check_in', 'check_out')
    def _check_validity_check_in_check_out(self):
        """ verifies if check_in is earlier than check_out. """
        pass

    @api.model
    def create(self, vals_list):
        # omitidos = 0  # Contador de registros omitidos
        # res = None
        # # Si se reciben múltiples registros en vals_list
        # if isinstance(vals_list, list):
        #     nuevos_registros = self.env['hr.attendance']
        #     for vals in vals_list:
        #         employee_id = vals.get('employee_id')
        #         check_in = vals.get('check_in')
        #         check_out = vals.get('check_out')
        #         existing_record = None
        #
        #         if employee_id and check_in and not check_out:
        #             existing_record = self.sudo().search_count([
        #                 ('employee_id', '=', employee_id),
        #                 ('check_in', '=', check_in),
        #             ])
        #         elif employee_id and check_out and not check_in:
                #     existing_record = self.sudo().search_count([
                #         ('employee_id', '=', employee_id),
                #         ('check_out', '=', check_out)
                #     ])
                # elif employee_id and check_in and check_out:
                #     existing_record = self.sudo().search_count([
                #         ('employee_id', '=', employee_id),
                #         ('check_in', '=', check_in),
                #         ('check_out', '=', check_out)
                #     ])
                #
                #
                # if existing_record:
                #     return {
                #         'type': 'ir.actions.act_window',
                #         'res_model': 'hr.attendance.popup',
                #         'view_mode': 'form',
                #         'target': 'new',
                #         'context': {'default_my_field': 'valor'},
                #     }
                # else:
                #     # Si no existe, crea el registro y lo añade a nuevos_registros
                #     if nuevos_registros:
        #                 nuevos_registros += super(CustomAttendance, self).create(vals)
        #
        #     nuevos_registros._check_errors()
        #     return nuevos_registros
        # else:
            # Si se recibe solo un registro en lugar de una lista
            # existing_record = None
            # employee_id = vals_list.get('employee_id')
            # check_in = vals_list.get('check_in')
            # check_out = vals_list.get('check_out')
            # nuevos_registros = self.env['hr.attendance']
            #
            # if employee_id and check_in and not check_out:
            #     existing_record = self.sudo().search_count([
            #         ('employee_id', '=', employee_id),
            #         ('check_in', '=', check_in),
            #     ])
            # elif employee_id and check_out and not check_in:
            #     existing_record = self.sudo().search_count([
            #         ('employee_id', '=', employee_id),
            #         ('check_out', '=', check_out)
            #     ])
            # elif employee_id and check_in and check_out:
            #     existing_record = self.sudo().search_count([
            #         ('employee_id', '=', employee_id),
            #         ('check_in', '=', check_in),
            #         ('check_out', '=', check_out)
            #     ])


        res = super(CustomAttendance, self).create(vals_list)
        return res

    def _update_overtime(self, employee_attendance_dates=None):
        pass


    def get_attendances_for_date(self, start, end, employee):
        attendance_incomplete = self.env['hr.attendance'].search_count([
            ('employee_id', '=', employee.id),
            '|',
            '&',
            ('check_in', '=', False),
            ('check_out', '<=', end),
            '&',
            ('check_out', '=', False),
            ('check_in', '>=', start)
        ])
        return attendance_incomplete


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


    def unir_asistencias(self):
        active_ids = self.env.context.get('active_ids', [])

        if not active_ids:
            raise ValidationError(_("No hay registros seleccionados."))

        attendances = self.browse(active_ids)

        employee_ids = attendances.mapped('employee_id')
        if len(employee_ids) > 1:
            raise ValidationError(_("Todos los registros deben pertenecer al mismo empleado."))

        attendances_with_both = attendances.filtered(lambda att: att.check_in and att.check_out)
        if attendances_with_both:
            raise ValidationError(_("Los registros seleccionados no deben tener completados tanto Entrada como Salida."
                                    "Seleccione solo registros con solo Entrada o solo Salida."))

        schedules = []
        for att in attendances:
            if att.check_in:
                check_in_utc = fields.Datetime.from_string(att.check_in)
                schedules.append((att.id, check_in_utc))
            if att.check_out:
                check_out_utc = fields.Datetime.from_string(att.check_out)
                schedules.append((att.id, check_out_utc))

        if not schedules:
            raise ValidationError(_("Ninguno de los registros tiene horarios de Entrada o Salida."))

        schedules.sort(key=lambda x: x[1])

        if len(schedules) % 2 != 0:
            raise ValidationError(_("Número impar de veces. No se pueden formar parejas completas."))

        pairs = []
        for i in range(0, len(schedules), 2):
            id1, schedule1 = schedules[i]
            id2, schedule2 = schedules[i + 1]

            if schedule1 <= schedule2:
                check_in_end = schedule1.replace(tzinfo=None)
                check_out_end = schedule2.replace(tzinfo=None)
            else:
                check_in_end = schedule2.replace(tzinfo=None)
                check_out_end = schedule1.replace(tzinfo=None)

            if check_in_end > check_out_end:
                raise ValidationError(_("La hora de entrada ({}) es posterior a la hora de salida ({}).".format(
                    check_in_end, check_out_end)))

            pairs.append((check_in_end, check_out_end))

        for check_in_end, check_out_end in pairs:
            self.create({
                'employee_id': employee_ids[0].id,
                'check_in': check_in_end,
                'check_out': check_out_end,
            })


        attendances.sudo().unlink()

        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'target': 'current',
            'domain': self.env.context.get('domain', []),
            'context': self.env.context,
        }

class HrEmployeeCustomAttendance(models.Model):
    _inherit = "hr.employee"

    def _compute_hours_last_month(self):
        """
        Compute hours in the current month, if we are the 15th of october, will compute hours from 1 oct to 15 oct
        """
        now = fields.Datetime.now()
        now_utc = pytz.utc.localize(now)
        for employee in self:
            tz = pytz.timezone(employee.tz or 'UTC')
            now_tz = now_utc.astimezone(tz)
            start_tz = now_tz.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_naive = start_tz.astimezone(pytz.utc).replace(tzinfo=None)
            end_tz = now_tz
            end_naive = end_tz.astimezone(pytz.utc).replace(tzinfo=None)

            hours = sum(
                att.worked_hours or 0
                for att in employee.attendance_ids.filtered(
                    lambda
                        att: att.check_in and att.check_in >= start_naive and att.check_out and att.check_out <= end_naive
                )
            )

            employee.hours_last_month = round(hours, 2)
            employee.hours_last_month_display = "%g" % employee.hours_last_month


