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
import datetime
from odoo import tools
from odoo.tools.safe_eval import safe_eval
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import time
from lxml import etree
from functools import partial
import logging
_logger = logging.getLogger(__name__)


class hr_payroll_structure(models.Model):
    _inherit = 'hr.payroll.structure'
    
    active = fields.Boolean(string=u'Activo?', readonly=False, help=u"", default=True)

    def _get_parent_structure(self):
        parent = self.mapped('parent_id')
        if parent:
            parent = parent._get_parent_structure()
        return parent + self

    def get_all_rules(self):
        """
        @return: returns a list of tuple (id, sequence) of rules that are maybe to apply
        """
        all_rules = []
        return [(rule.id, rule.sequence_order) for rule in self.rule_ids]


class hr_salary_rule_category(models.Model):
    _inherit = 'hr.salary.rule.category'
    
    active = fields.Boolean(string=u'Activo?', readonly=False, help=u"", default=True)
    type = fields.Selection([
        ('input', 'Ingreso'),
        ('output', 'Egreso'),
        ], string='Tipo',
        readonly=False, required=False, help=u"")


class hr_salary_rule_percentage_base(models.Model):
    _name = 'hr.salary.rule.percentage.base'
    
    name = fields.Char(string=u'Nombre', index=True, 
                       required=True, readonly=False, help=u"")
    base = fields.Char(string=u'Código Python', index=True, 
                       required=True, readonly=False, help=u"")


class hr_salary_rule(models.Model):
    _inherit = 'hr.salary.rule'

    # tax_code_id = fields.Many2one('account.tax.code', u'Código de Impuesto')
    active = fields.Boolean(string=u'Activo?', readonly=False, help=u"", default=True)
    percentage_id = fields.Many2one('hr.salary.rule.percentage.base', string=u'Porcentaje Basado en', 
                                    required=False, readonly=False, help=u"", ondelete="restrict")
    amount_percentage_base = fields.Char(string=u'Percentage based on', index=True, related="percentage_id.base",
                                         required=False, readonly=True, help=u"")
    partner_id = fields.Many2one('res.partner', string=u'Empresa Asociada', 
                                 required=False, readonly=False, help=u"", ondelete="restrict")
    category_code = fields.Char(string=u'Codigo Categoria', index=True, 
                                related="category_id.code", store=True)
    # account_payslip = fields.Selection([('credit', 'Acreedora'),
    #                                     ('debit', 'Deudora')], string='Cuenta en nómina',
    #                                    help="En la nómina solo considerara la cuenta seleccionada")
    pay_to_other = fields.Boolean(string=u'Asignar Empresa', readonly=False, help=u"Use esta opción cuando el movimiento contable debe asignarse la empresa asociada a la regla")
    set_date_maturity_region = fields.Boolean(string=u'Asignar Fecha de Vencimiento', readonly=False, help=u"Si esta opción esta activa, se asignará segun la región asignada en el contrato al empleado la fecha de vencimiento, particularmente para los décimos")
    # no_account = fields.Boolean(string=u'No generar Contabilidad', readonly=False, help=u"")
    # group_move = fields.Boolean(string=u'Agrupar Asiento Contable', readonly=False, help=u"Por defecto el sistema detalla cada asiento por cada empleado, con esta opción activa")
    
    def _recursive_search_of_rules(self):
        """
        @return: returns a list of tuple (id, sequence) which are all the children of the passed rule_ids
        """
        return [(rule.id, rule.sequence_order) for rule in self]

    @api.model
    def get_employee_age(self, employee):
        age = 0
        if employee:
            today = datetime.datetime.today()
            total_years = 0       
            if employee.birthday:
                dob = employee.birthday
                total_years = today.year - dob.year
            age = total_years
        return age

    def compute_rule(self, localdict):
        if not localdict: localdict = {}
        localdict.update({
            # 'rdatetime': datetime,
            # 'datetime': datetime,
            'timedelta': timedelta,
            'relativedelta': relativedelta,
            })
        """
        :param localdict: dictionary containing the environement in which to compute the rule
        :return: returns a tuple build as the base/amount computed, the quantity and the rate
        :rtype: (float, float, float)
        """
        self.ensure_one()
        # util_model = self.env['ecua.utils']
        irenta_model = self.env['hr.impuesto.renta.referencia']
        if not localdict: localdict = {}
        localdict.update({
            'get_monto_retencion_mes': irenta_model.get_monto_retencion_mes,
            'get_employee_age': self.get_employee_age,
            })
        if self.amount_select == 'fix':
            try:
                return self.amount_fix, float(safe_eval(self.quantity, localdict)), 100.0
            except:
                raise UserError(_('Wrong quantity defined for salary rule %s (%s).') % (self.name, self.code))
        elif self.amount_select == 'percentage':
            try:
                return (float(safe_eval(self.amount_percentage_base, localdict)),
                        float(safe_eval(self.quantity, localdict)),
                        self.amount_percentage)
            except:
                raise UserError(_('Wrong percentage base or quantity defined for salary rule %s (%s).') % (self.name, self.code))
        else:
            try:
                safe_eval(self.amount_python_compute, localdict, mode='exec', nocopy=True)
                return float(localdict['result']), 'result_qty' in localdict and localdict['result_qty'] or 1.0, 'result_rate' in localdict and localdict['result_rate'] or 100.0
            except Exception as e:
                error = 'error'
                raise UserError(_('Wrong python code defined for salary rule %s (%s). Error %s') % (self.name, self.code, error))

    def satisfy_condition(self, localdict):
        """
        @param contract_id: id of hr.contract to be tested
        @return: returns True if the given rule match the condition for the given contract. Return False otherwise.
        """
        self.ensure_one()
        # util_model = self.env['ecua.utils']
        irenta_model = self.env['hr.impuesto.renta.referencia']
        if not localdict: localdict = {}
        localdict.update({
            'get_monto_retencion_mes': irenta_model.get_monto_retencion_mes,
            'get_employee_age': self.get_employee_age,
            })
        if self.condition_select == 'none':
            return True
        elif self.condition_select == 'range':
            try:
                result = safe_eval(self.condition_range, localdict)
                return self.condition_range_min <= result and result <= self.condition_range_max or False
            except:
                raise UserError(_('Wrong range condition defined for salary rule %s (%s).') % (self.name, self.code))
        else:  # python code
            try:
                safe_eval(self.condition_python, localdict, mode='exec', nocopy=True)
                return 'result' in localdict and localdict['result'] or False
            except Exception as e:
                error = 'error'
                raise UserError(_('Wrong python condition defined for salary rule %s (%s), Error: %s.') % (self.name, self.code, error))

    @api.model
    def calculate_basic_salary(self, payslip, contract):
        resultado = 0
        horas = payslip.worked_days.get('WORK100', {}).get('number_of_hours', 0)
        if contract.type_day == 'partial':
            resultado = (contract.value_for_parcial * horas) / contract.contracted_hours
        else:
            resultado = (payslip.days_worked == 30 and contract.wage or (payslip.days_worked * contract.daily_value))

        _logger.info("Horas trabajadas: %s", horas)
        _logger.info("Resultado calculado: %s", resultado)
        return resultado