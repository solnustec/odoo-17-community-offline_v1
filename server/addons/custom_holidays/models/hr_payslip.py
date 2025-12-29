from types import SimpleNamespace

from odoo import api, Command, fields, models, _

from datetime import datetime, date, time, timedelta
from typing import Tuple, Union, Optional
from calendar import monthrange
import calendar
from datetime import datetime, date as date_module


from odoo.http import request, route, Controller, content_disposition
from dateutil.relativedelta import relativedelta


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_base_local_dict(self):

        res = super()._get_base_local_dict()
        new_dict = {
            'get_days_for_decimo_c': self.get_days_for_decimo_c,
            'get_days_for_decimo': self.get_days_for_decimo,
            'get_values_total': self.get_values_total,
            'get_diccionary_for_decimos': self.get_diccionary_for_decimos,
            'get_current_payslip': self.get_current_payslip,
            'get_values_income': self.get_values_income,
            'get_values_vacations': self.get_values_vacations,
            'get_allocation_for_employee': self.get_allocation_for_employee,
            'get_values_for_holidays': self.get_values_for_holidays,
            'calculate_days_worked': self.calculate_days_worked,
            '_has_minimum_one_year_service': self._has_minimum_one_year_service,
            '_calculate_years_of_service': self._calculate_years_of_service,
            'get_values_for_desahucio': self.get_values_for_desahucio,
        }

        res.update(new_dict)

        return res

    def get_values_for_holidays(self, employee_id, date_start, date_end):
        vacation_start, vacation_end = self._get_current_vacation_period(date_start, date_end)

        holidays = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', employee_id),
            ('date_from', '<=', vacation_end),
            ('date_to', '>=', vacation_start),
            ('holiday_status_id.time_type', '=', 'leave'),
            ('state', '=', 'validate'),
        ])

        total_days = sum(holidays.mapped('number_of_days'))

        return total_days

    # def _get_current_vacation_period(self, contract_start: date, contract_end: date) -> Tuple[date, date]:
    #
    #     # Encontrar en qué año de servicio está el empleado
    #     years_completed = self._calculate_completed_years(contract_start, contract_end)
    #
    #     # El período de vacaciones actual comienza en el último aniversario
    #     current_period_start_year = contract_start.year + years_completed
    #
    #     try:
    #         vacation_period_start = date(current_period_start_year, contract_start.month, contract_start.day)
    #     except ValueError:  # Para 29 de febrero
    #         vacation_period_start = self._safe_date_creation(current_period_start_year, contract_start.month,
    #                                                          contract_start.day)
    #
    #     # El período termina en la fecha de fin del contrato o antes del próximo aniversario
    #     try:
    #         next_anniversary = date(current_period_start_year + 1, contract_start.month, contract_start.day)
    #     except ValueError:
    #         next_anniversary = self._safe_date_creation(current_period_start_year + 1, contract_start.month,
    #                                                     contract_start.day)
    #
    #     # El fin del período es el menor entre la fecha de fin del contrato y un día antes del siguiente aniversario
    #     vacation_period_end = min(contract_end, next_anniversary - timedelta(days=1))
    #
    #     return vacation_period_start, vacation_period_end

    # def _has_minimum_one_year_service(self, start_date: date, end_date: date) -> bool:
    #
    #     try:
    #         # Calcular el primer aniversario
    #         first_anniversary = date(start_date.year + 1, start_date.month, start_date.day)
    #     except ValueError:  # Caso 29 de febrero
    #         first_anniversary = self._safe_date_creation(start_date.year + 1, start_date.month, start_date.day)
    #
    #     return end_date >= first_anniversary


    def get_values_for_desahucio(self, start_date, end_date, employee_id):

        neto_amount = 0

        if not self._has_minimum_one_year_service(start_date, end_date):
            return neto_amount

        last_payslip = self._get_last_payslip(employee_id, end_date)
        if last_payslip:
            for line in last_payslip.line_ids:
                if line.code == 'TOTINGM':
                    neto_amount = round(line.amount, 2)

        return neto_amount

    def _get_last_payslip(self, employee_id, end_date):

        previous_month_date = end_date - relativedelta(months=1)

        first_day = previous_month_date.replace(day=1)
        year = previous_month_date.year
        month = previous_month_date.month
        last_day = calendar.monthrange(year, month)[1]
        last_day_of_month = previous_month_date.replace(day=last_day)

        # Buscar el payslip del mes anterior
        domain = [
            ('employee_id', '=', employee_id),
            ('date_from', '>=', first_day),
            ('date_to', '<=', last_day_of_month),
            ('state', 'in', ['done', 'paid']),
            ('struct_id.name', '=', 'Rol de Pagos'),
        ]

        payslip = self.env['hr.payslip'].sudo().search(domain, limit=1)

        return payslip if payslip else False

    def get_current_payslip(self, employee_id, end_date):
        # Usar la fecha actual (mes actual) en lugar del mes anterior
        current_month_date = end_date  # Ya no restamos el mes
        first_day = current_month_date.replace(day=1)
        year = current_month_date.year
        month = current_month_date.month
        last_day = calendar.monthrange(year, month)[1]
        last_day_of_month = current_month_date.replace(day=last_day)

        # Buscar el payslip del mes actual
        domain = [
            ('employee_id', '=', employee_id),
            ('date_from', '>=', first_day),
            ('date_to', '<=', last_day_of_month),
            ('state', 'in', ['done', 'paid']),
            ('struct_id.name', '=', 'Rol de Pagos'),
        ]

        payslip = self.env['hr.payslip'].sudo().search(domain, limit=1)

        return payslip if payslip else False

    def _calculate_years_of_service(self, start_date, end_date):
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        diff = relativedelta(end_date, start_date)
        return diff.years

    #####vacaciones calculo


    def calculate_days_worked(self, date_start_contract, date_end_contract):

        date_start, date_end = self._get_current_vacation_period(date_start_contract, date_end_contract)


        if isinstance(date_start, str):
            contract_start = date.fromisoformat(date_start)
        else:
            contract_start = date_start

        if isinstance(date_end, str):
            contract_end = date.fromisoformat(date_end)
        else:
            contract_end = date_end

        days_by_month = {}

        # Obtener el rango de años y meses a procesar
        start_year = contract_start.year
        start_month = contract_start.month
        end_year = contract_end.year
        end_month = contract_end.month

        # Iterar por todos los meses en el rango del contrato
        current_year = start_year
        current_month = start_month

        while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
            # Calcular inicio y fin del mes actual
            month_start = date(current_year, current_month, 1)

            # Calcular el último día del mes
            if current_month == 12:
                next_month_start = date(current_year + 1, 1, 1)
            else:
                next_month_start = date(current_year, current_month + 1, 1)
            month_end = next_month_start - timedelta(days=1)

            # Verificar si el contrato abarca este mes
            if contract_start <= month_end and contract_end >= month_start:
                if contract_start <= month_start and contract_end >= month_end:
                    # Mes completo trabajado - usar días reales del mes
                    days_worked = (month_end - month_start).days + 1
                else:
                    # Mes parcialmente trabajado
                    work_start = max(contract_start, month_start)
                    work_end = min(contract_end, month_end)

                    # Calcular días reales trabajados
                    days_worked = (work_end - work_start).days + 1

                # Agregar al diccionario temporal con formato YYYY-MM-01
                month_key = f"{current_year}-{current_month:02d}-01"
                days_by_month[month_key] = int(days_worked)

            # Avanzar al siguiente mes
            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1

        # Calcular la suma total de días
        total_days = sum(days_by_month.values())

        return total_days


    def get_allocation_for_employee(self, employee_id):
        number_of_days = 0
        holidays = self.env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', employee_id),
            ('holiday_status_id.time_type', '=', 'leave'),
            ('state', '=', 'validate'),
        ], limit=1)

        if holidays:
            number_of_days = holidays[0].number_of_days

            return number_of_days

        return 9999


    def _calculate_completed_years(self, start_date: date, current_date: date) -> int:
        """
        Calcula los años completos de servicio del empleado.

        Args:
            start_date: Fecha de inicio del contrato
            current_date: Fecha actual o fin del contrato

        Returns:
            Número entero de años de servicio completados
        """
        years = current_date.year - start_date.year

        # Verificar si ya pasó el aniversario este año
        try:
            anniversary_this_year = date(current_date.year, start_date.month, start_date.day)
        except ValueError:  # Para 29 de febrero
            anniversary_this_year = self._safe_date_creation(current_date.year, start_date.month, start_date.day)

        if current_date < anniversary_this_year:
            years -= 1

        return max(0, years)



    ##########3
    MONTHS_ES = {
        1: 'ene', 2: 'feb', 3: 'mar', 4: 'abr', 5: 'may', 6: 'jun',
        7: 'jul', 8: 'ago', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dic'
    }

    def _validate_inputs(self, date, employee_id):
        """Valida los parámetros de entrada."""
        if isinstance(date, str):
            try:
                date = datetime.strptime(date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError("Formato de fecha inválido. Use YYYY-MM-DD.")
        elif isinstance(date, datetime):
            date = date.date()
        elif not isinstance(date, date_module):
            raise ValueError("El parámetro de fecha debe ser válido.")

        if employee_id:
            employee = request.env['hr.employee'].sudo().browse(employee_id)
            if not employee.exists():
                raise ValueError(f"Empleado con ID {employee_id} no existe.")
        return date

    def _get_employee_start_date(self, employee_id):
        """Obtiene la fecha de ingreso del empleado."""
        if not employee_id:
            return None

        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if employee and employee.contract_id.date_start:
            ingreso = employee.contract_id.date_start
            if isinstance(ingreso, str):
                ingreso = datetime.strptime(ingreso, '%Y-%m-%d').date()
            return ingreso
        return None

    def get_vacation_period(self, date_start: date, date_end: date, employee_id: Optional[int]) -> Tuple[
        Union[date, bool], Union[date, bool]]:
        """
        Calcula el período de vacaciones actual basado en las fechas del contrato laboral.

        Args:
            date_start: Fecha de inicio del contrato del empleado
            date_end: Fecha de fin del contrato del empleado (o fecha actual)
            employee_id: ID del empleado

        Returns:
            Tuple con (inicio_periodo_vacaciones, fin_periodo_vacaciones)
            Retorna (False, False) si el empleado tiene menos de un año de antigüedad
        """
        if not employee_id:
            return False, False

        # Verificar si el empleado tiene al menos un año de antigüedad
        if not self._has_minimum_one_year_service(date_start, date_end):
            return False, False

        # Calcular el período de vacaciones actual
        vacation_start, vacation_end = self._get_current_vacation_period(date_start, date_end)

        return vacation_start, vacation_end

    def _has_minimum_one_year_service(self, start_date: date, end_date: date) -> bool:
        """
        Verifica si el empleado tiene al menos un año de servicio.

        Args:
            start_date: Fecha de inicio del contrato
            end_date: Fecha de fin del contrato o fecha actual

        Returns:
            True si tiene al menos un año de antigüedad, False en caso contrario
        """
        try:
            # Calcular el primer aniversario
            first_anniversary = date(start_date.year + 1, start_date.month, start_date.day)
        except ValueError:  # Caso 29 de febrero
            first_anniversary = self._safe_date_creation(start_date.year + 1, start_date.month, start_date.day)

        return end_date >= first_anniversary

    def _get_current_vacation_period(self, contract_start: date, contract_end: date) -> Tuple[date, date]:
        """
        Calcula el período de vacaciones actual en el que se encuentra el empleado.

        Args:
            contract_start: Fecha de inicio del contrato
            contract_end: Fecha de fin del contrato o fecha actual

        Returns:
            Tuple con (inicio_periodo_actual, fin_periodo_actual)
        """
        # Encontrar en qué año de servicio está el empleado
        years_completed = self._calculate_completed_years(contract_start, contract_end)

        # El período de vacaciones actual comienza en el último aniversario
        current_period_start_year = contract_start.year + years_completed

        try:
            vacation_period_start = date(current_period_start_year, contract_start.month, contract_start.day)
        except ValueError:  # Para 29 de febrero
            vacation_period_start = self._safe_date_creation(current_period_start_year, contract_start.month,
                                                             contract_start.day)

        # El período termina en la fecha de fin del contrato o antes del próximo aniversario
        try:
            next_anniversary = date(current_period_start_year + 1, contract_start.month, contract_start.day)
        except ValueError:
            next_anniversary = self._safe_date_creation(current_period_start_year + 1, contract_start.month,
                                                        contract_start.day)

        # El fin del período es el menor entre la fecha de fin del contrato y un día antes del siguiente aniversario
        vacation_period_end = min(contract_end, next_anniversary - timedelta(days=1))

        return vacation_period_start, vacation_period_end

    # def _calculate_completed_years(self, start_date: date, current_date: date) -> int:
    #     """
    #     Calcula los años completos de servicio del empleado.
    #
    #     Args:
    #         start_date: Fecha de inicio del contrato
    #         current_date: Fecha actual o fin del contrato
    #
    #     Returns:
    #         Número entero de años de servicio completados
    #     """
    #     years = current_date.year - start_date.year
    #
    #     # Verificar si ya pasó el aniversario este año
    #     try:
    #         anniversary_this_year = date(current_date.year, start_date.month, start_date.day)
    #     except ValueError:  # Para 29 de febrero
    #         anniversary_this_year = self._safe_date_creation(current_date.year, start_date.month, start_date.day)
    #
    #     if current_date < anniversary_this_year:
    #         years -= 1
    #
    #     return max(0, years)

    def _safe_date_creation(self, year: int, month: int, day: int) -> date:
        """
        Crea una fecha de forma segura, manejando casos como 29 de febrero.

        Args:
            year: Año
            month: Mes
            day: Día

        Returns:
            Objeto date válido
        """
        try:
            return date(year, month, day)
        except ValueError:
            if month == 2 and day == 29:
                # Si es 29 de febrero y el año no es bisiesto, usar 28 de febrero
                return date(year, month, 28)
            else:
                raise ValueError(f"No se pudo crear fecha válida: {year}-{month}-{day}")

    # Ejemplos de funcionamiento:

    def _get_decimo_tercero_period(self, calculation_date, employee_id):
        """
        Calcula el período válido para décimo tercero sueldo.
        Período legal: 1 de diciembre del año anterior al 30 de noviembre del año actual.
        Pero limitado por la fecha de ingreso del empleado.
        """
        year = calculation_date.year

        # Determinar el período correcto basado en la fecha de cálculo
        if calculation_date.month >= 12:  # Diciembre o después
            # Período actual: dic año actual a nov año siguiente
            legal_start = date_module(year, 12, 1)
            legal_end = date_module(year + 1, 11, 30)
        else:  # Enero a noviembre
            # Período actual: dic año anterior a nov año actual
            legal_start = date_module(year - 1, 12, 1)
            legal_end = date_module(year, 11, 30)

        # Ajustar por fecha de ingreso del empleado
        employee_start = self._get_employee_start_date(employee_id)
        if employee_start:
            # El período efectivo empieza en la fecha de ingreso si es posterior al inicio legal
            effective_start = max(legal_start, employee_start)
            # El período efectivo termina en el último día del mes de cálculo o fin legal
            calculation_month_end = date_module(calculation_date.year, calculation_date.month,
                                                calendar.monthrange(calculation_date.year, calculation_date.month)[1])
            effective_end = min(legal_end, calculation_month_end)
        else:
            effective_start = legal_start
            calculation_month_end = date_module(calculation_date.year, calculation_date.month,
                                                calendar.monthrange(calculation_date.year, calculation_date.month)[1])
            effective_end = min(legal_end, calculation_month_end)

        return effective_start, effective_end

    def _get_decimo_cuarto_period(self, calculation_date, employee_id):
        """
        Calcula el período válido para décimo cuarto sueldo.
        Período legal: 1 de agosto al 31 de julio del año siguiente.
        Pero limitado por la fecha de ingreso del empleado.
        """
        year = calculation_date.year

        # Determinar el período correcto basado en la fecha de cálculo
        if calculation_date.month >= 8:  # Agosto o después
            # Período actual: ago año actual a jul año siguiente
            legal_start = date_module(year, 8, 1)
            legal_end = date_module(year + 1, 7, 31)
        else:  # Enero a julio
            # Período actual: ago año anterior a jul año actual
            legal_start = date_module(year - 1, 8, 1)
            legal_end = date_module(year, 7, 31)

        # Ajustar por fecha de ingreso del empleado
        employee_start = self._get_employee_start_date(employee_id)
        if employee_start:
            # El período efectivo empieza en la fecha de ingreso si es posterior al inicio legal
            effective_start = max(legal_start, employee_start)
            # El período efectivo termina en el último día del mes de cálculo o fin legal
            calculation_month_end = date_module(calculation_date.year, calculation_date.month,
                                                calendar.monthrange(calculation_date.year, calculation_date.month)[1])
            effective_end = min(legal_end, calculation_month_end)
        else:
            effective_start = legal_start
            calculation_month_end = date_module(calculation_date.year, calculation_date.month,
                                                calendar.monthrange(calculation_date.year, calculation_date.month)[1])
            effective_end = min(legal_end, calculation_month_end)

        return effective_start, effective_end

    def _get_earliest_date(self, date_start: date, date_end: date, employee_id: Optional[int]) -> Union[
        date, bool]:

        if not employee_id:
            return False

        # Obtener todas las fechas de inicio
        vacation_start, _ = self.get_vacation_period(date_start, date_end, employee_id)
        dt_start, _ = self._get_decimo_tercero_period(date_end, employee_id)
        dc_start, _ = self._get_decimo_cuarto_period(date_end, employee_id)

        # Filtrar fechas válidas usando comprensión de lista
        valid_dates = [
            start_date for start_date in [vacation_start, dt_start, dc_start]
            if start_date is not False
        ]

        return min(valid_dates) if valid_dates else False

    def _is_month_in_period(self, month_date: date, period_start: Union[date, bool],
                            period_end: Union[date, bool]) -> bool:

        if period_start is False or period_end is False:
            return False

        year = month_date.year
        month = month_date.month

        month_start = date(year, month, 1)

        # Último día del mes
        days_in_month = monthrange(year, month)[1]
        month_end = date(year, month, days_in_month)

        return period_start <= month_end and period_end >= month_start

    def _build_payslip_domain(self, date_from, date_to, employee_id):
        domain = [
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
            ('state', 'in', ['done', 'paid']),
            ('struct_id.name', '=', 'Rol de Pagos'),
        ]
        if employee_id:
            domain.append(('employee_id', '=', employee_id))
        return domain

    def get_holidays_liquidations(self, date_start=False, date_end=False, employee_id=False):

        """
        Genera un reporte de nóminas con neto, neto/24 y décimos para el período de vacaciones.
        Considera correctamente los períodos de décimos basándose en la fecha de ingreso del empleado.

        :param date: Fecha límite (str o date, por defecto fecha actual).
        :param employee_id: ID del empleado (opcional).
        :return: Lista de diccionarios con datos de nóminas por mes.
        """

        date = self._validate_inputs(date_end, employee_id)

        vacation_start, vacation_end = self.get_vacation_period(date_start, date_end, employee_id)
        dt_period_start, dt_period_end = self._get_decimo_tercero_period(date_end, employee_id)
        dc_period_start, dc_period_end = self._get_decimo_cuarto_period(date_end, employee_id)

        date_from = self._get_earliest_date(date_start, date_end, employee_id)
        date_to = date

        # Construir dominio y buscar nóminas
        domain = self._build_payslip_domain(date_from, date_to, employee_id)
        payslips = request.env['hr.payslip'].sudo().search(domain)

        # Generar meses en el rango
        all_months = []
        totals = {}
        current_date = date_from.replace(day=1)
        if vacation_start and vacation_end:
            days_holidays = self.calculate_days_worked_custom(vacation_start, vacation_end)
        else:
            days_holidays = 0

        while current_date <= date_to:
            all_months.append((current_date.year, current_date.month))
            current_date += relativedelta(months=1)

        # Obtener empleados
        if employee_id:
            employee_ids = [employee_id]
        else:
            employee_ids = list(set([p.employee_id.id for p in payslips]))
            if not employee_ids and employee_id:
                employee_ids = [employee_id]

        result = []
        payslips_by_month = {}

        # Agrupar nóminas por mes y empleado
        for payslip in payslips:
            emp_id = payslip.employee_id.id
            payslip_date = payslip.date_from
            month_key = f"{emp_id}-{payslip_date.year}-{payslip_date.month}"
            if month_key not in payslips_by_month or payslip.date_from > payslips_by_month[month_key].date_from:
                payslips_by_month[month_key] = payslip

        # Generar reporte
        for emp_id in employee_ids:

            totals = {
                "neto": 0.0,
                "holidays": 0.0,
                "dt": 0.0,
                "dc": 0.0,
                "days": 0
            }

            for year, month in all_months:
                month_str = self.MONTHS_ES[month]
                year_str = str(year)[-2:]
                mes_formato = f"{month_str}-{year_str}"
                month_key = f"{emp_id}-{year}-{month}"

                # Crear fecha del primer día del mes para comparaciones
                month_date = date_module(year, month, 1)

                # Determinar si el mes está en los períodos (usando los períodos ajustados)
                is_vacation_period = self._is_month_in_period(month_date, vacation_start, vacation_end)
                is_dec_tercero_period = self._is_month_in_period(month_date, dt_period_start, dt_period_end)
                is_dec_cuarto_period = self._is_month_in_period(month_date, dc_period_start, dc_period_end)

                payslip_dict = {
                    "month": mes_formato,
                    "neto": "N/A",
                    "days": "" if not is_vacation_period or not is_dec_tercero_period or not is_dec_cuarto_period else "N/A",
                    "holidays": "" if not is_vacation_period else "N/A",
                    "dt": "" if not is_dec_tercero_period else "N/A",
                    "dc": "" if not is_dec_cuarto_period else "N/A",
                    "has_payslip": False,
                    "totals": {
                        "neto": 0.0,
                        "holidays": 0.0,
                        "dt": 0.0,
                        "dc": 0.0,
                        "days": 0
                    },
                    "period_info": {
                        "vacation_period": is_vacation_period,
                        "dt_period": is_dec_tercero_period,
                        "dc_period": is_dec_cuarto_period,
                        "month_date": f"{year}-{month:02d}-01"
                    }
                }

                if month_key in payslips_by_month:
                    payslip = payslips_by_month[month_key]
                    payslip_dict["has_payslip"] = True

                    for line in payslip.line_ids:
                        if line.code == 'TOTINGM':
                            neto_amount = round(line.amount, 2)
                            payslip_dict["neto"] = neto_amount
                            totals["neto"] += neto_amount

                            if is_vacation_period:
                                days = days_holidays[str(month_date)]
                                holidays_amount = round(((line.amount * int(days)) / 30) / 24, 2) if line.amount else 0
                                payslip_dict["holidays"] = holidays_amount
                                totals["holidays"] += holidays_amount

                        elif line.code == 'DECTER' and is_dec_tercero_period:
                            dt_amount = round(line.amount, 2)
                            payslip_dict["dt"] = dt_amount
                            totals["dt"] += dt_amount

                        elif line.code == 'DECCUAR' and is_dec_cuarto_period:
                            dc_amount = round(line.amount, 2)
                            payslip_dict["dc"] = dc_amount
                            totals["dc"] += dc_amount

                        if line.code == 'DYSMES':
                            days_amount = int(line.amount)
                            payslip_dict["days"] = days_amount
                            totals["days"] += days_amount

                result.append(payslip_dict)

        return result, totals

    def calculate_days_worked_custom(self, date_start, date_end):
        """
        Calcula los días trabajados por mes en el período específico del contrato.

        Args:
            date_start (str or date): Fecha de inicio del contrato
            date_end (str or date): Fecha de fin del contrato

        Returns:
            dict: Diccionario con formato {'2024-01-01': dias, '2024-02-01': dias, ...}
        """
        # Convertir strings a objetos date si es necesario

        if isinstance(date_start, str):
            contract_start = date.fromisoformat(date_start)
        else:
            contract_start = date_start

        if isinstance(date_end, str):
            contract_end = date.fromisoformat(date_end)
        else:
            contract_end = date_end

        result = {}

        start_year = contract_start.year
        start_month = contract_start.month
        end_year = contract_end.year
        end_month = contract_end.month

        # Iterar por todos los meses en el rango del contrato
        current_year = start_year
        current_month = start_month

        while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
            # Calcular inicio y fin del mes actual
            month_start = date(current_year, current_month, 1)

            if current_month == 12:
                next_month_start = date(current_year + 1, 1, 1)
            else:
                next_month_start = date(current_year, current_month + 1, 1)
            month_end = next_month_start - timedelta(days=1)

            # Verificar si el contrato abarca este mes
            if contract_start <= month_end and contract_end >= month_start:
                if contract_start <= month_start and contract_end >= month_end:
                    # Mes completo trabajado - usar días reales del mes
                    days_worked = (month_end - month_start).days + 1
                else:

                    work_start = max(contract_start, month_start)
                    work_end = min(contract_end, month_end)

                    days_worked = (work_end - work_start).days + 1

                # Agregar al resultado con formato YYYY-MM-01
                month_key = f"{current_year}-{current_month:02d}-01"
                result[month_key] = int(days_worked)

            # Avanzar al siguiente mes
            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1

        # Ajustar el último mes a 30 días siempre
        # if result:
        #     last_month_key = max(result.keys())
        #     result[last_month_key] = 30

        return result

    def get_months_without_payslips(self, date=False, employee_id=False):
        """
        Retorna solo los meses que no tienen payslips (aparecerán con string vacío).
        """
        all_data = self.get_holidays_liquidations(date, employee_id)
        months_without_data = [record for record in all_data if not record.get("has_payslip", False)]

        return {
            "total_months": len(all_data),
            "months_without_payslips": len(months_without_data),
            "missing_months": [{"mes": r["month"], "employee_id": employee_id} for r in months_without_data]
        }



    def get_values_income(self, employee, date_star, date_end ):
        valor_1, totales = self.get_holidays_liquidations(date_star, date_end, employee)

        return totales.get('neto')

    def get_values_vacations(self, employee, date_star, date_end ):
        valor_1, totales = self.get_holidays_liquidations(date_star, date_end, employee)

        return totales.get('holidays')


    def get_vacation_period_with_completed_year(self, date_start: date, date_end: date) -> Tuple[
        Union[date, bool], Union[date, bool]]:


        # Verificar si el empleado tiene al menos un año de antigüedad
        if not self._has_minimum_one_year_service(date_start, date_end):
            return date_start, date_end

        # Calcular el período de vacaciones actual
        vacation_start, vacation_end = self._get_current_vacation_period(date_start, date_end)

        return vacation_start, vacation_end


    def get_diccionary_for_decimos(self, employee_id, date_start, date_end):
        valor_1, totales = self.get_holidays_liquidations(date_start, date_end, employee_id=employee_id)

        return self.extract_date_amount(valor_1)

    def get_values_total(self, employee, date_star, date_end, text):
        valor_1, totales = self.get_holidays_liquidations(date_star, date_end, employee)

        return totales.get(text)

    def extract_date_amount(self, data):

        result = []

        for item in data:
            obj = SimpleNamespace(
                date=item['month'],
                amount=self.safe_float_conversion(item['neto'])
            )
            result.append(obj)

        return result

    def safe_float_conversion(self, value, default=0.0):
        if value is None or value == 'N/A' or value == '':
            return default

        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def days_worked_compute_employee(self, calculation_start_date, calculation_end_date, employee_start_date,
                                     employee_end_date=False):
        # Convertir strings a objetos date si es necesario
        if isinstance(calculation_start_date, str):
            calculation_start_date = date.fromisoformat(calculation_start_date)
        if isinstance(calculation_end_date, str):
            calculation_end_date = date.fromisoformat(calculation_end_date)
        if isinstance(employee_start_date, str):
            employee_start_date = date.fromisoformat(employee_start_date)
        if employee_end_date and isinstance(employee_end_date, str):
            employee_end_date = date.fromisoformat(employee_end_date)

        # Mapeo de números de mes a abreviaciones en español
        month_names = {
            1: 'ene', 2: 'feb', 3: 'mar', 4: 'abr', 5: 'may', 6: 'jun',
            7: 'jul', 8: 'ago', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dic'
        }

        # Calcular el período efectivo de trabajo
        # Inicio efectivo: lo más tarde entre inicio de cálculo e inicio de empleado
        effective_start_date = max(calculation_start_date, employee_start_date)

        # Fin efectivo: lo más temprano entre fin de cálculo y fin de empleado (si existe)
        if employee_end_date is False or employee_end_date is None:
            # Empleado activo - usar fecha fin de cálculo
            effective_end_date = calculation_end_date
        else:
            # Empleado con fecha de salida - usar la menor
            effective_end_date = min(calculation_end_date, employee_end_date)

        # Si la fecha efectiva de inicio es posterior a la de fin, no hay días trabajados
        if effective_start_date > effective_end_date:
            return {
                'data': self.extract_date_amount([]),
                'total_days': 0
            }

        result = []
        total_days = 0  # Variable para sumar todos los días

        # Iterar por cada mes en el período efectivo
        current_date = date(effective_start_date.year, effective_start_date.month, 1)
        end_month = date(effective_end_date.year, effective_end_date.month, 1)

        while current_date <= end_month:
            # Definir inicio y fin del mes actual
            days_in_month = monthrange(current_date.year, current_date.month)[1]
            month_start = current_date
            month_end = date(current_date.year, current_date.month, days_in_month)

            # Calcular el período trabajado en este mes
            work_start_in_month = max(effective_start_date, month_start)
            work_end_in_month = min(effective_end_date, month_end)

            # Calcular días trabajados en base a 30 días
            if work_start_in_month <= work_end_in_month:
                # Días reales trabajados en el mes
                actual_days_worked = (work_end_in_month - work_start_in_month).days + 1

                # Total de días en el mes
                total_days_in_month = (month_end - month_start).days + 1

                # Proporción trabajada
                proportion_worked = actual_days_worked / total_days_in_month

                # Días en base 30
                days_worked_30_base = round(proportion_worked * 30, 0)

                # Crear formato de fecha (ej: 'abr-25')
                month_abbr = month_names[current_date.month]
                year_abbr = str(current_date.year)[-2:]
                date_str = f"{month_abbr}-{year_abbr}"

                month_days = int(days_worked_30_base)
                result.append({
                    'month': date_str,
                    'neto': month_days
                })

                # Sumar al total
                total_days += month_days

            # Avanzar al siguiente mes
            if current_date.month == 12:
                current_date = date(current_date.year + 1, 1, 1)
            else:
                current_date = date(current_date.year, current_date.month + 1, 1)

        # Retornar diccionario con data procesada y total por separado
        return {
            'data': self.extract_date_amount(result),
            'total_days': total_days
        }


    def get_days_for_decimo_c(self, calculation_start_date, calculation_end_date, employee_start_date, employee_end_date=False):
       data = self.days_worked_compute_employee(calculation_start_date, calculation_end_date, employee_start_date,
                                     employee_end_date)

       return data.get('data')


    def get_days_for_decimo(self, calculation_start_date, calculation_end_date, employee_start_date, employee_end_date=False):
       data = self.days_worked_compute_employee(calculation_start_date, calculation_end_date, employee_start_date,
                                     employee_end_date)

       return data.get('total_days')









