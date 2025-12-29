
# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.addons.resource.models.utils import HOURS_PER_DAY

class CustomLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    allocation_type = fields.Selection([
        ('regular', 'Regular Allocation'),
        ('accrual', 'Accrual Allocation')
    ], string="Allocation Type", default="regular", required=True, readonly=False)

    employee_id = fields.Many2one('hr.employee', ondelete='cascade')



    @api.depends('holiday_status_id', 'allocation_type', 'number_of_hours_display',
                 'number_of_days_display', 'date_to')
    def _compute_from_holiday_status_id(self):
        accrual_allocations = self.filtered(lambda
                                                alloc: alloc.allocation_type == 'accrual' and not alloc.accrual_plan_id and alloc.holiday_status_id)
        accruals_read_group = self.env['hr.leave.accrual.plan']._read_group(
            [('time_off_type_id', 'in', accrual_allocations.holiday_status_id.ids)],
            ['time_off_type_id'],
            ['id:array_agg'],
        )
        accruals_dict = {time_off_type.id: ids for time_off_type, ids in
                         accruals_read_group}
        for allocation in self:
            allocation_unit = allocation._get_request_unit()
            if allocation_unit != 'hour':
                allocation.number_of_days = allocation.number_of_days_display
            else:
                hours_per_day = allocation.employee_id.sudo().resource_calendar_id.hours_per_day \
                                or allocation.holiday_status_id.company_id.resource_calendar_id.hours_per_day \
                                or HOURS_PER_DAY
                allocation.number_of_days = allocation.number_of_hours_display / hours_per_day
            if allocation.accrual_plan_id.time_off_type_id.id not in (
            False, allocation.holiday_status_id.id):
                allocation.accrual_plan_id = False
            if allocation.allocation_type == 'accrual' and not allocation.accrual_plan_id:
                if allocation.holiday_status_id:
                    allocation.accrual_plan_id = \
                    accruals_dict.get(allocation.holiday_status_id.id, [False])[0]
    @api.model_create_multi
    def create(self, vals_list):
        """ Override to avoid automatic logging of creation """
        records = super(CustomLeaveAllocation, self).create(vals_list)
        for record in records:
            record._onchange_allocation_type()
            record._onchange_date_from()
            record._compute_has_accrual_plan()
            record._compute_holiday_status_id()
            record._compute_type_request_unit()

        return records
