
from odoo import models, fields
from odoo.osv import expression

class ErrorPopup(models.TransientModel):
    _name = 'hr.popup.liquidations'
    _description = 'Generate Payslip for Liquidations'

    #
    payslip_context = fields.Many2one( 'hr.payslip', string="Payslip de contexto", readonly=True)


    def continue_and_generate(self):

        payslip_employees = self.env['hr.payslip.employees'].sudo()
        employees_witout_contract = payslip_employees._generate_payslips(payslip_general, employees, self.struct_id.id,
                                                                         self.is_history_payslip)





        attendances = self.env['hr.work.entry'].sudo().search([
            ('date_start', '>=', self.date_start),
            ('date_stop', '<=', self.date_end)
        ])

        if attendances.exists():
            attendances.sudo().unlink()
        parent_model = 'hr.attendance.general.modal'
        # parent_model = self.env.context.get('active_model')
        # parent_record = self.env[parent_model].browse(self.env.context.get('active_id'))
        parent_record = self.env[parent_model].sudo().search([], order='id desc', limit=1)
        continue_attendance = True
        result = parent_record.process(False, continue_attendance=continue_attendance)

        if result:
            return result
    # def action_confirm(self):

    def _generate_payslips_custom(self, payslip, employees, structure_id=False, is_history_payslip=False):
        Payslip = self.env['hr.payslip'].sudo()
        default_values = Payslip.default_get(Payslip.fields_get())
        batch_size = 200



        contracts, employees_not_found = self.get_contractsCustom(
            employees, payslip.date_from, payslip.date_to
        )

        contract_ids = contracts.ids
        for i in range(0, len(contract_ids), batch_size):

            batch_contracts = contracts.browse(contract_ids[i:i + batch_size])
            payslip_vals = [
                dict(default_values, **{
                    'name': _('New Payslip'),
                    'employee_id': contract.employee_id.id,
                    # 'payslip_run_id': payslip_run.id,
                    'date_from': payslip.date_from,
                    'date_to': payslip.date_end,
                    'contract_id': contract.id,
                    'is_history_payslip': is_history_payslip,
                    'struct_id':  structure_id or self.structure_id.id or contract.structure_type_id.default_struct_id.id,
                })

                for contract in batch_contracts
            ]
            payslips = Payslip.with_context(tracking_disable=True).create(payslip_vals)
            payslips._compute_name()
            payslips.compute_sheet()

        return employees_not_found


    def continue_process(self):



    def get_contractsCustom(self, employees, date_from, date_to, states=['open'], kanban_state=False):
        state_domain = [('state', 'in', ['open', 'close'])]
        if kanban_state:
            state_domain = expression.AND([state_domain, [('kanban_state', 'in', kanban_state)]])

        # Buscar todos los contratos que coincidan con los criterios
        contracts_found = self.env['hr.contract'].search(
            expression.AND([[('employee_id', 'in', employees.ids)],
                            state_domain,
                            [('date_start', '<=', date_to),
                             '|',
                             ('date_end', '=', False),
                             ('date_end', '>=', date_from)]])
        )

        # Obtener IDs de empleados que tienen contratos
        employees_with_contracts_ids = contracts_found.mapped('employee_id').ids
        employees_without_contracts = employees.filtered(
            lambda emp: emp.id not in employees_with_contracts_ids
        )

        return contracts_found, employees_without_contracts







