
from odoo import models, fields, api
from datetime import timedelta, datetime, date
import pytz
import calendar

class HrAttendanceGeneral(models.Model):
    _name = 'hr.attendance.general'
    _description = 'Marcaciones'

    user_id = fields.Char('Identificador de usuario', required=True)
    timestamp = fields.Datetime(string='Marcación', required=True)
    reference = fields.Char(string='Referencia')
    device_sn = fields.Char(string='Serie Biométrico')
    origen = fields.Char(string='Origen', default='Manual')
    color = fields.Integer(string='Color', default=0)
    user_id_exist = fields.Boolean(string='Usuario existe', default=True)
    active = fields.Boolean(string='Activo', default=True)

    @api.model_create_multi
    def create(self, vals_list):
        batch_size = 1000
        records = self.env['hr.attendance.general']
        for i in range(0, len(vals_list), batch_size):
            batch_vals = vals_list[i:i + batch_size]
            batch_records = self._create_batch(batch_vals)
            records |= batch_records

        return records

    def _create_batch(self, batch_vals):
        user_id_timestamps = [(vals['user_id'], vals['timestamp']) for vals in batch_vals]
        unique_pairs = set(user_id_timestamps)

        duplicate_pairs = set()
        if unique_pairs:
            query = """
                    SELECT user_id, timestamp
                    FROM hr_attendance_general
                    WHERE (user_id, timestamp) IN %s
                """
            self.env.cr.execute(query, [tuple(unique_pairs)])
            duplicate_pairs = {(row[0], row[1]) for row in self.env.cr.fetchall()}

        user_ids = set(vals['user_id'] for vals in batch_vals)

        existing_users = set()
        if user_ids:
            query = """
                    SELECT pin
                    FROM hr_employee
                    WHERE pin IN %s
                """
            self.env.cr.execute(query, [tuple(user_ids)])
            existing_users = {row[0] for row in self.env.cr.fetchall()}

        non_duplicate_vals = []
        for vals in batch_vals:
            if (vals['user_id'], vals['timestamp']) in duplicate_pairs:
                continue

            vals['user_id_exist'] = vals['user_id'] in existing_users
            vals['color'] = 0 if vals['user_id_exist'] else 1
            non_duplicate_vals.append(vals)

        if not non_duplicate_vals:
            return self.env['hr.attendance.general']

        records = super(HrAttendanceGeneral, self.with_context(no_compute=True)).create(non_duplicate_vals)

        location_updates = []
        for record in records:
            if record.reference:
                location_updates.append({
                    'reference': record.reference,
                    'timestamp': record.timestamp
                })

        if location_updates:
            query = """
                    UPDATE hr_expected_locations
                    SET last_attendance = updates.last_attendance,
                        status = 'ok'
                    FROM (
                        SELECT unnest(%s::text[]) AS reference,
                               unnest(%s::timestamp[]) AS last_attendance
                    ) AS updates
                    WHERE hr_expected_locations.reference = updates.reference
                """
            references = [update['reference'] for update in location_updates]
            timestamps = [update['timestamp'] for update in location_updates]
            self.env.cr.execute(query, [references, timestamps])
        return records



    def write(self, vals):
        cr = self.env.cr

        if 'user_id' in vals:
            cr.execute("""
                SELECT COUNT(*)
                FROM hr_employee
                WHERE pin = %s
            """, (vals.get('user_id'),))
            user_exists = cr.fetchone()[0] > 0

            vals['user_id_exist'] = user_exists
            vals['color'] = 0 if user_exists else 1

        return super(HrAttendanceGeneral, self).write(vals)

    def _compute_last_week_range(self):
        today = datetime.today()
        start_of_last_week = today - timedelta(days=today.weekday() + 7)
        end_of_last_week = today - timedelta(days=today.weekday())
        self.env.context = {
            'last_week_start': start_of_last_week.strftime('%Y-%m-%d'),
            'last_week_end': end_of_last_week.strftime('%Y-%m-%d')
        }

    def action_update_state(self):
        cr = self.env.cr
        query = """
            UPDATE %s
            SET user_id_exist = TRUE,
                color = 0
            WHERE user_id_exist = FALSE
            AND user_id IN (SELECT pin FROM hr_employee WHERE pin IS NOT NULL)
        """ % self._table
        cr.execute(query)
        return True



class HrAttendancesModal(models.TransientModel):
    _name = 'hr.attendance.general.modal'
    _description = 'Marcaciones modal'

    date_start = fields.Datetime(string='Fecha de inicio', required=True,
                          default=lambda self: self._get_default_date_from())
    date_end = fields.Datetime(string='Fecha de fin', required=True,
                          default=lambda self: self._get_default_date_to())

    def process (self, flag=True, continue_attendance=False):

        attendances = self.env['hr.attendance.general'].sudo().search_read([
            ('timestamp', '>=', self.date_start),
            ('timestamp', '<=', self.date_end)
        ], fields=['user_id', 'timestamp', 'reference', 'origen'])

        if not attendances:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No procesado',
                    'message': 'No se encuentran marcaciones en las fechas especificadas.',
                    'type': 'warning',
                    'sticky': True,
                }
            }
        context = {
            'default_date_start': self.date_start,
            'default_date_end': self.date_end,
        }
        if self.verifi_attendance_duplicate(self.date_start, self.date_end) and flag:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'hr.attendance.popup',
                'view_mode': 'form',
                'target': 'new',
                'context': context,
            }
        else:
            result = self.create_attendances_general_modal(
                attendances,
                continue_attendance,
                context
            )

            if result:
                return result

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Recalculo Completado',
                    'message': 'Las asistencias han sido calculadas correctamente.',
                    'type': 'success',
                    'sticky': False,
                }
            }



    def create_attendances_general_modal(self, attendances, continue_attendance, context):

        model_process = self.env['hr.attendance.import']
        self.delete_inconsistencies()
        list_final = model_process.extract_list_final_from_attendances(attendances)
        result = model_process.process_attendance(attendances, list_final, continue_attendance, context)

        if result:
            return result
        return False


    def delete_inconsistencies(self):
        inconsistencies = self.env['hr.attendance.inconsistencies'].sudo().search([
            ('date', '>=', self.date_start),
            ('date', '<=', self.date_end)
        ])
        inconsistencies.sudo().unlink()

    def verifi_attendance_duplicate(self, date_start, date_end):

        query = """
            SELECT EXISTS (
                SELECT 1 FROM hr_work_entry
                WHERE (date_start BETWEEN %s AND %s)
                OR (date_stop BETWEEN %s AND %s)
                OR (date_start <= %s AND date_stop >= %s) 
                LIMIT 1
            )
        """

        self.env.cr.execute(query, (date_start, date_end, date_start, date_end, date_start, date_end))
        exists = self.env.cr.fetchone()[0]

        return exists


    @api.model
    def _get_default_date_from(self):
        tz_ecuador = pytz.timezone('America/Guayaquil')
        now_ecuador = datetime.now(tz_ecuador)
        first_day_ecuador = now_ecuador.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        first_day = first_day_ecuador.astimezone(pytz.UTC).replace(tzinfo=None)
        return first_day

    @api.model
    def _get_default_date_to(self):
        tz_ecuador = pytz.timezone('America/Guayaquil')
        now_ecuador = datetime.now(tz_ecuador)
        _, last_day = calendar.monthrange(now_ecuador.year, now_ecuador.month)
        last_day_ecuador = now_ecuador.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
        last_day = last_day_ecuador.astimezone(pytz.UTC).replace(tzinfo=None)
        return last_day

class HrAttendanceRecalculateWizard(models.TransientModel):
    _name = 'hr.attendance.popup'
    _description = 'Confirmación de Recalculo de Asistencias'

    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)

    def action_confirm(self):
        attendances = self.env['hr.work.entry'].sudo().search([
            ('date_start', '>=', self.date_start),
            ('date_stop', '<=', self.date_end)
        ])

        if attendances.exists():
            attendances.sudo().unlink()
        parent_model = self.env.context.get('active_model')
        parent_record = self.env[parent_model].sudo().browse(self.env.context.get('active_id'))
        result = parent_record.process(False)

        if result:
            return result

        # return {
        #     'type': 'ir.actions.act_window',
        #     'res_model': 'hr.attendance',
        #     'view_mode': 'tree,form',
        #     'target': 'current',
        #     'domain': self.env.context.get('domain', []),
        #     'context': self.env.context,
        # }


