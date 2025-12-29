

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError
from datetime import datetime, time
from dateutil.relativedelta import relativedelta

class HrLeave(models.Model):
    _inherit = 'hr.leave'
    def action_confirm(self):
        start = min(self.mapped('date_from'), default=False)
        stop = max(self.mapped('date_to'), default=False)
        with self.env['hr.work.entry']._error_checking(start=start, stop=stop, employee_ids=self.employee_id.ids):
            return super().action_confirm()

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('holiday_type', 'employee') == 'employee' and not vals.get(
                'multi_employee', False) and not vals.get('employee_id', False) for vals
               in vals_list):
            raise ValidationError(
                _("There is no employee set on the time off. Please make sure you're logged in the correct company."))
        employee_ids = {v['employee_id'] for v in vals_list if v.get('employee_id')}
        # We check a whole day before and after the interval of the earliest
        # request_date_from and latest request_date_end because date_{from,to}
        # can lie in this range due to time zone reasons.
        # (We can't use date_from and date_to as they are not yet computed at
        # this point.)
        start_dates = [fields.Date.to_date(v.get('request_date_from')) for v in
                       vals_list if v.get('request_date_from')]
        stop_dates = [fields.Date.to_date(v.get('request_date_to')) for v in vals_list
                      if v.get('request_date_to')]
        start = datetime.combine(
            min(start_dates, default=datetime.max.date()) - relativedelta(days=1),
            time.min)
        stop = datetime.combine(
            max(stop_dates, default=datetime.min.date()) + relativedelta(days=1),
            time.max)
        with self.env['hr.work.entry']._error_checking(start=start, stop=stop,
                                                       employee_ids=employee_ids):
            return super().create(vals_list)


    def write(self, vals):
        if not self:
            return True
        skip_check = not bool({'employee_id', 'state', 'request_date_from', 'request_date_to'} & vals.keys())
        employee_ids = self.employee_id.ids
        if 'employee_id' in vals and vals['employee_id']:
            employee_ids += [vals['employee_id']]
        # We check a whole day before and after the interval of the earliest
        # request_date_from and latest request_date_end because date_{from,to}
        # can lie in this range due to time zone reasons.
        # (We can't use date_from and date_to as they are not yet computed at
        # this point.)
        start_dates = self.filtered('request_date_from').mapped('request_date_from') + [fields.Date.to_date(vals.get('request_date_from', False)) or datetime.max.date()]
        stop_dates = self.filtered('request_date_to').mapped('request_date_to') + [fields.Date.to_date(vals.get('request_date_to', False)) or datetime.min.date()]
        start = datetime.combine(min(start_dates) - relativedelta(days=1), time.min)
        stop = datetime.combine(max(stop_dates) + relativedelta(days=1), time.max)
        with self.env['hr.work.entry']._error_checking(start=start, stop=stop, skip=skip_check, employee_ids=employee_ids):
            return super().write(vals)
