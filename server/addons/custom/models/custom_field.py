from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.translate import _
import re
from odoo.exceptions import ValidationError


class CustomFieldCategory(models.Model):
    _name = 'custom.category'
    _description = 'Campos de la categoria'

    name = fields.Char(string='Nombre', required=True)
    description = fields.Text(string='Descripción')
    field_ids = fields.One2many('custom.field', 'category_id', string='Campos')
    custom_field_ids = fields.One2many('custom.field', 'category_id', string='Campos')


class CustomField(models.Model):
    _name = 'custom.field'
    _description = 'Campos personalizados'

    name = fields.Char(string='Nombre visible en el formulario', required=True)
    code_field = fields.Char(string='Id', required=True,
                             help='Nombre del campo en la base de datos')
    model_id = fields.Many2one('ir.model', string='Modelo', required=True,
                               ondelete='cascade',
                               help='Modelo donde se va a crear el campo')
    field_type = fields.Selection([
        ('char', 'Char'),
        ('text', 'Text'),
        ('integer', 'Integer'),
        ('float', 'Float'),
        ('boolean', 'Boolean'),
        ('date', 'Date'),
        ('datetime', 'Datetime'),
        ('selection', 'Selection'),
        ('file', 'File'),
    ], string='Tipo', required=True)
    field_visibility = fields.Selection([
        ('module', 'Module'),
        ('web', 'Web'),
        ('both', 'Both'),
    ], string='Visibilidad', default='both')
    selection_options = fields.Text(string='Opciones de selección')
    active = fields.Boolean(string='Activo', default=True)
    required = fields.Boolean(string='Requerido', default=False)

    category_id = fields.Many2one('custom.category', string='Categoria',
                                  ondelete='cascade')
    regex_validation = fields.Char(string='Expresión Regular de Validación')
    file = fields.Binary(string='Archivo')

    # @api.model
    # def create_custom_field(self, vals):
    #     field = self.env['ir.model.fields'].create({
    #         'name': vals['code_field'],
    #         'model_id': vals['model_id'].model,
    #         'field_description': vals['name'],
    #         'ttype': vals['field_type'],
    #         'state': 'manual',
    #     })
    #     return field

    @api.model
    def create_custom_field(self):
        for record in self:
            field_vals = {
                'name': record.code_field,
                'model_id': record.model_id.model,
                'field_description': record.name,
                'ttype': record.field_type,
                'state': 'manual',
            }
            if record.field_type == 'selection':
                options = [(opt.strip(), opt.strip()) for opt in
                           record.selection_options.split(',')]
                field_vals['selection'] = options

            self.env['ir.model.fields'].create(field_vals)

    @api.constrains('field_value')
    def _check_field_value(self):
        for record in self:
            if record.regex_validation and record.field_value:
                if not re.match(record.regex_validation, record.field_value):
                    raise ValidationError(
                        'El valor ingresado no cumple con la validación de expresión regular.')


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    generic_field_value_ids = fields.Many2one('custom.generic_field',
                                              string='Campo de Valor Genérico')


class GenericFieldValue(models.Model):
    _name = 'custom.generic_field'
    _description = 'Generic Field Value'

    field_id = fields.Many2one('custom.field', string='Campo', required=True,
                               ondelete='cascade')
    res_model = fields.Many2one('ir.model', string='Modelo', required=True,
                                ondelete='cascade')
    res_id = fields.Integer(string='Resource ID', required=True)
    value_char = fields.Char(string='Texto')
    value_text = fields.Text(string='Area de Texto')
    value_integer = fields.Integer(string='Entero')
    value_float = fields.Float(string='Decimal')
    value_boolean = fields.Boolean(string='Booleano')
    value_date = fields.Date(string='Fecha')
    value_datetime = fields.Datetime(string='Fecha Hora')
    value_selection = fields.Char(string='Seleccion')
    file_attachment_ids = fields.One2many('ir.attachment', 'generic_field_value_ids',
                                          string='Archivos')
    display_value = fields.Char(string='Valor', compute='_compute_display_value')


    @api.depends('value_char', 'value_text', 'value_integer', 'value_float',
                 'value_boolean', 'value_date', 'value_datetime', 'value_selection')
    def _compute_display_value(self):

        for record in self:
            if record.value_char:
                record.display_value = record.value_char
            elif record.value_selection:
                record.display_value = record.value_selection
            elif record.value_text:
                record.display_value = record.value_text
            elif record.value_date:
                record.display_value = fields.Date.to_string(record.value_date)
            elif record.value_datetime:
                record.display_value = fields.Datetime.to_string(record.value_datetime)
            elif record.value_integer:
                record.display_value = str(record.value_integer)
            elif record.value_float:
                record.display_value = str(record.value_float)
            elif record.value_boolean is not None:
                record.display_value = 'Sí' if record.value_boolean else ''
            else:
                record.display_value = ''


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    identification = fields.Char(string='Identificación')
    job_id = fields.Many2one('hr.job', string='Empleo')
    generic_field_value_ids = fields.One2many('custom.generic_field', 'res_id', string='Campos')

    def create_employee_from_applicant(self):
        self.ensure_one()
        self._check_interviewer_access()

        if not self.partner_id:
            if not self.partner_name:
                raise UserError(_('Please provide an applicant name.'))
            self.partner_id = self.env['res.partner'].create({
                'is_company': False,
                'name': self.partner_name,
                'email': self.email_from,
            })

        action = self.env['ir.actions.act_window']._for_xml_id(
            'hr.open_view_employee_list')
        employee = self.env['hr.employee'].create(self._get_employee_create_vals())
        action['res_id'] = employee.id

        for field_value in self.generic_field_value_ids:
            for file_attachment in field_value.file_attachment_ids:
                file_attachment.copy({
                    'res_model': self.env['ir.model'].search(
                        [('model', '=', 'hr.employee')], limit=1).id,
                    'res_id': employee.id
                })
            field_value.copy({
                'res_model': self.env['ir.model'].search(
                    [('model', '=', 'hr.employee')], limit=1).id,
                'res_id': employee.id
            })

        return action


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    generic_field_value_ids = fields.One2many('custom.generic_field', 'res_id',
                                              string='Campos',
                                              domain=[
                                                  ('res_model', '=', 'hr.employee')])


class HrJob(models.Model):
    _inherit = 'hr.job'

    custom_field_ids = fields.Many2many('custom.field', string='Campos')
    custom_field_category_ids = fields.Many2many('custom.category',
                                                 compute='_compute_custom_field_categories',
                                                 string='Custom Field Categories')

    @api.depends('custom_field_ids')
    def _compute_custom_field_categories(self):
        for job in self:
            job.custom_field_category_ids = job.custom_field_ids.mapped('category_id')

    @api.model
    def default_get(self, fields_list):
        res = super(HrJob, self).default_get(fields_list)
        default_fields = self.env['custom.field'].search(
            [('name', 'in', ['Número de Identificación','Tipo de identificación'])])

        if default_fields:
            res['custom_field_ids'] = [
                (6, 0, default_fields.ids)]

        return res
