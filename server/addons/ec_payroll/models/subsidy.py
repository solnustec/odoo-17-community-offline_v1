# -*- coding: utf-8 -*-
from odoo import models, fields, registry, api
from odoo.tools.translate import _
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DTF
from datetime import datetime,date
from dateutil.relativedelta import relativedelta
import time
import logging
from dateutil import rrule
from pytz import timezone, utc
import pytz

_logger = logging.getLogger(__name__)


class hrWorkEntry(models.Model):
	_inherit = 'hr.work.entry'
	request_subsidy_id = fields.Many2one('hr.request.subsidy')


class hrContract(models.Model):
	_inherit = 'hr.contract'

	def create_leaves_entries_values(self, date_start, date_stop, work_entry_type_id, subsidy_id):
		"""
		Generate a work_entries list between date_start and date_stop for one contract.
		:return: list of dictionnary.
		"""
		
		vals_list = []
		for contract in self:
			contract_vals = []
			employee = contract.employee_id
			calendar = contract.resource_calendar_id
			resource = employee.resource_id
			tz = pytz.timezone(calendar.tz)

			attendances = calendar._work_intervals(
				pytz.utc.localize(date_start) if not date_start.tzinfo else date_start,
				pytz.utc.localize(date_stop) if not date_stop.tzinfo else date_stop,
				resource=resource, tz=tz
			)
			# Attendances
			for interval in attendances:
				
				# All benefits generated here are using datetimes converted from the employee's timezone
				contract_vals += [{
					'name': "%s: %s" % (work_entry_type_id.name, employee.name),
					'date_start': interval[0].astimezone(pytz.utc).replace(tzinfo=None),
					'date_stop': interval[1].astimezone(pytz.utc).replace(tzinfo=None),
					'work_entry_type_id': work_entry_type_id.id,
					'employee_id': employee.id,
					'contract_id': contract.id,
					'company_id': contract.company_id.id,
					'state': 'draft',
					'request_subsidy_id': subsidy_id,
				}]

			# # Leaves
			# leaves = self.env['resource.calendar.leaves'].sudo().search([
			#     ('resource_id', 'in', [False, resource.id]),
			#     ('calendar_id', '=', calendar.id),
			#     ('date_from', '<', date_stop),
			#     ('date_to', '>', date_start)
			# ])

			# for leave in leaves:
			#     start = max(leave.date_from, datetime.combine(contract.date_start, datetime.min.time()))
			#     end = min(leave.date_to, datetime.combine(contract.date_end or date.max, datetime.max.time()))
			#     if leave.holiday_id:
			#         work_entry_type = leave.holiday_id.holiday_status_id.work_entry_type_id
			#     else:
			#         work_entry_type = leave.mapped('work_entry_type_id')
			#     contract_vals += [{
			#         'name': "%s%s" % (work_entry_type.name + ": " if work_entry_type else "", employee.name),
			#         'date_start': start,
			#         'date_stop': end,
			#         'work_entry_type_id': work_entry_type.id,
			#         'employee_id': employee.id,
			#         'leave_id': leave.holiday_id and leave.holiday_id.id,
			#         'company_id': contract.company_id.id,
			#         'state': 'draft',
			#         'contract_id': contract.id,
			#     }]

			# If we generate work_entries which exceeds date_start or date_stop, we change boundaries on contract
			if contract_vals:
				date_stop_max = max([x['date_stop'] for x in contract_vals])
				if date_stop_max > contract.date_generated_to:
					contract.date_generated_to = date_stop_max

				date_start_min = min([x['date_start'] for x in contract_vals])
				if date_start_min < contract.date_generated_from:
					contract.date_generated_from = date_start_min

			vals_list += contract_vals

		return vals_list


class hrSubsidy(models.Model):
	_name = "hr.request.subsidy"
	_rec_name = 'number'

	def ics_datetime(self, idate, allday=False):
		if idate:
			if allday:
				return fields.Date.to_date(idate)
			else:
				idate = fields.Datetime.to_datetime(idate)
				return idate.replace(tzinfo=pytz.timezone('UTC'))
		return False

	def get_number(self):
		code = None
		cr = self._cr
		cr.execute('SELECT max(number::int) + 1 FROM hr_request_subsidy')
		results = cr.fetchone()

		if results[0]:
			code = str(results[0]).zfill(6)
		else:
			code = '000001'
		return code
	
	@api.depends('date_start', 'date_end')
	def _get_total_days(self):
		if self.date_start and self.date_end:
			self.days_total_subsidy = self.get_days(self.date_start,self.date_end)

	number = fields.Char(string=u'Código', readonly=True, default=get_number)
	employee_id = fields.Many2one('hr.employee', string=u'Empleado', required=True)
	contract_id = fields.Many2one('hr.contract', string=u'Contrato', readonly=False, compute="_get_contract",)
	date_start_contract = fields.Date(string=u'Fecha Contrato', related="contract_id.date_start", required=True)
	date_trx = fields.Date(string=u"Fecha de Transacción", default=fields.Date.today(), readonly=True)
	state = fields.Selection([('draft', 'Borrador'), ('send', 'Enviado'), ('done', 'Aprobado'), ('pay', 'Pagado')], string=u'Estado', default='draft')
	date_start = fields.Date(string=u'F. Inicio Subsidio', required=True)
	date_end = fields.Date(string=u'F. Fin Subsidio', required=True)
	days_total_subsidy = fields.Float(string=u'Días Totales Subsidio', readonly=True, store=True, compute=_get_total_days)
	type_subsidy = fields.Selection([('maternity', 'Maternidad'), ('disease', 'Enfermedad')], string=u'Tipo de Subsidio',required=True)
	work_entry_ids = fields.One2many('hr.work.entry', 'request_subsidy_id', string=u'Días', required=True)
	date_return = fields.Date(string=u'F. Retorno de Labores', required=True)
	payslip_id = fields.Many2one('hr.payslip')

	@api.depends('employee_id')
	def _get_contract(self):
		self.contract_id = False
		if self.employee_id:
			contract = self.env['hr.contract'].search([('employee_id', '=', self.employee_id.id)])
			self.contract_id = contract[0].id

	@api.onchange('date_start')
	def change_date(self):
		date_end = None
		if self.date_start and self.type_subsidy=='maternity':	
			self.date_end=self.date_start +  relativedelta(days=83) #aqui estaba 84 pero los dias no cuadran xq debe contar el primer dia de la fecha
		
	def get_exists_slip(self):
		if self.payslip_id:
				raise UserError(_(u'Existe una Nómina creada con esta Transacción, verifique') )		
		return False

	def get_conf_work_entry(self):
		if self.env.user.company_id.work_entry_type:
			return self.env.user.company_id.work_entry_type
		else:
			return False
			
	def get_conf_work_entry_type(self):
		if self.type_subsidy == 'maternity':
			if self.env.user.company_id.maternity_entry_type:
				return self.env.user.company_id.maternity_entry_type
			else:
				return False
			
		if self.type_subsidy == 'disease':
			if self.env.user.company_id.disease_entry_type:
				return self.env.user.company_id.disease_entry_type
			else:
				return False

	def get_days(self, date_start, date_end):
		# +  relativedelta(days=1)

		if type(date_start) == str:
			date_start = datetime.strptime(date_start, '%Y-%m-%d').date()
		if type(date_end) == str:
			date_end =datetime.strptime(date_end, '%Y-%m-%d').date()

		days = ((date_end ) - date_start).days + 1

		if days > 84 and self.type_subsidy == 'maternity':
			self.date_end = None
			raise UserError(_(u'El máximo número de días de Maternidad es 84') )
		if days > 180 and self.type_subsidy == 'disease':
			self.date_end = None
			raise UserError(_(u'El máximo número de días de Enfermedad es 180') )
		return days

	@api.onchange('date_start', 'date_end')
	def on_change_date(self):
		if self.date_start and self.date_end:
			self.days_total_subsidy = self.get_days(self.date_start,self.date_end)

	def write(self, vals):
		date_start = vals.get('date_start', self.date_start)
		date_end = vals.get('date_end', self.date_end)
		if date_start and date_end:
			vals['days_total_subsidy'] = self.get_days(date_start, date_end)
		return super(hrSubsidy, self).write(vals)


	# def get_calendar(self):

	# 	start_dt = self.ics_datetime(self.date_start)
	# 	end_dt=self.ics_datetime(self.date_end)
		

	# 	if not start_dt.tzinfo:
	# 		start_dt = start_dt.replace(tzinfo=utc)
	# 	if not end_dt.tzinfo:
	# 		end_dt = end_dt.replace(tzinfo=utc)

	# 	resources=self.contract_id.resource_calendar_id._attendance_intervals(start_dt,end_dt,None)
	# 	idsAttendance=[x[2] for x in resources]


	# 	for line in resources:
	# 		import pdb
	# 		pdb.set_trace()
	# 		rr=0
	# 		ids = self.env['hr.work.entry'].search([('employee_id','=',self.employee_id.id),('date_start','>=',line[2]['date_to']),('date_stop','<=',self.date_end)])

	def generate_work_entries_subsidy(self):
		workEntriesUpdate=[]
		obj_work_entries =self.env['hr.work.entry']

		start_dt = self.ics_datetime(self.date_start)
		end_dt = self.ics_datetime(self.date_end) + relativedelta(days=1)
		
		work_entry_type_id = self.get_conf_work_entry_type() or False 
		if not work_entry_type_id:
			raise UserError(_(u'No existe configuración de Tipos de Entrada de Trabajo.') )

		# import pdb 
		# pdb.set_trace()

		values = []
		itervalues = self.contract_id.create_leaves_entries_values(start_dt,end_dt,work_entry_type_id,self.id)
		# itervalues=values

		#('%Y-%m-%d %H:%M:%S')
		# import pdb
		# pdb.set_trace()

		for line in itervalues:
			work_entries = self.env['hr.work.entry'].search([('employee_id', '=', self.employee_id.id),
				('date_start', '>=', line['date_start'].strftime('%Y-%m-%d %H:%M:%S')), ('date_stop', '<=', line['date_stop'].strftime('%Y-%m-%d %H:%M:%S'))])
			if work_entries:
				for x in work_entries:
					workEntriesUpdate.append(x.id)
				# values.remove(line)
			else:
				values.append(line)

		# import pdb 
		# pdb.set_trace()

		if workEntriesUpdate:
			obj_work_entries.search([('id', 'in', tuple(workEntriesUpdate))]).sudo().write({'work_entry_type_id':work_entry_type_id,'request_subsidy_id':self.id})
		self.env['hr.work.entry'].sudo().create(values)

	# def get_work_entries_values_subsidy(self):
	# 	start_dt = self.ics_datetime(self.date_start)
	# 	end_dt=self.ics_datetime(self.date_end)
		

	# 	if not start_dt.tzinfo:
	# 		start_dt = start_dt.replace(tzinfo=utc)
	# 	if not end_dt.tzinfo:
	# 		end_dt = end_dt.replace(tzinfo=utc)

	# 	import pdb 
	# 	pdb.set_trace()
	# 	values = self.contract_id._get_work_entries_values(start_dt,end_dt)


	# def get_exists_slip(self):

	# 	import pdb 
	# 	pdb.set_trace()

	# 	if self.env['hr.payslip'].search([('employee_id','=', self.employee_id.id),('date_to','>=',self.date_start),('date_from','<=',self.date_start)]):
	# 		raise UserError(_(u'Existe una Nómina Generada') )


	def action_done(self):
		# self.generate_work_entries_subsidy()
		self.state = 'done'

	def action_to_send(self):
		if self.days_total_subsidy == 0:
			raise UserError(_(u'Días de subsidio incorrectos') )
		self.state = 'send'

	def action_draft(self):

		if not self.get_exists_slip():
			self.state = 'draft'

		self.reverse_leaves_work_entry()

	def reverse_leaves_work_entry(self):
		work_entry_type = self.get_conf_work_entry()
		if not work_entry_type:
			raise UserError(_(u'No existe configuración de Tipos de Entrada de Trabajo.') )

		for line in self.env['hr.work.entry'].search([('request_subsidy_id','=',self.id)]):
			line.sudo().write({'work_entry_type_id':work_entry_type})

	def unlink(self):
		if not self.get_exists_slip():
			self.reverse_leaves_work_entry()
			return super(hrSubsidy, self).unlink() 