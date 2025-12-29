# -*- coding: utf-8 -*-
from odoo import models, fields, registry, api
from odoo.tools.translate import _
import unicodedata
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.osv import expression
from odoo.exceptions import AccessError
from lxml import etree
import base64
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class res_partner_bank(models.Model):
    _inherit = 'res.partner.bank'

    def _get_partner(self):
        if self.env.context.get('hr', False):
            return self.env['res.partner'].browse(self.env.context.get('hr', False))
        return None

    partner_id = fields.Many2one('res.partner', 'Account Holder', ondelete='cascade', index=True, domain=['|', ('is_company', '=', True), ('parent_id', '=', False)], required=True, default=_get_partner)

# class SalaryHistory(models.Model):
#     _inherit = 'salary.history'
#     _description = 'Historial Salarial'
#
#     currency_id = fields.Many2one(
#         "res.currency",
#         string="Currency of the Payment Transaction",
#         required=True,
#         default=lambda self: self.env.user.company_id.currency_id,
#     )
#     sueldo = fields.Monetary(string="Sueldo", currency_field="currency_id")
#     cargo_id = fields.Many2one("hr.job", "Cargo")
#     contrato_id = fields.Many2one("hr.contract", "Contrato")


# class ContractHistory(models.Model):
#     _inherit = 'contract.history'
#     _description = 'Historial de Contratos'
#
#     select_Contrato=[
#         ('EVENTUAL', 'EVENTUAL'),
#         ('INDEFINIDO', 'INDEFINIDO'),
#     ]
#
#     select_adendum=[
#         ('SUELDO', 'POR SUELDO'),
#         ('HORARIO', 'POR HORARIO'),
#     ]
#
#     tipo_documento = fields.Selection([('contrato', 'Contrato'), ('adendum', 'Adendum'),],
#                                       string="Tipo de Documento")
#     observacion = fields.Selection(selection=select_adendum+select_Contrato, string='Observación',
#                                    groups="hr.group_hr_user",  tracking=True)
#     contrato_id = fields.Many2one('hr.contract', 'Nuevo Contrato')

    # @api.onchange('observacion')
    # def validar_contrato(self):
    #     for l in self:
    #         l.employee_id=self._context['active_id']
    #         contrato_id = self.env['hr.contract'].search(
    #             [('employee_id', '=', self._context['active_id']), ('state', '=', 'open')], limit=1)
    #         if self.tipo_documento == 'adendum':
    #             if l.observacion in ['SUELDO', 'HORARIO']:
    #                 if contrato_id:
    #                     new_contrato = contrato_id.copy()
    #                     contrato_id.state = 'close'
    #                     self.contrato_id = new_contrato.id
    #                 else:
    #                     raise ValidationError("No cuenta con un contrato activo para realizar el proceso de Adenda.")
    #             else:
    #                 raise UserError("Para el tipo de Documento Adendum como observación puede seleccionar POR SUELDO u HORARIO")
    #         elif self.tipo_documento == 'contrato':
    #             if l.observacion in ['EVENTUAL', 'INDEFINIDO']:
    #                 if contrato_id:
    #                     raise UserError("Mantiene un contrato activo para este colaborador. Por favor realice los procesos respectivos y puede retomar a ingresar este registro.")
    #             else:
    #                 raise UserError("Para el tipo de Documento Contrato como observación puede seleccionar EVENTUAL o INDEFINIDO")


# class WageDetails(models.Model):
#     _inherit = 'hr.contract'

    # @api.onchange('wage')
    # def onchange_wage(self):
    #     vals = {
    #         'employee_id': self.employee_id.id,
    #         'employee_name': self.employee_id,
    #         'updated_date': datetime.today(),
    #         'current_value': self.wage,
    #         'sueldo': self.wage,
    #         'cargo_id': self.job_id.id,
    #         'contrato_id': self.id,
    #
    #     }
    #     self.env['salary.history'].sudo().create(vals)

    # @api.onchange('job_id')
    # def onchange_job_id(self):
    #     employee_id = self.env['hr.employee'].search([('id', '=', self.employee_id.id)])
    #     vals = {
    #         'employee_id': self._origin.id,
    #         'employee_name': employee_id.name,
    #         'updated_date': datetime.today(),
    #         'changed_field': 'Posición',
    #         'current_value': self.job_id.name,
    #         'departamento_id': self.department_id.id,
    #         'cargo_id': self.job_id.id,
    #         'area_id': self.department_id.parent_id.id,
    #     }
    #     self.env['department.history'].sudo().create(vals)



class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    id_employeed_old = fields.Char(string=u'Id base antigua', required=False)
    identification_id = fields.Char(string=u'Cédula / Pasaporte', required=True)
    foreign = fields.Boolean(string=u'Extranjero?')
    asumir_antiguedad = fields.Boolean(string=u'Asumir Antiguedad', readonly=False, help=u"")
    wife_id = fields.Many2one('hr.family.burden', string=u'Esposo(a) / Conviviente',
                              required=False, readonly=False, help=u"", ondelete="restrict")
    family_burden_ids = fields.One2many('hr.family.burden', 'employee_id', u'Hijos / Parientes')
    pay_with_check = fields.Boolean(string=u'Pagar con Cheque', readonly=False, help=u"")
    payment_method = fields.Selection([('CUE', 'Deposito a cuenta'),
                                       ('EFE', 'Efectivo'),
                                       ('CHE', 'Cheque'),
                                       ], string='Forma de pago', default='CUE')
    cen_bank_id = fields.Many2one('res.bank', u'Banco')
    # cen_account_number = fields.Char(u'Número de cuenta')
    type_account = fields.Selection([('savings', 'Ahorros'),
                                     ('current', 'Corriente'),
                                     ('virtual', 'Virtual'),
    ], string='Tipo de Cuenta Bancaria', readonly=False, required=False,
                                    default='savings')
    third_payment = fields.Boolean(string="Pago a terceros?", default=False)
    supplier = fields.Boolean('Proveedor')
    customer = fields.Boolean('Cliente')
    # is_discapacitado = fields.Boolean(u'Presenta Discapacidad?', required=False)
    # discapacidad = fields.Float(u'Porcentaje de Discapacidad')
    # nombre_discapacidad = fields.Char(u'Discapacidad')
    tipo_sangre = fields.Char(u'Tipo Sangre')
    email_private = fields.Char('Email Personal')
    gender = fields.Selection(selection='_get_new_gender', string='Sexo', groups="hr.group_hr_user", tracking=True)
    marital = fields.Selection(selection='_get_new_marital', string='Estado Civil', groups="hr.group_hr_user", default='Soltero(a)', tracking=True)

    disability = fields.One2many('disability.custom_employe', 'employee_custom_id',
                                 string='Discapacidad')
    disability_substitute_person = fields.One2many(
        'disability_substitute_person.custom_employe',
        'employee_disability_substitute_person_id',
        string='Sustituto de Persona con Discapacidad')
    references = fields.One2many('references.custom_employe', 'employee_references_id',
                                 string='Referencias')
    availability_date_to_start = fields.Date(
        string='Fecha de Disponibilidad para Comenzar')
    availability_to_travel = fields.Selection(
        [('Si', 'Si'), ('No', 'No')],
        string='Disponibilidad para Viajar',
    )
    availability_to_change_residence = fields.Selection(
        [('Si', 'Si'), ('No', 'No')],
        string='Disponibilidad para Cambio de Residencia',
    )
    availability_for_rotating_shifts = fields.Selection(
        [('Si', 'Si'), ('No', 'No')],
        string='Disponibilidad para Turnos Rotativos',
    )
    availability_to_work_weekends_and_holidays = fields.Selection(
        [('Si', 'Si'), ('No', 'No')],
        string='Disponibilidad para Trabajar Fines de Semana y Festivos',
    )
    own_vehicle_availability = fields.Selection(
        [('Si', 'Si'), ('No', 'No')],
        string='Disponibilidad de Vehículo Propio',
    )
    drivers_license_type = fields.Selection(
        [('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E'), ('F', 'F')],
        string='Tipo de Licencia de Conducir',
    )
    additional_preparation = fields.One2many('additional_preparation.custom_employe',
                                             'employee_additional_preparation_id',
                                             string='Formación adicional')
    card_identification = fields.Binary('Cédula de identidad')
    file_extra = fields.One2many('files_extra.custom_employe',
                                 'employee_files_extra_id', string='Archivos Varios')
    file_memorandum = fields.One2many('files_memorandum.custom_employe',
                                      'employee_files_memorandum_id',
                                      string='Archivos Memorándum')
    type_identification = fields.Selection(
        [('Cédula', 'Cédula'), ('Pasaporte', 'Pasaporte')],
        string='Tipo de identificación',
    )

    canton = fields.Char('Cantón')
    phone_landline = fields.Char('Teléfono Fijo')
    url_linkedin = fields.Char('Url Perfil Linkedin')
    url_facebook = fields.Char('Url Perfil Facebook')
    name_of_institution = fields.Char('Nombre de la Institución')
    graduation_year = fields.Char('Año de Graduación')
    education_degree_earned = fields.Char('Título Obtenido')
    level_of_instruction = fields.Char('Nivel de Instrucción')
    no_senescyt_registration = fields.Char('Nro. Registro SENECYT')
    curriculum_vitae = fields.Binary('Hoja de Vida')
    file_name_curriculum_vitae = fields.Char("Nombre Archivo", )

    is_lactation = fields.Boolean("Se encuentra en Lactancia")
    lactance_ids = fields.One2many(
        'hr.employee.lactance',
        'employee_id',
        string='Periodo de Lactancia')

    total_family_burdens = fields.Integer(
        string="Número de cargas familiares válidas",
        compute='_compute_total_family_burdens',
        store=False
    )
    is_on_the_blacklist = fields.Boolean(string='¿Está en la lista negra?')
    note_for_on_the_blacklist = fields.Html(string='Razón de estar en lista negra')
    pin = fields.Char(compute='_compute_pin', store=True)
    resource_id = fields.Many2one('resource.resource', ondelete='cascade')
    department_from = fields.Char(string='Departamento anterior', readonly=True)
    job_from = fields.Char(string='Cargo anterior', readonly=True)

    @api.model
    def update_birthday_mailing_list(self, name_list):
        today_str = datetime.today().strftime('-%m-%d')

        employees = self.sudo().search([('birthday', 'like', today_str)])
        mailing_list = self.env['mailing.list'].sudo().search([('name', '=', name_list)], limit=1)

        if not mailing_list:
            mailing_list = self.env['mailing.list'].sudo().create({
                'name': name_list
            })

        # Limpia la lista actual
        contacts = self.env['mailing.contact'].sudo().search([('list_ids', 'in', mailing_list.id)])
        contacts.unlink()

        for emp in employees:
            if emp.work_email:
                contact = self.env['mailing.contact'].sudo().create({
                    'name': emp.name,
                    'email': emp.work_email,
                    'list_ids': [(6, 0, [mailing_list.id])]
                })

    @api.model
    def send_email_birthday_mailing_list(self, id_mail):

        mail = self.env['mailing.mailing'].sudo().browse(id_mail)

        if not mail:
            return

        mail.write({
            'state': 'draft'
        })

        # mail.action_launch()

    @api.onchange('name')
    def onchange_name_format(self):
        for rec in self:
            if rec.name:
                name_clean = rec.name.strip().lower()
                name_clean = name_clean.replace('ñ', 'n')

                name_without_accents = unicodedata.normalize('NFD', name_clean)
                name_without_accents = ''.join(char for char in name_without_accents
                                               if unicodedata.category(char) != 'Mn')
                rec.name = name_without_accents.title()

    @api.onchange('identification_id')
    def _onchange_identification_id(self):
        if self.identification_id:
            self.identification_id = self.identification_id.strip()

    @api.depends('identification_id')
    def _compute_pin(self):
        for record in self:
            if record.identification_id:
                identification = record.identification_id.strip()

                # Si empieza con 0, quitar el primer dígito
                if identification.startswith('0'):
                    record.pin = identification[1:]
                else:
                    record.pin = identification[:-1]
            else:
                record.pin = False

    def _send_notification_department_id(self):

        for record in self:
            if record.department_id:
                if self.env['ir.config_parameter'].sudo().get_param(
                        'ec_payroll.enable_email_department_change'):
                    template_id = self.env.ref(
                        "ec_payroll.ec_payroll_department_change_mail_template").id
                    template = self.env['mail.template'].browse(template_id)

                    template.sudo().send_mail(record.id, force_send=True, email_values={
                        # 'attachment_ids': [(4, self.pdf_attachment().id)]
                    })

    def _send_notification_job_id(self):

        for record in self:
            if record.job_id:
                if self.env['ir.config_parameter'].sudo().get_param(
                        'ec_payroll.enable_email_department_change'):
                    template_id = self.env.ref(
                        "ec_payroll.ec_payroll_job_change_mail_template").id
                    template = self.env['mail.template'].browse(template_id)

                    template.sudo().send_mail(record.id, force_send=True, email_values={
                        # 'attachment_ids': [(4, self.pdf_attachment().id)]
                    })

    def get_email_to(self):
        """Obtiene los emails de los usuarios según el grupo correspondiente"""
        emails = []

        group = self.env.ref('ec_payroll.group_hr_employee_notify', raise_if_not_found=False)
        if group:
            users = group.users
        else:
            users = self.env['res.users']

        # Extraer emails de los usuarios
        for user in users:
            if user.email:
                emails.append(user.email)
        return emails

    def get_email_sender(self):
        """Obtiene el email del servidor configurado para cambio de departamento"""
        email_server_id = self.env['ir.config_parameter'].sudo().get_param(
            'ec_payroll.email_department_change_sender'
        )
        if email_server_id:
            email_server = self.env['ir.mail_server'].sudo().browse(int(email_server_id))
            if email_server and email_server.smtp_user:
                return email_server.smtp_user

        return False



    @api.constrains('pin')
    def _check_pin_unique(self):
        for record in self:
            if record.pin:
                existing = self.sudo().search([
                    ('pin', '=', record.pin),
                    ('id', '!=', record.id)
                ])
                if existing:
                    raise ValidationError(f'El PIN "{record.pin}" ya existe. Debe ser único.')

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        res = super(HrEmployee, self).get_view(view_id=view_id, view_type=view_type, **options)
        if view_type == 'form':
            if self.env.user.has_group('ec_payroll.group_employee_perfil_admin'):
                doc = etree.XML(res['arch'])
                for field_node in doc.xpath("//field"):
                    field_node.set("readonly", "1")
                configs = self.env['employee.field.block'].search([
                    ('model_id.model', '=', self._name),
                    ('unblock', '=', True)
                ])
                for config in configs:
                    field_name = config.field_id.name
                    for field_node in doc.xpath("//field[@name='%s']" % field_name):
                        if "readonly" in field_node.attrib:
                            field_node.attrib.pop("readonly")
                res['arch'] = etree.tostring(doc, encoding='unicode')
        return res

    # horario_docente=fields.Many2one("cen.horario.docente")
    # calificacion_docente=fields.Float("Calificación Docente")

    # def contract_history(self):
    #     res_user = self.env['res.users'].search([('id', '=', self._uid)])
    #     if res_user.has_group('hr.group_hr_manager'):
    #         return {
    #             'name': _("Historial de Contratos"),
    #             'view_mode': 'tree',
    #             'res_model': 'contract.history',
    #             'type': 'ir.actions.act_window',
    #             'target': 'new',
    #             'domain': [('employee_id', '=', self.id)]
    #         }
    #     if self.id == self.env.user.employee_id.id:
    #         return {
    #             'name': _("Historial de Contratos"),
    #             'view_mode': 'tree',
    #             'res_model': 'contract.history',
    #             'type': 'ir.actions.act_window',
    #             'target': 'new'
    #         }
    #     else:
    #         raise UserError('You cannot access this field!!!!')

    # def salary_history(self):
    #     res_user = self.env['res.users'].search([('id', '=', self._uid)])
    #     if res_user.has_group('hr.group_hr_manager'):
    #         return {
    #             'name': _("Historial Salarial"),
    #             'view_mode': 'tree',
    #             'res_model': 'salary.history',
    #             'type': 'ir.actions.act_window',
    #             'target': 'new',
    #             'domain': [('employee_id', '=', self.id)]
    #         }
    #     elif self.id == self.env.user.employee_id.id:
    #         return {
    #             'name': _("Historial Salarial"),
    #             'view_mode': 'tree',
    #             'res_model': 'salary.history',
    #             'type': 'ir.actions.act_window',
    #             'target': 'new'
    #         }
    #     else:
    #         raise UserError('You cannot access this field!!!!')

    # def department_details(self):
    #     res_user = self.env['res.users'].search([('id', '=', self._uid)])
    #     view_id_tree = self.env.ref('history_employee.employee_department_history', False)
    #     if res_user.has_group('hr.group_hr_manager'):
    #         return {
    #             'name': _("Historial Laboral"),
    #             'view_mode': 'tree',
    #             'res_model': 'department.history',
    #             'type': 'ir.actions.act_window',
    #             'target': 'new',
    #             'domain': [('employee_id', '=', self.id)],
    #         }
    #     elif self.id == self.env.user.employee_id.id:
    #         return {
    #             'name': _("Historial Laboral"),
    #             'view_mode': 'tree',
    #             'res_model': 'department.history',
    #             'type': 'ir.actions.act_window',
    #             'target': 'new',
    #         }
    #     else:
    #         raise UserError('You cannot access this field!!!!')

    # @api.onchange('department_id')
    # def _onchange_department(self):
    #     employee_id = self.env['hr.employee'].search([('id', '=', self._origin.id)])
    #     contrato_id=self.env['hr.contract'].search([('employee_id', '=', self._origin.id),('state', '=', 'open')],limit=1)
    #     vals = {
    #         'employee_id': self._origin.id,
    #         'employee_name': employee_id.name,
    #         'updated_date': datetime.now(),
    #         'changed_field': 'Departamento',
    #         'current_value': self.department_id.name,
    #         'departamento_id':self.department_id.id,
    #         'cargo_id':contrato_id.job_id.id,
    #         'area_id': self.department_id.parent_id.id,
    #     }
    #     self.env['department.history'].sudo().create(vals)

    @api.model
    def _get_new_marital(self):
        selection = [
            ('Soltero(a)', 'Soltero(a)'),
            ('Casado(a)', 'Casado(a)'),
            ('Cohabitante legal', 'Cohabitante legal'),
            ('Viudo(a)', 'Viudo(a)'),
            ('Divorciado(a)', 'Divorciado(a)')
        ]
        return selection

    @api.model
    def _get_new_gender(self):
        selection = [
            ('Hombre', 'Hombre'),
            ('Mujer', 'Mujer'),
            ('Otro', 'Otro'),
        ]
        return selection

    @api.constrains('address_id')
    def _check_address_id(self):
        # import pdb
        # pdb.set_trace()
        if self.address_id:
            other_employees = self.search([
                ('address_id', '=', self.address_id.id),
                ('id', '!=', self.id),
                                           ])

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('identification_id', '=ilike', name + '%'), ('name', operator, name)]
            if operator in expression.NEGATIVE_TERM_OPERATORS:
                domain = ['&', '!'] + domain[1:]
        employees = self.search(domain + args, limit=limit)
        return employees.name_get()

    @api.onchange('user_id')
    def _onchange_user_id(self):
        if self.user_id:
            self.address_id = self.user_id.partner_id.id
        else:
            self.address_id = None

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        payslip_model = self.env['hr.payslip']
        employees = self.env['hr.employee'].browse()
        if self.env.context.get('date_start', False) and self.env.context.get('date_end', False):
            for employee in self.with_context(date_start=False, date_end=False).search([]):
                contracts = payslip_model.get_contract(employee, self.env.context.get('date_start', False), self.env.context.get('date_end', False))
                if not contracts:
                    employees |= employee
            if employees:
                args.append(('id', 'not in', employees.ids))
        return super(HrEmployee, self).search(args, offset=offset, limit=limit, order=order)

    def get_no_liquidated_contracts(self):
        self.ensure_one()
        contract_model = self.env['hr.contract']
        contracts = contract_model.browse()
        for contract in self.contract_ids:
            if not contract.hr_liquidation_ids:
                contracts |= contract
        return contracts

    def _compute_total_family_burdens(self):
        for record in self:
            valid_burdens = record.family_burden_ids.filtered(lambda burden: burden.is_valid)
            record.total_family_burdens = len(valid_burdens)

    @api.model
    def create(self, vals):
        if 'identification_id' in vals and vals['identification_id']:
            self.verifi_list_black_to_employee(vals['identification_id'])
        return super(HrEmployee, self).create(vals)




    def verifi_list_black_to_employee (self, identification_id):
        self._cr.execute("""
                    SELECT id, is_on_the_blacklist 
                    FROM hr_employee 
                    WHERE identification_id = %s 
                    LIMIT 1
                """, (identification_id,))

        result = self._cr.fetchone()

        if result:
            employee_id, is_blacklisted = result
            if is_blacklisted:
                raise ValidationError(
                    "No se puede crear el empleado: El número de cédula ya existe "
                    "y está en la lista negra."
                )
            else:
                raise ValidationError(
                    "No se puede crear el empleado: El número de cédula ya existe."
                )

    def write(self, vals):
        # Almacenar departamentos y cargos anteriores para cada registro
        departments_before = {}
        jobs_before = {}

        for record in self:
            departments_before[record.id] = record.department_id
            jobs_before[record.id] = record.job_id

        # Verificar identificación en lista negra
        if 'identification_id' in vals and vals['identification_id']:
            self.verifi_list_black_to_employee(vals['identification_id'])

        # Control de permisos por campos
        if self.env.user.has_group('ec_payroll.group_employee_perfil_admin'):
            allowed_fields = self.env['employee.field.block'].search([
                ('model_id.model', '=', self._name),
                ('unblock', '=', True)
            ]).mapped('field_id.name')

            for field in vals.keys():
                if field not in allowed_fields:
                    raise AccessError("No tiene permiso para modificar el campo '%s'." % field)


        if 'resource_calendar_id' in vals:
            for record in self:
                current_calendars = record.department_id.resource_id.sudo().ids
                new_calendar_id = vals['resource_calendar_id']

                if new_calendar_id not in current_calendars:
                    # También podés usar sudo() acá si da error al asignar
                    record.department_id.resource_id = [(4, new_calendar_id)]

        # Ejecutar el write del padre
        result = super(HrEmployee, self).write(vals)

        if 'department_id' in vals:
            for record in self:
                department_before = departments_before.get(record.id)
                record.department_from = department_before.name if department_before else ''
            self._send_notification_department_id()

        if 'job_id' in vals:
            for record in self:
                job_before = jobs_before.get(record.id)
                record.job_from = job_before.name if job_before else ''
            self._send_notification_job_id()

        if 'is_on_the_blacklist' in vals:
            self.check_in_blacklist()

        return result

    def check_in_blacklist(self):
        for employee in self:
            applicant = self.env['hr.applicant'].search([('identification', '=', employee.identification_id)], limit=1)
            if employee.is_on_the_blacklist and applicant.exists():
                applicant.sudo().write(
                    {
                        'in_blacklist': True,
                        'color': 1,
                        'kanban_state': 'blocked',
                    })
            elif not employee.is_on_the_blacklist and applicant.exists():
                applicant.sudo().write(
                    {
                        'in_blacklist': False,
                        'color': 0,
                        'kanban_state': 'normal',
                    })

    def load_lactation_periods(self):
        lactation_dictionary = {}

        lactation_employees = self.env['hr.employee'].sudo().search([('is_lactation', '=', True)])

        for employee in lactation_employees:
            if employee.id not in lactation_dictionary:
                lactation_dictionary[employee.id] = []

            periods = employee.lactance_ids.read(['start_periode', 'end_periode'])
            for period in periods:
                lactation_dictionary[employee.id].append((period['start_periode'], period['end_periode']))

        return lactation_dictionary



class EmployeeLactance(models.Model):
    _name = 'hr.employee.lactance'

    name = fields.Char(string='Nombre', compute='_compute_name', store=True)
    total_days = fields.Integer(string='Días totales', compute='_compute_total_days', readonly=True)
    start_periode = fields.Date(string='Inicio del período', required=True)
    end_periode = fields.Date(string='Fin del período', required=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)

    @api.constrains('start_periode', 'end_periode', 'employee_id')
    def _check_overlap_dates(self):
        for rec in self:
            if rec.start_periode and rec.end_periode:
                if rec.start_periode > rec.end_periode:
                    raise ValidationError("La fecha de inicio no puede ser mayor a la fecha de fin.")

                overlapping_records = self.sudo().search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('id', '!=', rec.id),
                    ('start_periode', '<=', rec.end_periode),
                    ('end_periode', '>=', rec.start_periode)
                ])
                if overlapping_records:
                    raise ValidationError(
                        f"El período {rec.start_periode} - {rec.end_periode} se solapa con otro período ya registrado para el empleado {rec.employee_id.name}.")

    @api.depends('start_periode', 'end_periode')
    def _compute_total_days(self):
        for record in self:
            if record.start_periode and record.end_periode:
                start_date = fields.Date.from_string(record.start_periode)
                end_date = fields.Date.from_string(record.end_periode)
                record.total_days = (end_date - start_date).days + 1
            else:
                record.total_days = 0

    @api.depends('start_periode', 'end_periode', 'total_days')
    def _compute_name(self):
        for record in self:
            if record.start_periode and record.end_periode:
                record.name = f"Desde: {record.start_periode}, hasta: {record.end_periode}, Total: {record.total_days} días"
            else:
                record.name = ""




class custom_employee_disability(models.Model):
    _name = 'disability.custom_employe'

    name = fields.Many2one('type_of_disability.custom_employe',string='Tipo de Discapacidad')
    percentage = fields.Integer('Porcentaje de Discapacidad')
    requirements = fields.Text('Requerimientos Especiales')
    adaptations = fields.Text('Adaptaciones Necesarias')
    documentation = fields.Binary('Documentación de Discapacidad')
    comment = fields.Text('Comentarios Adicionales')

    employee_custom_id = fields.Many2one('hr.employee', string='Empleado')

class custom_employee_disability_substitute_person(models.Model):
    _name = 'disability_substitute_person.custom_employe'

    name = fields.Char('Nombre Completo (Sustituto)')
    identification_substitute = fields.Char('Cédula de Ciudadanía/Identidad (Sustituto)')
    email_substitute = fields.Char('Correo Electrónico (Sustituto)')
    birth_substitute = fields.Date('Fecha de Nacimiento (Sustituto)')
    age_substitute = fields.Integer('Edad (Sustituto)', compute='_compute_age', store=True)
    percentaje_disability_substitute = fields.Integer('Porcentaje de Discapacidad (Sustituto)')
    type_disability_substitute = fields.Many2one('type_of_disability.custom_employe',string='Tipo de Discapacidad (Sustituto)')
    requirements_substitute  = fields.Text('Requerimientos Especiales (Sustituto)')
    card_disability_substitute = fields.Binary('Carné de Discapacidad (Sustituto)')
    identity_card_for_person_disability = fields.Binary('Cédula de Ciudadanía/Identidad de la Persona con Discapacidad (Sustituto)')
    support_judgment_substitute = fields.Binary('Sentencia de manutención (En caso de padres divorciados) (Sustituto)')
    support_affidavit_substitute = fields.Binary('Declaración Juramentada de manutención (En caso de padres divorciados)')

    type_of_disability_person_disability = fields.Many2one('type_of_disability.custom_employe','Tipo de Discapacidad (P. Discapacidad)')
    requirements_person_disability = fields.Text('Requerimientos Especiales (P. Discapacidad)')
    card_disability_person_disability = fields.Binary('Carné de Discapacidad (P. Discapacidad)')
    card_citizenship_person_disability = fields.Binary('Cédula de Ciudadanía/Identidad de la Persona con Discapacidad')
    support_judgment_person_disability = fields.Binary('Sentencia de manutención (En caso de padres divorciados) (P. Discapacidad)')
    support_affidavit_person_disability = fields.Binary('Declaración Juramentada de manutención (En caso de padres divorciados) (P. Discapacidad)')

    employee_disability_substitute_person_id = fields.Many2one('hr.employee', string='Empleado')

    @api.depends('birth_substitute')
    def _compute_age(self):
        for record in self:
            if record.birth_substitute:
                today = datetime.today()
                birth_date = fields.Date.from_string(record.birth_substitute)
                age_substitute = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                record.age_substitute = age_substitute
            else:
                record.age_substitute = 0


class custom_employee_references(models.Model):
    _name = 'references.custom_employe'

    name = fields.Char('Nombres')
    type = fields.Selection(
        [('Profesional', 'Profesional'), ('Personal', 'Personal')],
        string='Tipo de Referencia',
    )
    place_of_work = fields.Char('Lugar de trabajo o actividad económica')
    relationship = fields.Many2one('type_of_relationship.custom_employe',string='Relación')
    phone = fields.Char('Teléfono')
    email = fields.Char('Correo Electrónico')

    employee_references_id = fields.Many2one('hr.employee', string='Empleado')


class custom_employee_additional_preparation(models.Model):
    _name = 'additional_preparation.custom_employe'

    name = fields.Char('Nombre del Curso/Certificación')
    institution = fields.Char('Institución')
    completion_date = fields.Char('Fecha de Finalización (Año)')
    duration = fields.Integer('Duración (Horas)')
    internal_course = fields.Selection(
        [('Si', 'Si'), ('No', 'No')],
        string='Curso interno',
    )

    employee_additional_preparation_id = fields.Many2one('hr.employee', string='Empleado')


class custom_employee_files_extra(models.Model):
    _name = 'files_extra.custom_employe'

    name = fields.Char('Nombre del Archivo')
    file = fields.Binary('Archivo')

    employee_files_extra_id = fields.Many2one('hr.employee', string='Empleado')

class custom_employee_files_memorandum(models.Model):
    _name = 'files_memorandum.custom_employe'

    name = fields.Char('Nombre del Archivo')
    file = fields.Binary('Archivo')

    employee_files_memorandum_id = fields.Many2one('hr.employee', string='Empleado')

class type_of_disability(models.Model):
    _name = 'type_of_disability.custom_employe'

    name = fields.Char('Nombre de la Discapacidad')
    employee_type_of_disability_id = fields.Many2one('hr.employee', string='Empleado')

class type_of_relationship(models.Model):
    _name = 'type_of_relationship.custom_employe'

    name = fields.Char('Nombre de la Relación')
    employee_type_of_relationship_id = fields.Many2one('hr.employee', string='Empleado')


