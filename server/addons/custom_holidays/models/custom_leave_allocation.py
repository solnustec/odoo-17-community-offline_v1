
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

    @api.depends('holiday_type')
    def _compute_from_holiday_type(self):
        """
        Override to prevent employee_id from being overwritten to current user (Administrator)
        when the accrual cron job runs. The base Odoo method falls back to self.env.user.employee_id
        when employee_ids is empty, which causes the bug where all allocations get assigned to Admin.
        """
        for allocation in self:
            if allocation.holiday_type == 'employee':
                # Preserve existing employee_id - do NOT fall back to current user
                if not allocation.employee_ids and allocation.employee_id:
                    allocation.employee_ids = allocation.employee_id
                elif not allocation.employee_ids and not allocation.employee_id:
                    # Only set default for NEW records being created (no id yet)
                    if not allocation.id:
                        default_employee = self.env['hr.employee'].browse(
                            self.env.context.get('default_employee_id')
                        ) or self.env.user.employee_id
                        if default_employee:
                            allocation.employee_ids = default_employee
            elif allocation.holiday_type == 'company':
                allocation.employee_ids = self.env['hr.employee'].search([
                    ('company_id', '=', allocation.mode_company_id.id)
                ]) if allocation.mode_company_id else False
            elif allocation.holiday_type == 'department':
                allocation.employee_ids = self.env['hr.employee'].search([
                    ('department_id', '=', allocation.department_id.id)
                ]) if allocation.department_id else False
            elif allocation.holiday_type == 'category':
                allocation.employee_ids = allocation.category_id.employee_ids if allocation.category_id else False

    @api.depends('employee_ids')
    def _compute_from_employee_ids(self):
        """
        Override to prevent employee_id from being overwritten to current user (Administrator).
        This method is called when employee_ids changes - we ensure existing employee_id is preserved.
        """
        for allocation in self:
            if allocation.employee_ids:
                # If employee_ids has values, use the first one
                allocation.employee_id = allocation.employee_ids[0]._origin
            elif allocation.employee_id:
                # Preserve existing employee_id - do NOT fall back to current user
                pass
            else:
                # Only set default for NEW records being created (no id yet)
                if not allocation.id:
                    default_employee = self.env['hr.employee'].browse(
                        self.env.context.get('default_employee_id')
                    ) or self.env.user.employee_id
                    allocation.employee_id = default_employee
                # For existing records without employee_id, leave as is (don't assign Admin)

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
