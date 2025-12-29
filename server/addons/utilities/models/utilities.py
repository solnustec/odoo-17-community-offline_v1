from datetime import datetime, date, timedelta

from odoo import models, fields, api

class EmployeeScheduleHistory(models.Model):
    _name = 'hr.payroll.utilities'
    _description = 'HR Payroll Utilities'

    fiscal_year = fields.Selection(
        selection='_get_years',
        string="Año de Ejercicio Fiscal",
        required=True,
        default=lambda self: str(datetime.now().year)
    )
    date_contable = fields.Date("Fecha de Contabilización", tracking=True, required=True)
    utilities_company = fields.Float("Utilidad Compañia", tracking=True, required=True)
    utilities_contractors = fields.Float("Utilidad Contratantes")
    utility_to_be_distributed = fields.Float("Utilidad a Distribuir a Empleados")
    is_calculated = fields.Boolean("¿Fue Calculado?", default=False)
    total_days_worked = fields.Float("Total Días Laborados")
    total_days_family_burdens = fields.Float("Totales De Cargas Familiares Por Total Días Trabajados")
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.user.company_id,
                                 tracking=True)
    total_benefits_iees = fields.Float(string="Total Prestaciones Solidarias al IEES")
    state = fields.Selection([('draft', 'Borrador'), ('approve', 'Validado'), ('cancel', 'Cancelado')],
                             default='draft',
                             tracking=True, string="Estado", store=True)
    utilities_lines_ids = fields.Many2many(
        'hr.payroll.utilities.lines',
        string='Lineas de Utilidades',
        help='Muestra las lineas de utilidades de cada empleado.'
    )



    def _get_years(self):
        current_year = datetime.now().year
        return [(str(year), str(year)) for year in range(current_year - 50, current_year + 51)]

    def calculate_utilities(self):
        for rec in self:
            rec.is_calculated = True
            if rec.utilities_lines_ids:
                rec.utilities_lines_ids.unlink()

            employees = rec.env['hr.employee'].search([])
            # employees = rec.env['hr.employee'].browse([2360, 2362, 2363, 2364, 2365, 2366, 2367, 2368])
            lines = []

            lines_utilidades_batch = []

            total_days_worked_all = sum(
                sum(rec.days_worked_compute_employee(employee.id, rec.fiscal_year))
                for employee in employees
            )

            rec.total_days_worked = total_days_worked_all

            total_days_worked_for_family_burdens = sum(
                sum(rec.days_worked_compute_employee(employee.id, rec.fiscal_year)) * employee.total_family_burdens
                for employee in employees
                if employee.total_family_burdens > 0
            )

            rec.total_days_family_burdens = total_days_worked_for_family_burdens

            for employee in employees:
                days_per_month = rec.days_worked_compute_employee(employee.id, rec.fiscal_year)
                total_days_worked = sum(days_per_month)

                if total_days_worked == 0:
                    continue



                totales_family_burdens = employee.total_family_burdens
                factorA = totales_family_burdens*total_days_worked
                valor_10 = rec.utilities_company * (10 / 15)
                valor_5 = rec.utilities_company * (5 / 15)
                total_utilities_10 = (total_days_worked*valor_10)/total_days_worked_all
                total_utilities_5 = (factorA*valor_5)/total_days_worked_for_family_burdens if total_days_worked_for_family_burdens else 0
                lines_utilidades_batch.append({
                    'employee_id': employee.id,
                    'family_burdens': totales_family_burdens,
                    'days_compute': total_days_worked,
                    'days_calendar': 360,
                    'calculate_10_porcent': total_utilities_10,
                    'calculate_5_porcent': total_utilities_5,
                    'total_utilities': total_utilities_10+total_utilities_5,
                    'total_days_family_burdens': factorA,
                    'judicial_retention': 0.0,
                    'advance_received': 0,
                    'to_receive': (total_utilities_10+total_utilities_5),
                    'accounting_entry': None,
                    'state': 'draft',
                    'utilities_id': rec.id,
                })

            if lines_utilidades_batch:
                created_lines = rec.env['hr.payroll.utilities.lines'].create(lines_utilidades_batch)

                lines = created_lines.ids

            if lines:
                rec.write({'utilities_lines_ids': [(6, 0, lines)]})

    def validate(self):
        for rec in self:
            if (rec.is_calculated):
                rec.state = 'approve'
            else:
                rec.calculate_utilities()
                rec.state = 'approve'

    def cancelate(self):
        for rec in self:
            rec.state = 'cancel'

    def days_worked_compute_employee(self, employee_id, fiscal_year):
        fiscal_year = int(fiscal_year)
        fiscal_start = date(fiscal_year, 1, 1)
        fiscal_end = date(fiscal_year, 12, 31)

        contracts = self.env['hr.contract'].search_read(
            [('employee_id', '=', employee_id)],
            ['date_start', 'date_end']
        )

        days_worked = [0] * 12

        for contract in contracts:
            contract_start = contract["date_start"]
            contract_end = contract["date_end"] if contract["date_end"] else fiscal_end

            if isinstance(contract_start, str):
                contract_start = date.fromisoformat(contract_start)
            if isinstance(contract_end, str):
                contract_end = date.fromisoformat(contract_end)

            for month in range(1, 13):
                month_start = date(fiscal_year, month, 1)
                month_end = date(fiscal_year, month + 1, 1) - timedelta(days=1) if month < 12 else fiscal_end

                if contract_start <= month_start and contract_end >= month_end:
                    days_worked[month - 1] = 30
                elif contract_start <= month_end and contract_end >= month_start:
                    work_start = max(contract_start, month_start)
                    work_end = min(contract_end, month_end)
                    # Calculate the proportion of the month worked based on a 30-day month
                    actual_days_worked = (work_end - work_start).days + 1
                    # Proportion of the 30-day month worked
                    proportion_worked = actual_days_worked / ((month_end - month_start).days + 1)
                    days_worked[month - 1] = round(proportion_worked * 30, 0)

        return days_worked

