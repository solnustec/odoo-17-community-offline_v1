# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrDepartureWizard(models.TransientModel):
    _inherit = 'hr.departure.wizard'

    is_on_the_blacklist = fields.Boolean(string='¿Está en la lista negra?')
    note_for_on_the_blacklist = fields.Html(string='Razón de estar en lista negra')


    def action_register_departure(self):
        # super(HrDepartureWizard, self).action_register_departure()

        if self.release_campany_car:
            self._free_campany_car()

        employee = self.employee_id
        if self.env.context.get('toggle_active', False) and employee.active:
            employee.with_context(no_wizard=True).toggle_active()
        employee.departure_reason_id = self.departure_reason_id
        employee.departure_description = self.departure_description
        employee.departure_date = self.departure_date
        employee.is_on_the_blacklist = self.is_on_the_blacklist
        employee.note_for_on_the_blacklist = self.note_for_on_the_blacklist

        if self.cancel_leaves:
            future_leaves = self.env['hr.leave'].search([('employee_id', '=', self.employee_id.id),
                                                         ('date_to', '>', self.departure_date),
                                                         ('state', '!=', 'refuse')])
            future_leaves.action_refuse()

        if self.archive_allocation:
            employee_allocations = self.env['hr.leave.allocation'].search([('employee_id', '=', self.employee_id.id)])
            if employee_allocations:
                employee_allocations.sudo().write({'state': 'refuse'})
                employee_allocations.action_archive()

        current_contract = self.sudo().employee_id.contract_id
        if current_contract and current_contract.date_start > self.departure_date:
            raise UserError(_("Departure date can't be earlier than the start date of current contract."))

        # super(HrDepartureWizard, self).action_register_departure()
        if self.set_date_end:
            self.sudo().employee_id.contract_ids.filtered(lambda c: c.state == 'draft').write({'state': 'cancel'})
            if current_contract and current_contract.state in ['open', 'draft']:
                self.sudo().employee_id.contract_id.write({'date_end': self.departure_date})
            if current_contract.state == 'open':
                current_contract.state = 'close'