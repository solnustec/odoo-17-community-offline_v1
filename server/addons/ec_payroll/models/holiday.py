# -*- coding: utf-8 -*-
from odoo import models, fields, registry, api
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tools.misc import formatLang
from odoo.tools import float_is_zero, float_compare, float_round
from odoo.osv import expression
from collections import OrderedDict
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DTF
from odoo import SUPERUSER_ID
from datetime import datetime
from datetime import time as datetime_time
from dateutil import relativedelta
import time

from lxml import etree
import logging
_logger = logging.getLogger(__name__)

class HrHolidaysStatus(models.Model):

    _inherit = 'hr.holidays.status'

    code = fields.Char(string=u'Código para Nómina', index=True, 
                       required=False, readonly=False, states={}, help=u"") 
    
    _sql_constraints = [('code_uniq', 'unique(company_id, code)', _('El código para el tipo de ausencia debe ser único!')), ]
    
    is_paid = fields.Boolean(string=u'Es pagada?', readonly=False, states={}, help=u"") 


class HrPayslipWorkedDays(models.Model):
    
    _inherit = 'hr.payslip.worked_days'
    
    @api.model
    def _get_holiday_status(self):
        status_model = self.env['hr.holidays.status']
        res = [('0', 'Días Trabajados 100%')]
        for status in status_model.search([]):
            res.append((status.id, status.name))
        return res

    holiday_status = fields.Selection(selection=_get_holiday_status, string='Tipo de Día', readonly=False, required=False, ) 


class HrPayslip(models.Model):
    
    _inherit = 'hr.payslip' 
    
    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        res = super(HrPayslip, self).get_worked_day_lines(contracts, date_from, date_to)
        if not contracts:
            return res
        status_model = self.env['hr.holidays.status']
        data = []
        date_from = max(fields.Datetime.from_string(date_from), fields.Datetime.from_string(contracts[0].date_start))
        date_to = contracts[0].date_end and min(fields.Datetime.from_string(date_to), fields.Datetime.from_string(contracts[0].date_end)) or fields.Datetime.from_string(date_to)
        delta = (date_to + relativedelta.relativedelta(days = 1)) - date_from
        start = fields.Datetime.from_string('2018-04-01')
        stop = fields.Datetime.from_string('2018-04-30').replace(hour=23, minute=59, second=59, microsecond=999999)
        total_hours_day = (contracts[0].resource_calendar_id.get_work_hours_count(start, stop, False, compute_leaves=False)) / 21
        worked_days = delta.days
        if max(date_from, date_to).month == 2 and worked_days in (28, 29):
            worked_days = 30
        work_line = {}
        for line in res:
            if line.get('code') == 'WORK100':
                line.update({
                    'holiday_status': '0',
                    'number_of_days': worked_days,
                    'number_of_hours': worked_days * total_hours_day,
                    })
                data.append(line)
                work_line = line
            else:
                status = status_model.search([('name', '=', line.get('code'))])
                if status:
                    if not status.code:
                        raise UserError(_(u'Debe configurar el código del tipo de ausencia %s') % (status.display_name))
                    line.update({
                        'code': status[0].code,
                        'holiday_status': status.id,
                        })
                    if not status.is_paid:
                        work_line['number_of_days'] -= line.get('number_of_days', 0.0)
        return res
