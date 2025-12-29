#-*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import gc
from collections import defaultdict

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

class HrWorkEntry(models.Model):
    _inherit = 'hr.work.entry'

    attendance_id = fields.Many2one('hr.attendance', 'Attendance')

    def _load_employee_contracts(self, employee_ids, date_ranges, batch_size=1000, continue_attendance=False, context=None):

        employee_ids = set(employee_ids)
        if not employee_ids or not date_ranges:
            return {}, {}

        employees = self.env['hr.employee'].browse(employee_ids).exists()
        employee_map = {emp.id: emp for emp in employees}
        # Determinar el rango global de fechas
        min_date = min(date_start for _, date_start, _ in date_ranges)
        max_date = max(date_end for _, _, date_end in date_ranges)

        domain = [
            ('employee_id', 'in', list(employee_map.keys())),
            ('state', 'in', ['open', 'pending', 'close']),
            '|', ('date_end', '=', False), ('date_end', '>=', min_date),
            ('date_start', '<=', max_date)
        ]

        contracts = self.env['hr.contract'].search(domain)
        # Liberar caché del ORM
        self.env.clear()
        gc.collect()

        contracts_by_employee = defaultdict(list)
        for contract in contracts:
            contracts_by_employee[contract.employee_id.id].append(contract)

        del contracts
        gc.collect()

        # Procesar rangos de fechas en lotes
        contract_map = {}
        errors_by_employee = defaultdict(list)
        for i in range(0, len(date_ranges), batch_size):
            batch_ranges = date_ranges[i:i + batch_size]
            for emp_id, date_start, date_end in batch_ranges:
                if emp_id not in employee_map:
                    continue
                key = (emp_id, date_start, date_end)
                matching_contracts = [
                    c for c in contracts_by_employee[emp_id]
                    if (c.date_start <= date_end and
                        (not c.date_end or c.date_end >= date_start))
                ]

                if not matching_contracts:
                    errors_by_employee[emp_id].append(('no_contract', date_start, date_end))
                elif len(matching_contracts) > 1:
                    errors_by_employee[emp_id].append(('multiple_contracts', date_start, date_end))
                else:
                    contract_map[key] = matching_contracts[0].id

            gc.collect()

        contract_map = {}
        errors_by_type = {
            'no_contract': set(),
            'multiple_contracts': set()
        }
        for i in range(0, len(date_ranges), batch_size):
            batch_ranges = date_ranges[i:i + batch_size]
            for emp_id, date_start, date_end in batch_ranges:
                if emp_id not in employee_map:
                    continue
                key = (emp_id, date_start, date_end)
                matching_contracts = [
                    c for c in contracts_by_employee[emp_id]
                    if (c.date_start <= date_end and
                        (not c.date_end or c.date_end >= date_start))
                ]

                if not matching_contracts:
                    errors_by_type['no_contract'].add(emp_id)
                elif len(matching_contracts) > 1:
                    errors_by_type['multiple_contracts'].add(emp_id)
                else:
                    contract_map[key] = matching_contracts[0].id

            gc.collect()

        errors = []
        if errors_by_type['no_contract']:

            employee_names = [employee_map[emp_id].name for emp_id in errors_by_type['no_contract']]
            errors.append(
                _("Los siguientes empleados presentan inconsistencias: no tienen contrato, las fechas no coinciden o el estado no es 'En proceso':\n%s",
                  "\n".join(f"- {name}" for name in sorted(employee_names)))
            )
        if errors_by_type['multiple_contracts']:
            employee_names = [employee_map[emp_id].name for emp_id in errors_by_type['multiple_contracts']]
            errors.append(
                _("Los siguientes empleados tienen múltiples contratos:\n%s",
                  "\n".join(f"- {name}" for name in sorted(employee_names)))
            )

        if errors and not continue_attendance:
            error_popup = self.env['error.popup.custom'].create({
                'error_messages': "\n".join(errors),
                'date_start': context.get('default_date_start'),
                'date_end': context.get('default_date_end'),
            })

            del contracts_by_employee
            del date_ranges
            del employees
            gc.collect()

            return {
                'type': 'ir.actions.act_window',
                'name': 'Errores de proceso',
                'res_model': 'error.popup.custom',
                'res_id': error_popup.id,
                'view_mode': 'form',
                'context': context,
                'view_id': self.env.ref('custom_attendance.view_error_popup_form').id,
                'target': 'new',
            }

        del contracts_by_employee
        del date_ranges
        del employees
        gc.collect()

        return employee_map, contract_map

    @api.model
    def _set_current_contracts(self, vals_list, continue_attendance=False, context=None):

        if not vals_list:
            return []

        is_single_dict = isinstance(vals_list, dict)
        vals_list = [vals_list] if is_single_dict else list(vals_list)

        to_process = [
            vals for vals in vals_list
            if not vals.get('contract_id') and
               vals.get('date_start') and
               vals.get('date_stop') and
               vals.get('employee_id')
        ]

        if not to_process:
            return vals_list

        employee_ids = {vals['employee_id'] for vals in to_process}
        date_ranges = [
            (
                vals['employee_id'],
                fields.Datetime.to_datetime(vals['date_start']).date(),
                fields.Datetime.to_datetime(vals['date_stop']).date()
            )
            for vals in to_process
        ]

        result = self._load_employee_contracts(
            employee_ids, date_ranges,
            continue_attendance=continue_attendance,
            context=context
        )


        if isinstance(result, dict) and result.get('type') == 'ir.actions.act_window' and not continue_attendance:
            return result

        employee_map, contract_map = result

        result = []
        for vals in vals_list:
            if not (vals.get('date_start')
                and vals.get('date_stop')
                and vals.get('employee_id')
                and not vals.get(
                    'contract_id')):

                result.append(vals.copy())
                continue

            employee_id = vals['employee_id']
            date_start = fields.Datetime.to_datetime(vals['date_start']).date()
            date_end = fields.Datetime.to_datetime(vals['date_stop']).date()
            key = (employee_id, date_start, date_end)

            contract_id = contract_map.get(key)
            if contract_id:
                new_vals = vals.copy()
                new_vals['contract_id'] = contract_id
                result.append(new_vals)
            else:
                if continue_attendance:
                    continue
                else:
                    result.append(vals.copy())

        return result


    def create_entrys(self, vals_list, continue_attendance=False, context=None):
        result = self._set_current_contracts(vals_list, continue_attendance, context)

        # Check if the result is an action (error popup)
        if isinstance(result, dict) and result.get('type') == 'ir.actions.act_window':
            return result

        vals_list = result
        work_entries = super(models.Model, self).create(vals_list)
        return work_entries



