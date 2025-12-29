from odoo import models, fields, api
from odoo import _, exceptions
from odoo.exceptions import ValidationError
from datetime import date

class InSurveyCampaign(models.Model):
    _name = 'in.survey.campaign'
    _description = 'Campaña de Encuesta'
    _rec_name = 'name'

    name = fields.Char(string='Nombre', required=True)
    survey_id = fields.Many2one('survey.survey', string='Encuesta base', required=True)
    department_id = fields.Many2one('hr.department', string='Departamento', required=True)
    date_start = fields.Date(string='Fecha de inicio', required=True)
    date_end = fields.Date(string='Fecha de fin', required=True)
    job_ids = fields.Many2many('hr.job', string='Cargos filtrados')
    employee_ids = fields.Many2many(
        'hr.employee', 
        string='Empleados específicos',
        domain="[('department_id', '=', department_id)]"
    )
    assignment_ids = fields.One2many('in.survey.campaign.assignment', 'campaign_id', string='Asignaciones')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activa'),
        ('closed', 'Cerrada'),
        ('cancelled', 'Cancelada'),
    ], string='Estado', default='draft')

    is_department_locked = fields.Boolean(string='Departamento Bloqueado', default=False, help='Indica si el departamento ya no puede ser modificado')
    is_jobs_locked = fields.Boolean(string='Cargos Bloqueados', default=False, help='Indica si los cargos ya no pueden ser modificados')
    is_employees_locked = fields.Boolean(string='Empleados Bloqueados', default=False, help='Indica si los empleados ya no pueden ser modificados')
    is_survey_manager = fields.Boolean(string='Es Survey Manager', compute='_compute_is_survey_manager', store=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        if self.env.user.has_group('survey.group_survey_manager'):
            user_employee = self.env.user.employee_id
            if user_employee and user_employee.department_id and 'department_id' in fields_list:
                res['department_id'] = user_employee.department_id.id
                res['is_department_locked'] = True

        return res

    def _compute_is_survey_manager(self):
        is_manager = self.env.user.has_group('survey.group_survey_manager')
        for record in self:
            record.is_survey_manager = is_manager

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end:
                if record.date_end < record.date_start:
                    raise ValidationError(_('La fecha fin no puede ser anterior a la fecha inicio.'))

    @api.onchange('department_id', 'job_ids')
    def _onchange_department_job_filter(self):
        if self.department_id:
            current_employees = self.employee_ids.filtered(lambda emp: emp.department_id.id != self.department_id.id)
            if current_employees:
                self.employee_ids = self.employee_ids - current_employees

            if self.job_ids:
                current_employees = self.employee_ids.filtered(lambda emp: emp.job_id.id not in self.job_ids.ids)
                if current_employees:
                    self.employee_ids = self.employee_ids - current_employees
        else:
            self.employee_ids = [(6, 0, [])]

        if self.department_id and self.job_ids:
            return {
                'domain': {
                    'employee_ids': [
                        ('department_id', '=', self.department_id.id),
                        ('job_id', 'in', self.job_ids.ids)
                    ]
                }
            }
        elif self.department_id:
            return {
                'domain': {
                    'employee_ids': [('department_id', '=', self.department_id.id)]
                }
            }
        else:
            return {
                'domain': {
                    'employee_ids': []
                }
            }

    def _get_employees_to_assign(self):
        self.ensure_one()
        Employee = self.env['hr.employee']

        if self.employee_ids:
            return self.employee_ids
        elif self.job_ids:
            return Employee.search([
                ('department_id', '=', self.department_id.id),
                ('job_id', 'in', self.job_ids.ids)
            ])
        else:
            return Employee.search([
                ('department_id', '=', self.department_id.id)
            ])

    def action_confirm(self):
        for campaign in self:
            employees = campaign._get_employees_to_assign()
            Assignment = self.env['in.survey.campaign.assignment']
            for employee in employees:
                if not Assignment.search_count([('campaign_id', '=', campaign.id), ('employee_id', '=', employee.id)]):
                    Assignment.create({
                        'campaign_id': campaign.id,
                        'employee_id': employee.id,
                        'state': 'pending',
                    })
            campaign.write({
                'state': 'active',
                'is_department_locked': True,
                'is_jobs_locked': True,
                'is_employees_locked': True
            })

class InSurveyCampaignAssignment(models.Model):
    _name = 'in.survey.campaign.assignment'
    _description = 'Asignación de Campaña de Encuesta'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    campaign_id = fields.Many2one('in.survey.campaign', string='Campaña', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, domain="[('department_id', '=', campaign_id.department_id)]")
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('answered', 'Respondida'),
        ('expired', 'Vencida'),
    ], string='Estado', default='pending')
    user_input_id = fields.Many2one('survey.user_input', string='Respuesta')

    survey_id = fields.Many2one(related='campaign_id.survey_id', string='Encuesta', readonly=True)
    date_start = fields.Date(related='campaign_id.date_start', string='Fecha de inicio', readonly=True)
    date_end = fields.Date(related='campaign_id.date_end', string='Fecha de fin', readonly=True)
    department_id = fields.Many2one(related='campaign_id.department_id', string='Departamento', readonly=True)

    _is_survey_manager = fields.Boolean(string='Is Survey Manager', compute='_compute_is_survey_manager', store=False)
    display_name = fields.Char(string='Nombre', compute='_compute_display_name', store=True)

    def _compute_is_survey_manager(self):
        is_manager = self.env.user.has_group('survey.group_survey_manager')
        for record in self:
            record._is_survey_manager = is_manager

    def _compute_display_name(self):
        for record in self:
            if record.campaign_id and record.employee_id:
                record.display_name = f"{record.campaign_id.name} - {record.employee_id.name}"
            elif record.campaign_id:
                record.display_name = record.campaign_id.name
            elif record.employee_id:
                record.display_name = f"Encuesta - {record.employee_id.name}"
            else:
                record.display_name = "Asignación de Encuesta"

    def name_get(self):
        result = []
        for assignment in self:
            if assignment.campaign_id and assignment.employee_id:
                name = f"{assignment.campaign_id.name} - {assignment.employee_id.name}"
            elif assignment.campaign_id:
                name = f"{assignment.campaign_id.name}"
            elif assignment.employee_id:
                name = f"Encuesta - {assignment.employee_id.name}"
            else:
                name = "Asignación de Encuesta"
            result.append((assignment.id, name))
        return result

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        campaign_id = self.env.context.get('default_campaign_id')
        if campaign_id:
            res['campaign_id'] = campaign_id
        return res

    @api.model
    def create(self, vals):
        assignment = super().create(vals)
        employee = assignment.employee_id
        campaign = assignment.campaign_id
        if employee and employee.user_id:
            activity_type = self.env.ref('mail.mail_activity_data_todo')
            assignment_url = '/web#id=%d&model=in.survey.campaign.assignment&view_type=form' % assignment.id
            survey_url = f'/survey/start/{campaign.survey_id.access_token}' if campaign.survey_id.access_token else assignment_url
            activity_vals = {
                'res_model_id': self.env['ir.model']._get_id('in.survey.campaign.assignment'),
                'res_id': assignment.id,
                'user_id': employee.user_id.id,
                'activity_type_id': activity_type.id,
                'date_deadline': campaign.date_end,
                'summary': _('Completar encuesta: %s', campaign.name),
                'note': _('''Por favor, complete la encuesta asignada.

<strong>Encuesta:</strong> %s
<strong>Fecha límite:</strong> %s

<a href="%s" class="btn btn-primary" style="background-color: #875A7B; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; display: inline-block; margin: 10px 0;">
    📝 Responder Encuesta
</a>

O ir a la asignación: <a href="%s">Ver detalles</a>''' % (campaign.name, campaign.date_end, survey_url, assignment_url)),
            }
            activity = self.env['mail.activity'].create(activity_vals)

            mail_message = self.env['mail.message'].search([
                ('model', '=', 'in.survey.campaign.assignment'),
                ('res_id', '=', assignment.id),
                ('message_type', '=', 'notification'),
            ], order='id desc', limit=1)
            if mail_message:
                mail_message.unlink()

            if employee.work_email:
                template = self.env.ref('internal_control.email_template_survey_assignment')
                rendered_body = template._render_template(template.body_html, template.model, [assignment.id])[assignment.id]
                rendered_subject = template._render_template(template.subject, template.model, [assignment.id])[assignment.id]
                mail_values = {
                    'subject': rendered_subject,
                    'body_html': rendered_body,
                    'email_to': employee.work_email,
                    'auto_delete': True,
                }
                self.env['mail.mail'].create(mail_values).send()
        return assignment

    def action_open_survey(self):
        self.ensure_one()
        survey = self.campaign_id.survey_id
        if not survey or not survey.access_token:
            raise exceptions.UserError('La encuesta base no tiene token público.')

        campaign = self.campaign_id
        today = date.today()
        if campaign.state != 'active' or not (campaign.date_start <= today <= campaign.date_end):
            raise exceptions.UserError(_('No puede responder la encuesta fuera del periodo de vigencia.'))

        UserInput = self.env['survey.user_input']
        user_input = UserInput.search([
            ('survey_id', '=', survey.id),
            ('partner_id', '=', self.employee_id.user_id.partner_id.id),
            ('assignment_id', '=', self.id)
        ], limit=1)

        if not user_input:
            user_input = UserInput.create({
                'survey_id': survey.id,
                'partner_id': self.employee_id.user_id.partner_id.id,
                'employee_id': self.employee_id.id,
                'campaign_id': campaign.id,
                'assignment_id': self.id,
                'state': 'new',
                'email': self.employee_id.user_id.email or self.employee_id.work_email,
                'is_admin_assigned': True,
                'assigned_by_id': self.env.user.id,
                'assigned_to_ids': [(4, self.employee_id.user_id.partner_id.id)],
            })
        
        url = (
            f'/survey/start/{survey.access_token}'
            f'?answer_token={user_input.access_token}'
            f'&assignment_id={self.id}'
            f'&campaign_id={self.campaign_id.id}'
        )
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }

    def action_open_survey_from_activity(self):
        return self.action_open_survey()
    
    def update_assignment_state(self):
        for assignment in self:
            if assignment.user_input_id:
                if assignment.user_input_id.state == 'done':
                    assignment.write({'state': 'answered'})
                elif assignment.user_input_id.state == 'new':
                    assignment.write({'state': 'pending'})
    
    def check_and_update_state(self):
        for assignment in self:
            if assignment.user_input_id:
                if assignment.user_input_id.state == 'done':
                    assignment.write({'state': 'answered'})
                elif assignment.user_input_id.state in ['new', 'skip']:
                    assignment.write({'state': 'pending'})
    
    @api.model
    def update_all_assignment_states(self):
        assignments = self.search([])
        for assignment in assignments:
            assignment.check_and_update_state()

    def _compute_is_survey_manager(self):
        user = self.env.user
        is_manager = user.has_group('survey.group_survey_manager')
        
        for record in self:
            record._is_survey_manager = is_manager or (record.employee_id.user_id and record.employee_id.user_id.id == user.id)

    @api.depends('campaign_id.name', 'employee_id.name')
    def _compute_display_name(self):
        for record in self:
            if record.campaign_id and record.employee_id:
                record.display_name = f"{record.campaign_id.name} - {record.employee_id.name}"
            elif record.campaign_id:
                record.display_name = f"{record.campaign_id.name}"
            elif record.employee_id:
                record.display_name = f"Encuesta - {record.employee_id.name}"
            else:
                record.display_name = "Asignación de Encuesta"

    @api.onchange('campaign_id')
    def _onchange_campaign_id(self):
        if self.campaign_id and self.campaign_id.department_id:
            return {
                'domain': {
                    'employee_id': [('department_id', '=', self.campaign_id.department_id.id)]
                }
            }
        return {
            'domain': {
                'employee_id': []
            }
        }