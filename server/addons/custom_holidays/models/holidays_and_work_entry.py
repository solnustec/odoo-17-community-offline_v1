
from odoo import models, fields, api
from math import ceil
class HrLeaveInherit(models.Model):
    _inherit = 'hr.leave'

    def _get_duration(self, check_leave_type=True, resource_calendar=None):
        duration = super(HrLeaveInherit, self)._get_duration(check_leave_type=check_leave_type, resource_calendar=resource_calendar)
        if self.holiday_status_id.exclude_weekends:
            return duration

        self.ensure_one()
        resource_calendar = resource_calendar or self.resource_calendar_id

        if not self.date_from or not self.date_to:
            return (0, 0)

        total_seconds = (self.date_to - self.date_from).total_seconds()
        days = (total_seconds // 86400) + 1

        remaining_seconds = total_seconds % 86400
        hours = remaining_seconds / 3600

        if self.leave_type_request_unit == 'day' and check_leave_type:
            days = ceil(days)

        return (days, hours)

    def _cancel_work_entry_conflict(self):
        """
        Creates a leave work entry for each hr.leave in self.
        Check overlapping work entries with self.
        Work entries completely included in a leave are archived.
        e.g.:
            |----- work entry ----|---- work entry ----|
                |------------------- hr.leave ---------------|
                                    ||
                                    vv
            |----* work entry ****|
                |************ work entry leave --------------|
        """
        pass


    def _validate_leave_request(self):
        super(HrLeaveInherit, self)._validate_leave_request()
        # self.sudo()._cancel_work_entry_conflict()  # delete preexisting conflicting work_entries
        return True



