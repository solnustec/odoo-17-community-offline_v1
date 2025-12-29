from psycopg2 import sql
import logging

from datetime import timedelta
from odoo import fields, models, tools, api

_logger = logging.getLogger(__name__)
class HrWorkEntryReport(models.Model):
    _name = 'hr.work.entry.report'
    _description = 'Work Entries Analysis Report'
    _auto = False
    _order = 'date_start desc'

    time_formatted = fields.Char(
        string='Tiempo',
        compute='_compute_time_formatted',
        store=True,
        help='Tiempo en formato HH:MM:SS.'
    )

    number_of_days = fields.Float('Horas', readonly=True)

    date_start = fields.Datetime('Date Start', readonly=True)
    company_id = fields.Many2one('res.company', 'Company', readonly=True)
    department_id = fields.Many2one('hr.department', 'Department', readonly=True)
    employee_id = fields.Many2one('hr.employee', 'Employee', readonly=True)
    work_entry_type_id = fields.Many2one('hr.work.entry.type', 'Work Entry Type', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validated'),
        ('conflict', 'Conflict'),
        ('cancelled', 'Cancelled')
    ], readonly=True)
    # Some of those might not be enabled (requiring respective work_entry modules) but adding them separately would require
    # a module just for that
    work_entry_source = fields.Selection([
        ('calendar', 'Working Schedule'),
        ('attendance', 'Attendances'),
        ('planning', 'Planning')], readonly=True)
    # / work_schedule.hours_per_day
    def init(self):
        query = """
        SELECT
            we.id,
            we.date_start,
            we.work_entry_type_id,
            we.employee_id,
            we.department_id,
            we.company_id,
            we.state,
            we.duration AS number_of_days,
            work_schedule.work_entry_source as work_entry_source
        FROM (
            SELECT
                id,
                employee_id,
                contract_id,
                date_start,
                date_stop,
                work_entry_type_id,
                department_id,
                company_id,
                state,
                duration
            FROM
                hr_work_entry
            WHERE
                employee_id IS NOT NULL
                AND employee_id IN (SELECT id FROM hr_employee)
                AND active = TRUE
        ) we
        LEFT JOIN (
            SELECT
                contract.id AS contract_id,
                contract.resource_calendar_id,
                calendar.hours_per_day,
                contract.work_entry_source
            FROM
                hr_contract contract
            LEFT JOIN (
                SELECT
                    id,
                    hours_per_day
                FROM
                    resource_calendar
            ) calendar ON calendar.id = contract.resource_calendar_id
        ) work_schedule ON we.contract_id = work_schedule.contract_id
        """

        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            sql.SQL("CREATE or REPLACE VIEW {} as ({})").format(
                sql.Identifier(self._table),
                sql.SQL(query)
            ))

    def _convert_hhmm_to_float(self, hhmm):
        try:
            hours, minutes = map(int, hhmm.split(':'))
            return hours + (minutes / 60.0)
        except (ValueError, AttributeError):
            return 0.0

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        _logger.info("Entrando al método search con args: %s", args)
        print("ver si entra al filtro de busqueda111")
        print("args recibidos: %s" % args)

        time_filter = None
        for arg in args:
            if arg[0] == 'number_of_days' and arg[1] in ['>=', '>']:
                time_filter = arg
                break

        if time_filter:
            _logger.info("Filtro de tiempo detectado: %s", time_filter)
            time_value = time_filter[2]
            time_float = self._convert_hhmm_to_float(time_value)
            _logger.info("Tiempo convertido a float: %s", time_float)

            # Obtener todos los registros que cumplen los demás filtros
            records = super(HrWorkEntryReport, self).search(args, offset=0, limit=None, order=order)

            # Filtrar por suma acumulada
            filtered_records = self.env['hr.work.entry.report']
            cumulative_sum = 0.0
            for record in records:
                cumulative_sum += record.number_of_days
                if cumulative_sum >= time_float:
                    filtered_records |= record

            _logger.info("Registros filtrados: %s", filtered_records.ids)
            if count:
                return len(filtered_records)
            return filtered_records

        return super(HrWorkEntryReport, self).search(args, offset=offset, limit=limit, order=order, count=count)