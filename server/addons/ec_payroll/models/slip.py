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
from dateutil.relativedelta import relativedelta
from dateutil import rrule
import time
from lxml import etree
from odoo import tools
import logging
import babel
from pytz import timezone, utc
import pytz


_logger = logging.getLogger(__name__)

TIPO_CUENTA={'savings':'AHORROS','current':'CORRIENTE','virtual': 'VIRTUAL','no':''}

MONTHS = {
    '1': 'Enero',
    '2': 'Febrero',
    '3': 'Marzo',
    '4': 'Abril',
    '5': 'Mayo',
    '6': 'Junio',
    '7': 'Julio',
    '8': 'Agosto',
    '9': 'Septiembre',
    '10': 'Octubre',
    '11': 'Noviembre',
    '12': 'Diciembre',
}


class hr_payslip_run(models.Model):
    _inherit = 'hr.payslip.run'

    type_slip_pay = fields.Selection([('slip', 'Roles'), ('holiday', 'Vacaciones'), ('thirteenth', 'Décimo Tercero'), ('fourteenth', 'Décimo Cuarto')], string=u'Tipo de Nómina',
                    default='slip')


class hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_note(self):
        account=''
        bank=''
        type_account=''
        if self.employee_id:
            if self.employee_id.bank_account_id:
                account=''
                bank=''
                type_account=''
                type_account=TIPO_CUENTA[self.employee_id.bank_account_id.type_account]
                account=self.employee_id.bank_account_id.acc_number
                bank=self.employee_id.bank_account_id.bank_id.name if self.employee_id.bank_account_id.bank_id else ''

        return ('Nota: Los valores fueron acreditados a su cuenta %s del banco %s')%(type_account+ ' '+account,bank)

    contract_id = fields.Many2one(comodel_name='hr.contract', strin="Contrato")
    # payment_ids = fields.One2many('account.payment', 'slip_id', string=u'Pagos Relacionados',
    #                               required=False, readonly=True, help=u"")
    # payment_line_ids = fields.One2many('account.payment.line', 'slip_id', string=u'Líneas de Pagos Relacionados',
    #                                    required=False, readonly=True, help=u"")
    payslip_run_id = fields.Many2one(comodel_name='hr.payslip.run', string='Payslip Batches', readonly=True,
                                      copy=False, states={'draft': [('readonly', False)]}, ondelete="cascade")
    contract_date_start = fields.Date(string=u'Fecha de Ingreso', related="contract_id.date_start", store=True, readonly=True)
    analytic_account_id = fields.Many2one(string=u'Cuenta Analítica', related="contract_id.analytic_account_id",
                                          store=True)
    type_slip_pay = fields.Selection(related="payslip_run_id.type_slip_pay", string=u'Tipo Nómina', store=True)
    note_roll = fields.Char('Nota para el Rol',)
    period_rol = fields.Char('Periodo Pago')
    wage = fields.Monetary(related='contract_id.wage',store=True)
    value_for_parcial =fields.Float(related='contract_id.value_for_parcial', store=True)
    type_day = fields.Selection(related='contract_id.type_day', store=True)

    # @api.depends(
    #     'payment_ids',
    #     'payment_ids.amount',
    #     'payment_ids.state',
    #     'payment_line_ids',
    #     # 'payment_line_ids.amount',
    #     # 'payment_line_ids.payment_id.amount',
    #     # 'payment_line_ids.payment_id.state',
    # )
    # def _get_paid_status(self):
    #     for sline in self:
    #         total_paid = sum([p.amount for p in sline.payment_ids if p.state not in ('draft', 'cancelled')])
    #         sline.paid = total_paid == sline.payslip_net
    #
    # paid = fields.Boolean(string=u'Pagado?', store=False,
    #                       compute='_get_paid_status', help=u"")



    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        res = []

        structure_type_id = self.env.context.get('structure_type', False)

        structure_ids = contracts.with_context(structure_type=structure_type_id).get_all_structures()
        rule_ids = self.env['hr.payroll.structure'].browse(structure_ids).get_all_rules()
        sorted_rule_ids = [id for id, sequence_order in sorted(rule_ids, key=lambda x:x[1])]
        inputs = self.env['hr.salary.rule'].browse(sorted_rule_ids).mapped('input_ids')

        for contract in contracts:
            for input in inputs:
                input_data = {
                    'name': input.name,
                    'code': input.code,
                    'contract_id': contract.id,
                }
                res += [input_data]
        return res


    def onchange_employee_id(self, date_from, date_to, employee_id=False, contract_id=False):
        #defaults
        res = {
            'value': {
                'line_ids': [],
                #delete old input lines
                'input_line_ids': [(2, x,) for x in self.input_line_ids.ids],
                #delete old worked days lines
                'worked_days_line_ids': [(2, x,) for x in self.worked_days_line_ids.ids],
                #'details_by_salary_head':[], TODO put me back
                'name': '',
                'contract_id': False,
                'struct_id': False,
            }
        }

        if (not employee_id) or (not date_from) or (not date_to):
            return res
        ttyme = datetime.fromtimestamp(time.mktime(time.strptime(date_from, "%Y-%m-%d")))
        employee = self.env['hr.employee'].browse(employee_id)
        locale = self.env.context.get('lang') or 'en_US'
        res['value'].update({
            'name': _('Salary Slip of %s for %s') % (employee.name, tools.ustr(babel.dates.format_date(date=ttyme, format='MMMM-y', locale=locale))),
            'company_id': employee.company_id.id,
        })

        if not self.env.context.get('contract'):
            #fill with the first contract of the employee
            contract_ids = self.get_contract(employee, date_from, date_to)
        else:
            if contract_id:
                #set the list of contract for which the input have to be filled
                contract_ids = [contract_id]
            else:
                #if we don't give the contract, then the input to fill should be for all current contracts of the employee
                contract_ids = self.get_contract(employee, date_from, date_to)

        if not contract_ids:
            return res
        contract = self.env['hr.contract'].browse(contract_ids[0])
        res['value'].update({
            'contract_id': contract.id
        })
        struct = contract.struct_id
        if not struct:
            return res
        res['value'].update({
            'struct_id': struct.id,
        })
        #computation of the salary input

        contracts = self.env['hr.contract'].browse(contract_ids)

        worked_days_line_ids = []

        # if self:
        #     worked_days_line_ids = self.with_context(contract_id=self.env.context.get('contract', False))._get_worked_day_lines()
        if self.env.context.get('contract', False):
            worked_days_line_ids = self.with_context(contract_id=self.env.context.get('contract', False))._get_worked_day_lines_for_liquidation()

        # input_line_ids = self.get_inputs(contracts, date_from, date_to)


        input_line_ids = []
        res['value'].update({
            'worked_days_line_ids': worked_days_line_ids,
            'input_line_ids': input_line_ids,
        })
        return res

    def get_days_proportion(self,day_rounded,hours,total_hours,work_entry_type,leave_exist,work_exist):

        hours_ec=240
        days_ec=30

        percent=0
        day_rounded_new=0
        hours_new=0
        total_hours_new=0



        # tz = pytz.timezone(calendar.tz)

        end_month=max(fields.Datetime.from_string(self.date_from), fields.Datetime.from_string(self.date_to)) + relativedelta(months=1, day=1, days=-1)


        date_from   =    self.env['hr.request.subsidy'].ics_datetime(self.date_from)
        date_to     =    self.env['hr.request.subsidy'].ics_datetime(self.date_to)

        total_hours_calendar=self.contract_id.resource_calendar_id.get_work_hours_count(date_from,date_to)



        if self.contract_id.type_day=='complete':
            # percent= day_rounded / (total_hours/8)

            if self.contract_id.date_start<=self.date_from :
                day_rounded_new=round(days_ec * (day_rounded / (total_hours_calendar/8)))
            else:
                day_rounded_new= (days_ec - self.contract_id.date_start.day)+1

                # if work_entry_type.code!='WORK100':
            #     day_rounded_new=day_rounded

            # if day_rounded_new==31:
            #     day_rounded_new=30
            # if end_month.day == 31 and work_entry_type.code=='WORK100' and (day_rounded_new+leave_exist)>30:
            #     day_rounded_new=30-leave_exist


            if work_entry_type.code=='WORK100':
                if day_rounded_new>=28 and not leave_exist and self.contract_id.date_start<=self.date_from:
                    day_rounded_new=30
                # if day_rounded_new>=28 and  leave_exist:
                #     day_rounded_new=30 - leave_exist

                if day_rounded_new and  leave_exist and (day_rounded_new + leave_exist)>=28 and self.contract_id.date_start<=self.date_from :
                    day_rounded_new=30-leave_exist
                if day_rounded_new and  leave_exist and self.contract_id.date_start > self.date_from :
                    day_rounded_new=day_rounded_new-leave_exist

            if work_entry_type.code!='WORK100':
                new_day=round(days_ec * (work_exist / (total_hours_calendar/8)))
                if (day_rounded_new + new_day) >30:
                    # new_day=0
                    if self.contract_id.date_start<=self.date_from :

                        day_rounded_new = 30-new_day
                    else:
                        day_rounded_new=day_rounded
                        # new_day=(self.date_to - self.contract_id.date_start).days






            #     if day_rounded_new>30:
            #         day_rounded_new=30  #day_rounded







            hours_new=day_rounded_new * 8
            total_hours_new=hours_ec
        else:
            desde=self.date_from
            hasta=self.date_to
            bandera=True
            dias_restado=0
            dias_trabajados=0
            lista_dias=[]
            total_trabajado=0
            for dia in self.contract_id.resource_calendar_id.attendance_ids:
                if dia.dayofweek not in lista_dias:
                    lista_dias.append(int(dia.dayofweek))
            dias_calendar=1
            if self.date_from and self.date_to:
                dias_calendar+=(self.date_to-self.date_from).days
            for i in range(dias_calendar):
                if  desde < self.contract_id.date_start:
                    if desde.weekday() in lista_dias:
                        dias_restado += 1

                else:
                    if desde.weekday() in lista_dias:
                        dias_trabajados += 1
                desde += relativedelta(days=1)


                # percent= day_rounded / (total_hours/8)
            if work_entry_type.code=='WORK100':
                day_rounded_new=(round(days_ec * self.contract_id.contracted_hours) / hours_ec)-leave_exist
                # hours_new=self.contract_id.partial_hours
                if dias_restado:
                    day_rounded_new = dias_trabajados-dias_restado

            if work_entry_type.code!='WORK100':

                day_rounded_new=day_rounded

            hours_new= day_rounded_new*self.contract_id.total_hours_day
            total_hours_new=self.contract_id.contracted_hours

        return day_rounded_new,hours_new,total_hours_new

    def get_conf_structure_thirteenth(self):
        return self.env.user.company_id.struct_thirteenth_pay

    def get_conf_structure_fourteenth(self):
        hours_new=0
        return self.env.user.company_id.struct_fourteenth_pay

    def get_conf_rule_thirteenth(self):
        return self.env.user.company_id.rule_thirteenth_id

    def get_conf_rule_fourteenth(self):
        return self.env.user.company_id.rule_fourteenth_id

    def get_conf_days_fourteenth(self):
        return self.env.user.company_id.month_start_fourteenth , self.env.user.company_id.day_start_fourteenth , self.env.user.company_id.month_end_fourteenth , self.env.user.company_id.day_end_fourteenth

    def _get_worked_day_lines_for_liquidation(self):
        """
        :returns: a list of dict containing the worked days values that should be applied for the given payslip
        """


        res = []
        # res= super(hr_payslip, self)._get_worked_day_lines()

        # fill only if the contract as a working schedule linked
        # self.ensure_one()
        contract = self.contract_id or self.env['hr.contract'].search([('id','=', self.env.context.get('contract_id', False))])



        if contract.resource_calendar_id:
            paid_amount = contract.wage
            unpaid_work_entry_types = contract.struct_id.unpaid_work_entry_type_ids.ids
            fecha_fin=now = self.env['cen.tools'].get_date_now()
            if contract.date_end:
                fecha_fin=contract.date_end
            delta = (fecha_fin - (fecha_fin + relativedelta(day=1))).days + 1
            # end_date_calc = self.date_end_contract + relativedelta(months=-1, day=1, days=-1)
            start_date = contract.date_end - relativedelta(days=abs(delta))

            work_hours = contract._get_work_hours(start_date, fecha_fin)
            total_hours = sum(work_hours.values()) or 1
            work_hours_ordered = sorted(work_hours.items(), key=lambda x: x[1])
            biggest_work = work_hours_ordered[-1][0] if work_hours_ordered else 0
            add_days_rounding = 0



            for work_entry_type_id, hours in work_hours_ordered:
                # import pdb
                # pdb.set_trace()
                work_entry_type = self.env['hr.work.entry.type'].browse(work_entry_type_id)
                is_paid = work_entry_type_id not in unpaid_work_entry_types
                calendar = contract.resource_calendar_id
                days = round(hours / calendar.hours_per_day, 5) if calendar.hours_per_day else 0
                if work_entry_type_id == biggest_work:
                    days += add_days_rounding
                day_rounded = self._round_days(work_entry_type, days)
                add_days_rounding += (days - day_rounded)

                if work_entry_type.code!='WORK100':
                    leave_exist=True

                #PROPORCION DIAS EC
                # day_rounded_new,hours_new,total_hours_new =self.get_days_proportion(day_rounded,hours,total_hours,work_entry_type,0)

                attendance_line = {
                    'sequence': work_entry_type.sequence,
                    'work_entry_type_id': work_entry_type_id,
                    'number_of_days': delta,
                    'number_of_hours': delta*8,
                    'amount': 0,
                }

                res.append(attendance_line)
        return res



    @api.model
    def get_payslip_lines_simulate(self, employee_id, date_from, date_to):


        payslip_model = self.env['hr.payslip']
        pline_model = self.env['hr.payslip.line']
        employee_model = self.env['hr.employee']
        employee = employee_model.browse(employee_id)
        contract_ids = payslip_model.get_contract(employee, date_from, date_to)

        if not contract_ids and not self.env.context.get('contract', False):
            raise UserError(_(u'No existe contrato activo para el empleado %s entre las fechas %s y %s') % (employee.display_name, date_from, date_to))
        slip_data = payslip_model.onchange_employee_id(date_from, date_to, employee.id, contract_id=self.env.context.get('contract'))
        slip_data = {
            'employee_id': employee.id,
            'name': slip_data['value'].get('name'),
            'struct_id': slip_data['value'].get('struct_id'),
            'contract_id': slip_data['value'].get('contract_id'),
            'input_line_ids': [(0, 0, x) for x in slip_data['value'].get('input_line_ids')],
            'worked_days_line_ids': [(0, 0, x) for x in slip_data['value'].get('worked_days_line_ids')],
            'date_from': date_from,
            'date_to': date_to,
            'company_id': employee.company_id.id,
        }
        payslip = payslip_model.new(slip_data)
        #payslip.with_context(contract=False).onchange_employee()


        data_lines = payslip_model.get_payslip_lines(contract_ids, payslip)
        lines = pline_model.browse()
        for line in data_lines:
            line.update({
                'slip_id': payslip.id
            })
            lines += pline_model.new(line)
        # import pdb
        # pdb.set_trace()
        return lines

    @api.model
    def get_payslip_lines(self, contract_ids, payslip):
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            localdict['categories'].dict[category.code] = category.code in localdict['categories'].dict and localdict['categories'].dict[category.code] + amount or amount
            return localdict

        class BrowsableObject(object):
            def __init__(self, employee_id, dict, env):
                self.employee_id = employee_id
                self.dict = dict
                self.env = env

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        class InputLine(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""
                    SELECT sum(amount) as sum
                    FROM hr_payslip as hp, hr_payslip_input as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()[0] or 0.0

        class WorkedDays(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def _sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""
                    SELECT sum(number_of_days) as number_of_days, sum(number_of_hours) as number_of_hours
                    FROM hr_payslip as hp, hr_payslip_worked_days as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()

            def sum(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[0] or 0.0

            def sum_hours(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[1] or 0.0

        class Payslips(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""

            def sum(self, code, from_date, to_date=None):

                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)
                            FROM hr_payslip as hp, hr_payslip_line as pl
                            WHERE hp.employee_id = %s AND hp.state = 'done'
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s""",
                                    (self.employee_id, from_date, to_date, code))
                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            def vacations(self,code):
                # import pdb
                # pdb.set_trace()
                objVacations=self.env['hr.request.vacations'].search([('contract_id','=',self.contract_id.id),('payslip_id','=',False),('pay_type','=','enjoy'),('state','=','done')])
                amount_total=0
                if objVacations:
                    objVacations.write({'payslip_id':self.id})
                    amount_total = objVacations.amount_total
                return amount_total

            def subsidy(self,code):
                #('payslip_id','=',False),
                objSubsidy=self.env['hr.request.subsidy'].search([('contract_id','=',self.contract_id.id),('state','=','done')])
                days=0
                if objSubsidy:
                    objSubsidy.write({'payslip_id':self.id})
                    # if objSubsidy.days_total_subsidy>=3:
                    #     days=3
                    # else:
                    days=objSubsidy.days_total_subsidy

                return days

            def sum_fourtheent(self,code):
                month_start, day_start, month_end, day_end =self.env['hr.payslip'].browse(self.id).get_conf_days_fourteenth()
                if not (month_start and day_start and month_end and day_end):
                    raise UserError(_(u'Por favor configure los días y meses de pago del Dédimo Cuarto') )

                rule = self.env['hr.payslip'].browse(self.id).get_conf_rule_fourteenth()
                if not rule:
                    raise UserError(_(u'No existe regla salarial de provisión de Décimo Cuarto Sueldo') )


                year_from = self.env['hr.payslip'].browse(self.id).date_from -relativedelta(years=1)
                year_to = self.env['hr.payslip'].browse(self.id).date_from

                date_start=''.join([str(year_from.year),'-',str(month_start).zfill(2),'-',str(day_start).zfill(2)])
                date_end = ''.join([str(year_to.year),'-',str(month_end).zfill(2),'-',str(day_end).zfill(2)])


                # import pdb
                # pdb.set_trace()
                amount=self.sum(rule.code,date_start,date_end)
                return amount

            def sum_thirteenth(self,code):

                # import pdb
                # pdb.set_trace()
                #
                months=12
                objpayslip = self.env['hr.payslip'].browse(self.id)

                date_start = objpayslip.date_from -relativedelta(months=12)
                date_end=objpayslip.date_from -relativedelta(days=1)

                rule = objpayslip.get_conf_rule_thirteenth()
                if not rule:
                    raise UserError(_(u'No existe regla salarial de provisión de Décimo Tercer Sueldo') )

                amount=self.sum(rule.code,date_start,date_end)
                return amount  #/months

            # def sum_decimo_14(self,code)

        class FondoReserva(BrowsableObject):

            def sum(self,percent_fondo,code,date_from, date_to=None):
                #FIXME: set pecent with parameter

                #

                end_month = max(fields.Datetime.from_string(date_from), fields.Datetime.from_string(date_to)) + relativedelta(months=1, day=1, days=-1)
                delta = 0
                if end_month.day == 31:
                    delta = -1
                elif end_month.day == 28:
                    delta = 2
                elif end_month.day == 29:
                    delta = 1
                elif end_month.day == 30:
                    delta = 0

                if fields.Datetime.from_string(date_from).month ==fields.Datetime.from_string(date_to).month \
                        and fields.Datetime.from_string(date_from).year ==fields.Datetime.from_string(date_to).year - 1:

                    if fields.Datetime.from_string(date_from).day>1:

                        dias = fields.Datetime.from_string(date_to).day -(fields.Datetime.from_string(date_from).day )
                        dias+=delta +1

                        return ((percent_fondo * dias) /30)/100
                    else:
                        return  percent_fondo /100


                else:
                    return  percent_fondo /100


        #we keep a dict with the result because a value can be overwritten by another rule with the same code
        result_dict = {}
        rules_dict = {}
        worked_days_dict = {}
        inputs_dict = {}
        blacklist = []
        fondo_rese={}
        structure_ids=[]
        slip_individual =None
        if not self.payslip_run_id:
            slip_individual=self.contract_id.structure_type_id.id


        # import pdb
        # pdb.set_trace()

        transaction_model = self.env['hr.scheduled.transaction']
        company = self.env.user.company_id
        # import pdb
        # pdb.set_trace()
        for worked_days_line in payslip.worked_days_line_ids:
            worked_days_dict[worked_days_line.code] = worked_days_line
        for input_line in payslip.input_line_ids:
            inputs_dict[input_line.code] = input_line

        categories = BrowsableObject(payslip.employee_id.id, {}, self.env)
        inputs = InputLine(payslip.employee_id.id, inputs_dict, self.env)
        worked_days = WorkedDays(payslip.employee_id.id, worked_days_dict, self.env)
        payslips = Payslips(payslip.employee_id.id, payslip, self.env)
        rules = BrowsableObject(payslip.employee_id.id, rules_dict, self.env)
        porcentaje_fondo_reserva = FondoReserva(payslip.employee_id.id, fondo_rese, self.env)

        baselocaldict = {'categories': categories, 'rules': rules, 'payslip': payslips, 'worked_days': worked_days, 'inputs': inputs,'porcentaje_fondo_reserva':porcentaje_fondo_reserva}
        #get the ids of the structures on the contracts and their parent id as well
        contracts = self.env['hr.contract'].browse(contract_ids)




        if self.payslip_run_id.type_slip_pay=='slip' or self.env.context.get('liquidation', False) or slip_individual:
            if self.env.context.get('liquidation', False):
                structure_ids = contracts.with_context(structure_type=contracts.struct_id.id).get_all_structures()
            else:
                structure_ids = contracts.with_context(structure_type=self.payslip_run_id.structure_type_id.id if not slip_individual else slip_individual).get_all_structures()
        if self.payslip_run_id.type_slip_pay=='holiday':
            #Debe cargar estructura Salarial para vacaciones
            structure_ids=self.env['hr.request.vacations'].get_conf_structure_vacations()
            if not structure_ids:
                raise UserError(_(u'No existe estructura salarial de Vacaciones configurada') )
            structure_ids=structure_ids.ids
        if self.payslip_run_id.type_slip_pay=='thirteenth':
            structure_ids=self.get_conf_structure_thirteenth()
            if not structure_ids:
                raise UserError(_(u'No existe estructura salarial de Décimo Tercero Sueldo para Pago') )
            structure_ids=structure_ids.ids

        if self.payslip_run_id.type_slip_pay=='fourteenth':
            structure_ids=self.get_conf_structure_fourteenth()
            if not structure_ids:
                raise UserError(_(u'No existe estructura salarial de Décimo Cuarto Sueldo para Pago') )
            structure_ids=structure_ids.ids


            #Debe cargar estructura Salarial para Subsidios


        #get the rules of the structure and thier children
        rule_ids = self.env['hr.payroll.structure'].browse(structure_ids).get_all_rules()
        rule_ids.extend([(r.id, r.sequence_order)for r in contracts.mapped('salary_rule_ids')])
        #run the rules by sequence
        sorted_rule_ids = [id for id, sequence_order in sorted(rule_ids, key=lambda x:x[1])]
        sorted_rules = self.env['hr.salary.rule'].browse(sorted_rule_ids)
        transaction_data = []

        for contract in contracts:
            employee = contract.employee_id
            transactions = transaction_model.search([
                ('employee_id', '=', payslip.employee_id.id),
                ('date', '>=', payslip.date_from),
                ('date', '<=', payslip.date_to),
                ('processed', '=', False),
            ])
            localdict = dict(baselocaldict, employee=employee, contract=contract)
            localdict.update(self.env.context.get('external_context', {}))
            localdict.update({
                'sbu_actual': company.get_sbu(payslip.date_to),
                'salida_nomina_actual': False,
                'total_ausencia': 0.0,
            })


            if self.payslip_run_id.type_slip_pay=='slip' or self.env.context.get('liquidation', False) or slip_individual:
                for transaction in transactions:
                    sign =transaction.category_transaction_id.rule_related_id.category_id.type == 'input' and 1.0 or -1.0
                    line_data = {
                        'salary_rule_id': transaction.rule_id.id ,
                        # 'transaction_id': transaction.id,
                        'contract_id': contract_ids[0],
                        'name': transaction.name,
                        'code': transaction.rule_id.code,
                        'category_id': transaction.category_id.id,
                        'sequence': transaction.rule_id.sequence,
                        'appears_on_payslip': True,
                        'amount_select': 'fix',
                        'amount_fix': transaction.amount_pending,
                        'amount': transaction.amount_pending * sign,
                        'employee_id': payslip.employee_id.id,
                        'quantity': 1.0,
                        'rate': 100.0,
                    }
                    _sum_salary_rule_category(localdict, transaction.category_id, transaction.amount)
                    transaction_data.append(line_data)
            # import pdb
            # pdb.set_trace()
            for rule in sorted_rules:
                key = rule.code + '-' + str(contract.id)
                localdict['result'] = None
                localdict['result_qty'] = 1.0
                localdict['result_rate'] = 100
                #check if the rule can be applied
                if rule.satisfy_condition(localdict) and rule.id not in blacklist:
                    #compute the amount of the rule
                    amount, qty, rate = rule.compute_rule(localdict)
                    sign = rule.category_id.type == 'input' and 1.0 or -1.0
                    amount = amount * sign
                    #check if there is already a rule computed with that code
                    previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                    #set/overwrite the amount computed for this rule in the localdict
                    tot_rule = round((amount * qty * rate / 100.0) + 0.0001, 2)
                    localdict[rule.code] = tot_rule
                    rules_dict[rule.code] = rule
                    #sum the amount for its salary category
                    localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount)
                    #create/overwrite the rule in the temporary results
                    if amount!=0: #ESTA CONDICION SE PUSO POR CEN, NO QUIEREN LOS VALORES EN CERO
                        result_dict[key] = {
                            'salary_rule_id': rule.id,
                            'contract_id': contract.id,
                            'name': rule.name,
                            'code': rule.code,
                            'category_id': rule.category_id.id,
                            'sequence': rule.sequence,
                            'appears_on_payslip': rule.appears_on_payslip,
                            'amount_select': rule.amount_select,
                            'amount_fix': rule.amount_fix,
                            'partner_id': rule.partner_id.id,
                            'amount': amount,
                            'employee_id': contract.employee_id.id,
                            'quantity': qty,
                            'rate': rate,
                        }
                else:
                    #blacklist this rule and its children
                    blacklist += [id for id, seq in rule._recursive_search_of_rules()]

        # import pdb
        # pdb.set_trace()
        res = [value for code, value in result_dict.items()]



        # return res + transaction_data
        return sorted(res+transaction_data, key=lambda k: k['sequence'])



    @api.depends('line_ids',)
    def _calculate(self):
        for sline in self:
            inputs_ids = None
            outputs_ids = None
            other_inputs_ids = None
            company_contributions = None
            outputs= 0.0
            inputs= 0.0
            total_inputs= 0.0
            other_inputs= 0.0
            other_inputsn= 0.0
            company_contributions= 0.0
            payslip_net= 0.0
            payslip_undiscount = 0.0

            for line in sline.line_ids:
                salary_rule_id = line.salary_rule_id and line.salary_rule_id or None
                category_transaction_id = line.transaction_id and line.transaction_id.category_transaction_id and line.transaction_id.category_transaction_id or None
                rule = salary_rule_id or category_transaction_id
                #Se calcula todos los ingresos que recibe el empleado directo a su rol de pagos
                if rule.category_id.type == 'input' and not rule.pay_to_other:
                    total_inputs += line.total
                elif rule.category_id.type == 'output':
                    outputs += line.total
                if rule.category_id.code == "INGR":
                    inputs += line.total
                elif rule.category_id.code == "OINGR":
                    other_inputs += line.total
                elif rule.category_id.code == "OINGRN":
                    other_inputsn += line.total
                elif rule.category_id.code == "CONT":
                    company_contributions += line.total
            payslip_net = inputs + other_inputs + other_inputsn + outputs
            payslip_undiscount = inputs + other_inputs + outputs
            if payslip_net < 0:
                payslip_net = 0
            # if payslip_undiscount < 0 and other_inputsn > 0:
            #     payslip_net = other_inputsn

            if payslip_undiscount >= 0.0:
                payslip_undiscount = 0.0

            sline.outputs = outputs
            sline.inputs = inputs
            sline.other_inputs = other_inputs
            sline.other_inputsn = other_inputsn
            sline.company_contributions = company_contributions
            sline.payslip_net = payslip_net
            sline.payslip_undiscount = payslip_undiscount

    outputs = fields.Float(u'Egresos', compute="_calculate")
    inputs = fields.Float(u'Ingresos', compute="_calculate")
    other_inputs = fields.Float(u'Otros Ingresos', compute="_calculate")
    other_inputsn = fields.Float(u'Ingresos no Descontables', compute="_calculate")
    company_contributions = fields.Float(u'Contribuciones Adicionales', compute="_calculate")
    payslip_net = fields.Float(u'Pago Neto', compute="_calculate")
    payslip_undiscount = fields.Float(u'Valores no Descontados', compute="_calculate")


    def get_account_data(self):
        # import pdb
        res = []
        precision = self.env['decimal.precision'].precision_get('Payroll')
        account_model = self.env['account.account']

        acc_id=self.env.user.company_id.expense_account_id.id

        debit_amount=0.0
        credit_amount=0.0

        for slip in self:
            line_ids = []
            date = slip.date or slip.date_to

            for line in slip.line_ids:
                amount = line.total
                if float_is_zero(amount, precision_digits=precision):
                    continue
                salary_rule_id = line.salary_rule_id and line.salary_rule_id or None
                category_transaction_id = line.transaction_id and line.transaction_id.category_transaction_id and line.transaction_id.category_transaction_id or None
                rule = salary_rule_id or category_transaction_id
                debit_account_id = slip.contract_id.struct_id.get_account(rule.account_debit.id)
                credit_account_id = slip.contract_id.struct_id.get_account(rule.account_credit.id)
                if rule.account_payslip:
                    if rule.account_payslip == 'credit':
                        debit_account_id = None
                    else:
                        credit_account_id = None
                name_rule = salary_rule_id and u'Regla Salarial' or u'Categoría de Transacción Programada'

                if (not debit_account_id and not rule.no_account) and (not credit_account_id and not rule.no_account):
                    raise UserError(_(u'La %s %s no tiene configurada la cuenta contable de débito') % (rule.name, name_rule))
                # if not credit_account_id and not rule.no_account:
                #     raise UserError(_(u'La %s %s no tiene configurada la cuenta contable de crédito') % (rule.name, name_rule))
                partner_id = line._get_partner_id(credit_account=False)
                analytic_account_id = slip.contract_id.analytic_account_id.id
                if not analytic_account_id:
                    analytic_account_id = rule.analytic_account_id.id
                tax_code_id = rule.tax_code_id.id
                date_maturity = date

                if rule.no_account:
                    continue
                if rule.pay_to_other:
                    partner_id = rule.partner_id and rule.partner_id.id or None
                # distribution = slip.contract_id.distribution_id
                dp_model = self.env['decimal.precision']
                d = dp_model.search([('name','=','Account')])
                digits = d and d.digits or 2
                if debit_account_id:
                    account = account_model.browse(debit_account_id)
                    new_partner_id = partner_id
                    if account.code.find('5', 0, 1) >= 0:
                        new_partner_id = line._get_partner_id(credit_account=False)
                    debit_line = {
                        'name': line.name,
                        'partner_id': new_partner_id,
                        'account_id': debit_account_id,
                        'journal_id': slip.journal_id.id,
                        'date': date,
                        'date_maturity': date_maturity,
                        'debit': amount > 0.0 and amount or 0.0,
                        'credit': amount < 0.0 and -amount or 0.0,
                        'analytic_account_id': analytic_account_id,
                        'rule': rule,
                        # 'force_base_code_id': False,
                        # 'force_tax_code_id': False,
                        # 'force_base_amount': 0.0,
                        # 'force_tax_amount': 0.0,
                    }
                    # if rule.category_code in ('INGR', 'OINGR', 'OINGRN', 'CONT') and tax_code_id:
                    #     debit_line.update({
                    #         # 'force_base_code_id': tax_code_id,
                    #         'force_base_amount': abs(amount),
                    #         })
                    # if rule.category_code in ('EGRE','OEGR') and tax_code_id:
                    #     debit_line.update({
                    #         'force_tax_code_id': tax_code_id,
                    #         'force_tax_amount': abs(amount),
                    #         })



                    line_ids.append(debit_line)
                    debit_amount+=amount > 0.0 and amount or 0.0

                if credit_account_id:
                    account = account_model.browse(credit_account_id)
                    new_partner_id = partner_id
                    if account.code.find('5', 0, 1) >= 0:
                        new_partner_id = line._get_partner_id(credit_account=False)
                    credit_line = {
                        'name': line.name,
                        'partner_id': new_partner_id,
                        'account_id': credit_account_id,
                        'journal_id': slip.journal_id.id,
                        'date': date,
                        'date_maturity': date_maturity,
                        'debit': amount < 0.0 and -amount or 0.0,
                        'credit': amount > 0.0 and amount or 0.0,
                        'analytic_account_id': analytic_account_id,
                        'rule': rule,
                        # 'force_base_code_id': False,
                        # 'force_tax_code_id': False,
                        # 'force_base_amount': 0.0,
                        # 'force_tax_amount': 0.0,
                    }


                    line_ids.append(credit_line)

                    credit_amount+=amount > 0.0 and amount or 0.0
                    # pdb.set_trace()
            if float_compare(credit_amount , debit_amount,precision_digits=precision)==-1:


                # acc_id=slip.journal_id.default_debit_account_id.id

                adjust_line= {
                    'name':  'Diferencia redondeo',
                    'account_id': acc_id,
                    'journal_id': slip.journal_id.id,
                    'date': date,
                    'partner_id': False,
                    'debit': 0.0,
                    'credit': debit_amount - credit_amount,
                    # 'force_base_code_id': False,
                    # 'force_tax_code_id': False,
                    # 'force_base_amount': 0.0,
                    # 'force_tax_amount': 0.0,

                }


                line_ids.append(adjust_line)


            if float_compare(debit_amount ,credit_amount ,precision_digits=precision)==-1:


                # acc_id=slip.journal_id.default_debit_account_id.id

                adjust_line= {
                    'name':  'Diferencia redondeo',
                    'account_id': acc_id,
                    'journal_id': slip.journal_id.id,
                    'date': date,
                    'partner_id': False,
                    'debit': credit_amount - debit_amount,
                    'credit': 0.0,
                    # 'force_base_code_id': False,
                    # 'force_tax_code_id': False,
                    # 'force_base_amount': 0.0,
                    # 'force_tax_amount': 0.0,

                }


                line_ids.append(adjust_line)

            res += line_ids


            debit_amount=0.0
            credit_amount=0.0

        return res

    basic_salary = fields.Float(string='Basic Salary', compute='_compute_basic_salary', store=True, precompute=True)

    def _compute_basic_salary(self):
        for payslip in self:
            payslip.basic_salary = payslip.contract_id.wage
    #     for payslip in self:
    #         # Calcula el salario básico como antes
    #         work100_line = payslip.worked_days_line_ids.filtered(lambda l: l.code == 'WORK100')
    #         horas = work100_line.number_of_hours if work100_line else 0
    #         if payslip.contract_id.type_day == 'partial':
    #             basic_salary = (payslip.contract_id.value_for_parcial * horas) / payslip.contract_id.contracted_hours
    #         else:
    #             if payslip.days_worked == 30:
    #                 basic_salary = payslip.days_worked == 30 and payslip.contract_id.wage or (payslip.days_worked * payslip.contract_id.daily_value)
    #             else:
    #                 basic_salary = ((payslip.contract_id.wage / 30) / payslip.contract_id.resource_calendar_id.hours_per_day) * horas
    #         payslip.basic_salary = basic_salary

    def compute_sheet(self):
        # self._compute_basic_salary()
        super(hr_payslip, self).compute_sheet()


    # def compute_sheet(self):
    #     for payslip in self:
    #         payslip.onchange_employee()
    #         number = payslip.number or self.env['ir.sequence'].next_by_code('salary.slip')
    #         if not self.env.context.get('no_unlink_lines'):
    #             #delete old payslip lines
    #             payslip.line_ids.unlink()
    #             # set the list of contract for which the rules have to be applied
    #             # if we don't give the contract, then the rules to apply should be for all current contracts of the employee
    #             contract_ids = payslip.contract_id.ids or \
    #                            self.get_contract(payslip.employee_id, payslip.date_from, payslip.date_to)
    #
    #             structure=None
    #
    #             if self.payslip_run_id:
    #                 structure=self.payslip_run_id.structure_type_id
    #                 contract_ids = self.env['hr.contract'].browse(contract_ids).filtered(lambda x: x.structure_type_id.id==structure.id).ids
    #             else:
    #
    #                 structure=self.struct_id
    #                 contract_ids = self.env['hr.contract'].browse(contract_ids).filtered(lambda x: x.struct_id.id==structure.id).ids
    #
    #             # import pdb
    #             # pdb.set_trace()
    #
    #             # if self.payslip_run_id:
    #             #     if self.payslip_run_id.type_slip_pay=='thirteenth':
    #             #         contract_ids=self.env['hr.contract'].browse(contract_ids).filtered(lambda x: x.thirteenth_payment=='accumulated' and x.structure_type_id.id==self.payslip_run_id.structure_type_id.id).ids
    #             #     if self.payslip_run_id.type_slip_pay=='fourteenth':
    #             #         contract_ids=self.env['hr.contract'].browse(contract_ids).filtered(lambda x: x.fourteenth_payment=='accumulated' and x.structure_type_id.id==self.payslip_run_id.structure_type_id.id).ids
    #
    #
    #             lines = sorted([(0, 0, line) for line in self.get_payslip_lines(contract_ids, payslip)], key=lambda k: k[2]['sequence'])
    #
    #             month=payslip.date_from.month
    #             year=payslip.date_from.year
    #
    #             payslip.write({'line_ids': lines, 'number': number,'note_roll':payslip._get_note(),'period_rol':MONTHS[str(month)]+ ' / '+str(year)})
    #         else:
    #             payslip.write({'number': number})
    #     return True


    # def action_payslip_done(self):
    #     self.with_context(no_unlink_lines=True).compute_sheet()
    #     return self.write({'state': 'done'})


    # def action_payslip_cancel(self):
    #     for slip in self:
    #         for payment in slip.payment_ids:
    #             payment.cancel()
    #     return self.write({'state': 'cancel'})


    def print_slip(self):
        return self.env.ref('ec_payroll.payslip_rol_report').report_action(self, config=False)

    pay_with_check = fields.Boolean(string=u'Pagar con Cheque', readonly=True,
                                    states={'draft': [('readonly', False)]},)

    @api.onchange('employee_id', 'date_from')
    def onchange_employee(self):
        if self.employee_id:
            if not self.employee_id.bank_account_id:
                self.pay_with_check = True
            else:
                self.pay_with_check = self.employee_id.pay_with_check
        # return super(hr_payslip, self)._onchange_employee()




    @api.constrains(
        'date_from',
        'date_to',
        'payslip_run_id',
        'type_slip_pay'
    )
    def _check_dates_slip(self):
        for sline in self:
            if sline.payslip_run_id:
                if sline.payslip_run_id.date_start != sline.date_from:
                    raise ValidationError(_("Las fechas de la nómina %s (Desde: %s) no coinciden con la fecha del procesamiento de nómina %s (Desde: %s) por favor verifique") % (sline.display_name, sline.date_from, sline.payslip_run_id.display_name, sline.payslip_run_id.date_start))
                if sline.payslip_run_id.date_end != sline.date_to:
                    raise ValidationError(_("Las fechas de la nómina %s (Hasta: %s) no coinciden con la fecha del procesamiento de nómina %s (Hasta: %s) por favor verifique") % (sline.display_name, sline.date_to, sline.payslip_run_id.display_name, sline.payslip_run_id.date_end))


            employee = sline.employee_id and sline.employee_id or None
            date_from = sline.date_from and sline.date_from or None
            date_to = sline.date_to and sline.date_to or None
            type_slip_pay = sline.type_slip_pay or None

            # if fields.Datetime.from_string(date_from).month != fields.Datetime.from_string(date_to).month or fields.Datetime.from_string(date_from).year != fields.Datetime.from_string(date_to).year:
            #     raise ValidationError(_(u'La fechas de la nómina %s debe estar dentro del mismo mes del año'))

            list_payslip = sline.browse()
            search_criteria = [('id','!=', sline.id),
                               ('employee_id','=', employee.id),
                               ('state', '!=', 'cancel'),
                               ]
            #Verificar si existe otra nomina en el mismo periodo de tiempo de otro payslip
            #      |----|
            #      .
            #    |----|
            list_payslip |= sline.search(search_criteria + [
                ('date_from','>=',date_from),
                ('date_from','<=',date_to),
                ('type_slip_pay', '=',type_slip_pay ),
            ])

            # |----|
            #      .
            #    |----|
            list_payslip |= sline.search(search_criteria + [
                ('date_to','>=',date_from),
                ('date_to','<=',date_to),
                ('type_slip_pay', '=',type_slip_pay ),
            ])
            # |---------|
            #
            #    |----|
            list_payslip |= sline.search(search_criteria + [
                ('date_from','<=',date_from),
                ('date_to','>=',date_to),
                ('type_slip_pay', '=',type_slip_pay ),
            ])
            #    |----|
            #
            #    |----|
            list_payslip |= sline.search(search_criteria + [
                ('date_to','=',date_from),
                ('date_to','=',date_to),
                ('type_slip_pay', '=',type_slip_pay ),
            ])

    @api.depends(
        'date_from',
        'date_to',
        'worked_days_line_ids',
        'contract_id',
        'contract_id.date_end',
    )
    def _get_type_slip(self):
        for sline in self:
            dline_model = sline.env['hr.payslip.worked_days']
            type_slip = 'fortnight'
            date_from = fields.Datetime.from_string(sline.date_from)
            date_to = fields.Datetime.from_string(sline.date_to)
            start_month = max(date_from, date_to) + relativedelta(day=1)
            end_month = max(date_from, date_to) + relativedelta(months=1, day=1, days=-1)
            delta = 0
            if end_month.day == 31:
                delta = -1
            elif end_month.day == 28:
                delta = 2
            elif end_month.day == 29:
                delta = 1
            if date_to.day == end_month.day:
                type_slip = 'end_month'
            if sline.contract_id:
                if sline.contract_id.date_end:
                    if sline.contract_id.date_end <= sline.date_to:
                        type_slip = 'end_month'
            sline.type_slip = type_slip
            days_worked = 0
            if 'end_month':
                slips = sline.search([
                    ('employee_id', '=', sline.employee_id.id),
                    ('date_from', '>=', start_month.strftime(DF)),
                    ('date_to', '<=', end_month.strftime(DF)),
                ])
                slips |= sline
                wlines = dline_model.browse()
                for slip in slips:
                    for wday in slip.worked_days_line_ids:
                        if isinstance(sline.id, models.NewId):
                            if wday.code == 'WORK100' and isinstance(wday.id, models.NewId):
                                wlines |= wday
                        else:
                            if wday.code == 'WORK100':
                                wlines |= wday
                days_worked = sum([w.number_of_days for w in wlines])
            else:
                days_worked = sum([w.number_of_days for w in sline.worked_days_line_ids])
            if end_month.month == 2 and days_worked in ('28', '29'):
                days_worked = 30
            if days_worked > 30:
                days_worked = 30
            sline.days_worked = days_worked

    type_slip = fields.Selection(selection=[
        ('fortnight', 'Anticipo de Quincena'),
        ('end_month', 'Fín de Mes'),
    ], string='Período de Nómina',
        store=True, compute='_get_type_slip', help=u"")
    days_worked = fields.Integer(string='Dias Trabajados',
                                 store=True, compute='_get_type_slip', help=u"")


    @api.depends(
        'date_from',
        'date_to',
        'employee_id.asumir_antiguedad',
        'contract_id',
        'contract_id.date_end',
    )
    def _get_continuidad_fondos_reserva(self):
        for sline in self:
            contract_model = sline.env['hr.contract']
            continuidad_fondos_reserva = sline.employee_id.asumir_antiguedad
            now = datetime.now()
            #FIXME: deberia ser una propiedad de la compania?
            days_to_pay = 365
            dias_acumulados = 0
            if not continuidad_fondos_reserva:
                contracts = contract_model.with_context(active_test=False).search([
                    ('employee_id', '=', sline.employee_id.id),
                    ('date_start', '<=', sline.date_to),
                ])
                for contract in contracts:
                    data_from = fields.Datetime.from_string(contract.date_start)
                    date_to = contract.date_end or sline.date_to
                    date_to = fields.Datetime.from_string(date_to) + relativedelta(day=1)
                    dias_acumulados += (date_to - data_from).days

            if dias_acumulados >= days_to_pay:
                continuidad_fondos_reserva = True
            sline.continuidad_fondos_reserva = continuidad_fondos_reserva

    continuidad_fondos_reserva = fields.Boolean(string='Continuidad Fondos de Reserva',
                                                 store=True, compute='_get_continuidad_fondos_reserva', help=u"")


    @api.model
    def get_contract(self, employee, date_from, date_to):
        """
        @param employee: recordset of employee
        @param date_from: date field
        @param date_to: date field
        @return: returns the ids of all the contracts for the given employee that need to be considered for the given dates
        """
        # if self.env.context.get('all_contracts', False):
        # a contract is valid if it ends between the given dates
        clause_1 = ['&', ('date_end', '<=', date_to), ('date_end', '>=', date_from)]
        # OR if it starts between the given dates
        clause_2 = ['&', ('date_start', '<=', date_to), ('date_start', '>=', date_from)]
        # OR if it starts before the date_from and finish after the date_end (or never finish)
        clause_3 = ['&', ('date_start', '<=', date_from), '|', ('date_end', '=', False), ('date_end', '>=', date_to)]
        clause_final = [('employee_id', '=', employee.id), ('state', 'in', ('open', 'pending', 'close')), '|', '|'] + clause_1 + clause_2 + clause_3

        return self.env['hr.contract'].search(clause_final).ids
        # return super(hr_payslip, self).get_contract(employee, date_from, date_to)


class hr_payslip_line(models.Model):

    _inherit = 'hr.payslip.line'

    # _order = 'slip_id,sequence asc,date_from'

    _rec_name = 'name'

    transaction_id = fields.Many2one('hr.scheduled.transaction', string=u'Transacción Programada', ondelete="restrict")
    # category_transaction_id = fields.Many2one('hr.scheduled.transaction.category', string=u'Rubro Programado',
    #                                           related="transaction_id.category_transaction_id", store=True)
    salary_rule_id = fields.Many2one('hr.salary.rule', string='Rule', required=False, ondelete="restrict")

    date_from = fields.Date(string='Date From', related='slip_id.date_from', store=True)
    date_to = fields.Date(string='Date To', related='slip_id.date_to', store=True)

    analytic_account_id = fields.Many2one(string=u'Cuenta Analítica' , related="slip_id.analytic_account_id", store=True)

    department_id = fields.Many2one(string=u'Departamento' , related="contract_id.department_id", store=True, readonly=True)

    def _get_partner_id(self, credit_account):
        partner_id = self.slip_id.employee_id.address_id and self.slip_id.employee_id.address_id.id or None
        if not partner_id:
            raise UserError(_(u'Debe configurar la Dirección Particular / Empresa relacionada al empleado %s %s') % (self.slip_id.employee_id.identification_id, self.slip_id.employee_id.name))
        return partner_id

    # @api.model
    # @tools.ormcache("self")
    # def _get_item_names(self):
    #     rules_model = self.env['hr.salary.rule']
    #     tcategory_model = self.env['hr.scheduled.transaction.category']
    #     util_model = self.env['ecua.utils']
    #     res = [(util_model.get_xml_for_report(r), r.display_name) for r in rules_model.search([])]
    #     res += [(util_model.get_xml_for_report(r), r.display_name) for r in tcategory_model.search([])]
    #     return res

    # @api.depends('salary_rule_id', 'transaction_id',)
    # def _get_item_name(self):
    #     # import pdb
    #     # pdb.set_trace()
    #
    #     util_model = self.env['ecua.utils']
    #
    #     for line in self:
    #         if line.salary_rule_id:
    #             line.nombre_rubro = util_model.get_xml_for_report(line.salary_rule_id)
    #         if line.transaction_id:
    #
    #             line.nombre_rubro = util_model.get_xml_for_report(line.transaction_id.category_transaction_id)
    #
    # nombre_rubro = fields.Selection(selection="_get_item_names",
    #                                 string='Nombre Rubro', compute="_get_item_name", store=True)

    liquidation_line_ids = fields.Many2many('hr.liquidation.provision.line', 'liquidation_line_payslip_line_rel',
                                            'payslip_line_id', 'liquidation_line_id', string=u'Líneas de Liquidación', states={}, help=u"")


    # @api.depends(
    #     'liquidation_line_ids',
    #     'liquidation_line_ids.liquidation_id.state',
    # )
    # def _get_provision_liquidated(self):
    #     self.provision_liquidated = len([l for l in self.liquidation_line_ids if l.liquidation_id.state in ('open', 'done')]) > 0
    # provision_liquidated = fields.Boolean(string=u'Provision Liquidada', store=True,
    #                                      compute='_get_provision_liquidated', help=u"")


    # @api.depends(
    #     'liquidation_line_ids',
    #     'liquidation_line_ids.liquidation_id.state',
    # )
    # def _get_provision_thirteenth(self):
    #     date_max=None
    #     obj=self.env['hr.payslip'].search([('type_slip_pay','=','thirteenth'),('employee_id','=',self.employee_id.id)]).filtered(lambda x: x.state=='done')
    #     for line in self:
    #         # struct=self.env['hr.payslip'].get_conf_structure_thirteenth()
    #
    #         if obj:
    #             date_max = max(obj.mapped('date_from'))
    #             line.provision_pay_from_thirteenth = True if line.date_from < date_max else False
    #         else:
    #             line.provision_pay_from_thirteenth = False
    #
    # provision_pay_from_thirteenth = fields.Boolean(string=u'Provision Pagada en Décimo Tercer Sueldo', store=True,
    #                                                compute ='_get_provision_thirteenth', help=u"")


    # @api.depends(
    #     'liquidation_line_ids',
    #     'liquidation_line_ids.liquidation_id.state',
    # )
    # def _get_provision_fourteenth(self):
    #
    #     date_max=None
    #     obj=self.env['hr.payslip'].search([('type_slip_pay','=','fourteenth'),('employee_id','=',self.employee_id.id)]).filtered(lambda x: x.state=='done')
    #     for line in self:
    #         if obj:
    #             date_max = max(obj.mapped('date_from'))
    #             line.provision_pay_from_fourteenth = True if line.date_from < date_max else False
    #         else:
    #             line.provision_pay_from_fourteenth=False
    #
    # provision_pay_from_fourteenth = fields.Boolean(string=u'Provision Pagada en Décimo Cuarto Sueldo', store=True,
    #                                                compute ='_get_provision_fourteenth', help=u"")


    # @api.depends(
    #     'liquidation_line_ids',
    #     'liquidation_line_ids.liquidation_id.state',
    # )
    # def _get_vacation_pay(self):
    #
    #     # self.ensure_one()
    #
    #
    #     for line in self:
    #         obj=self.env['hr.request.vacations'].search([('contract_id','=',line.contract_id.id),('payslip_id','=',line.slip_id.id),('state','=','done')])
    #         line.vacations_pay_from = True if obj else False
    #     # self.vacations_pay_from=False
    #
    # vacations_pay_from = fields.Boolean(string=u'Vacaciones Pagadas', store=True,
    #                                     compute ='_get_vacation_pay', help=u"")





    days_worked = fields.Integer(string='Dias Trabajados',
                                 store=True, related='slip_id.days_worked', help=u"")

