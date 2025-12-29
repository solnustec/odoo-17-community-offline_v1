from odoo import models, fields, api,_
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression


class ExpenseRecord(models.Model):
    _name = 'hr.payroll.discounts'
    _inherit = ['mail.thread']
    _description = 'Registro de Descuento a Empleado'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        # required=True,
        tracking=True,
        domain="['|', ('active', '=', True), ('active', '=', False)]"
    )

    employee_identification = fields.Char(
        string='Cédula del Empleado',
        help='Campo para importar por cédula del empleado',
        compute='_compute_employee_identification',
        inverse='_inverse_employee_identification',
        store=False
    )

    category_id = fields.Many2one('hr.payroll.discounts.category',
                                  string='Categoría', required=True,
                                  tracking=True)
    description = fields.Text(string='Descripción', tracking=True)
    date = fields.Date(string='Fecha', required=True,
                       default=fields.Date.today, tracking=True)
    amount = fields.Float(string='Monto', required=True, default=0.0,
                          digits=(16, 2),  # Mejor usar digits que decimal_places
                          tracking=True)
    is_percentage = fields.Boolean(string='¿Es porcentaje?', default=False, tracking=True)
    payslip_id = fields.Many2one('hr.payslip', string='Payslip', tracking=True)
    state = fields.Selection(
        related='payslip_id.state',
        string='Payslip State',
        readonly=True,
        store=True
    )

    @api.model
    def create(self, vals):
        has_identification = 'employee_identification' in vals and vals['employee_identification']
        has_employee = 'employee_id' in vals and vals['employee_id']

        if not has_identification and not has_employee:
            raise UserError(_("Debe proporcionar al menos la cédula del empleado o seleccionar un empleado registrado"))


        return super(ExpenseRecord, self).create(vals)


    @api.model
    def _get_dynamic_domain(self):
        if self.env.user.has_group('hr_payroll.group_hr_payroll_manager'):
            return [(1, '=', 1)]
        return [('create_uid', '=', self.env.user.id)]

    @api.model
    def _apply_ir_rules(self, query, mode='read'):

        super()._apply_ir_rules(query, mode)

        dynamic_domain = self._get_dynamic_domain()
        if dynamic_domain:
            expression.expression(
                dynamic_domain,
                self.sudo(),
                self._table,
                query
            )



    @api.depends('employee_id')
    def _compute_employee_identification(self):

        for record in self:
            if record.employee_id:
                record.employee_identification = record.employee_id.identification_id or ''
            else:
                record.employee_identification = ''

    def _inverse_employee_identification(self):

        for record in self:
            if record.employee_identification:
                employee = self.env['hr.employee'].sudo().with_context(active_test=False).search([
                    ('identification_id', '=', record.employee_identification)
                ], limit=1)
                if employee:
                    record.employee_id = employee.id
                else:
                    raise ValidationError(
                        f"No se encontró empleado con cédula: {record.employee_identification}"
                    )
            else:
                record.employee_id = False

    @api.model
    def get_employee_discounts(self, employee_id=None, category=False, payslip_id=False, is_percentage=False, date_from=None, date_to=None):

        domain = [('is_percentage', '=', is_percentage)]

        if payslip_id:
            domain.extend(['|', ('state', 'in', [False, 'draft', 'verify', 'cancel']), ('payslip_id', '=', payslip_id)])
        else:
            domain.append(('state', 'in', [False, 'draft', 'verify', 'cancel']))


        if employee_id:
            domain.append(('employee_id', '=', employee_id))
        if category:
            domain.append(('category_id.name', '=', category))
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))

        res = self.sudo().search(domain)

        return res




class ExpenseCategory(models.Model):
    _name = 'hr.payroll.discounts.category'
    _inherit = ['mail.thread', ]
    _description = 'Categoría de Descuento'

    name = fields.Char(string='Nombre', required=True, tracking=True)
    status = fields.Boolean(string='Activo', default=True, tracking=True)
