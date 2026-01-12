# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import hashlib
import logging
import base64
from datetime import date

_logger = logging.getLogger(__name__)

class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    employee_id = fields.Many2one('hr.employee', string='Empleado', ondelete='set null')
    department_id = fields.Many2one('hr.department', string='Departamento', related='employee_id.department_id', store=True)
    created_by_id = fields.Many2one('res.users', string='Creado por', default=lambda self: self.env.user)
    is_admin_assigned = fields.Boolean(string='Asignado por Admin', default=False)
    assigned_by_id = fields.Many2one('res.users', string='Asignado por', readonly=True)
    assigned_to_ids = fields.Many2many('res.partner', string='Asignado a', readonly=True)
    calculate_report_ids = fields.One2many('survey.calculate.report', 'user_input_id', string='Reportes de Cálculo')
    email_hash = fields.Char(string="Email Hasheado", index=True, readonly=True)
    email_display = fields.Char(string='Correo', compute='_compute_email_display', store=False)
    anonymous_token = fields.Char('Token Anónimo', index=True)
    campaign_id = fields.Many2one('in.survey.campaign', string='Campaña')
    assignment_id = fields.Many2one('in.survey.campaign.assignment', string='Asignación')
    branch_visit_id = fields.Many2one('survey.branch.visit', string='Visita a Sucursal')

    @staticmethod
    def generar_token_anonimo(identificador, survey_id, clave='secreto'):
        raw = f'{identificador}-{survey_id}-{clave}'
        return hashlib.sha256(raw.encode()).hexdigest()

    @api.model
    def create(self, vals):
        # --- Lógica de encuestas anónimas (restaurada) ---
        survey_id = vals.get('survey_id')
        identificador = None
        if survey_id:
            survey = self.env['survey.survey'].browse(survey_id)
            # Validar vigencia antes de permitir responder (solo para encuestas normales)
            if not survey.is_active():
                _logger.warning('Encuesta no activa')
                raise ValidationError(_("Esta encuesta no está disponible en este momento."))
            if survey.is_anonymous:
                partner_id = vals.get('partner_id')
                partner = self.env['res.partner'].browse(partner_id) if partner_id else None
                if not partner_id and self.env.user.partner_id:
                    partner_id = self.env.user.partner_id.id
                if partner_id:
                    identificador = f"partner-{partner_id}"
                if partner and partner.email:
                    email_hash = hashlib.sha256(partner.email.lower().encode()).hexdigest()
                    vals['email_hash'] = email_hash
                if not identificador and self.env.user:
                    identificador = f"user-{self.env.user.id}"
                if identificador:
                    token = self.generar_token_anonimo(identificador, survey_id)
                    existing = self.env['survey.user_input'].search([
                        ('survey_id', '=', survey_id),
                        ('anonymous_token', '=', token)
                    ])
                    if existing:
                        _logger.warning('Encuesta anónima ya respondida')
                        raise ValidationError("Ya has respondido esta encuesta anónima.")
                    vals['anonymous_token'] = token
                else:
                    _logger.warning("No se pudo generar token anónimo: sin identificador")
        # --- Lógica de campañas/asignaciones ---
        campaign_id = vals.get('campaign_id')
        assignment_id = vals.get('assignment_id')
        employee_id = vals.get('employee_id') or self.env.user.employee_id.id
        # Si no se pasa assignment_id, intentar deducirlo
        if not assignment_id and employee_id and survey_id:
            assignments = self.env['in.survey.campaign.assignment'].search([
                ('employee_id', '=', employee_id),
                ('state', '=', 'pending'),
                ('campaign_id.survey_id', '=', survey_id)
            ])
            if len(assignments) == 1:
                assignment_id = assignments.id
                vals['assignment_id'] = assignment_id
                campaign_id = assignments.campaign_id.id
                vals['campaign_id'] = campaign_id
            elif len(assignments) > 1:
                _logger.warning('Más de una asignación pendiente para este usuario y encuesta')
                raise UserError(_('Tiene más de una asignación pendiente para esta encuesta. Por favor, acceda desde la asignación correspondiente.'))
            else:
                # No es necesario loggear cuando no hay asignación - es un caso normal
                pass

        if campaign_id and employee_id:
            campaign = self.env['in.survey.campaign'].browse(campaign_id)
            assignment = self.env['in.survey.campaign.assignment'].browse(assignment_id) if assignment_id else None
            if not assignment:
                assignment = self.env['in.survey.campaign.assignment'].search([
                    ('campaign_id', '=', campaign_id),
                    ('employee_id', '=', employee_id)
                ], limit=1)
            if not assignment:
                _logger.warning('Empleado sin asignación')
                raise UserError(_('No tiene asignada esta encuesta en la campaña seleccionada.'))
            vals['assignment_id'] = assignment.id

        # --- Crear el user_input ---
        user_input = super().create(vals)
        # --- Solo vincular user_input a la asignación cuando esté completada ---
        # La asignación se marcará como 'answered' solo cuando el estado sea 'done'
        return user_input

    @api.depends('email', 'email_hash', 'survey_id.is_anonymous')
    def _compute_email_display(self):
        for record in self:
            if record.survey_id.is_anonymous and record.email_hash:
                record.email_display = record.email_hash
            else:
                record.email_display = record.email

    def _compute_and_save_metrics(self):
        for record in self:
            try:
                category = record.survey_id.category_id
                if not category:
                    # No es necesario loggear cuando no hay categoría - es un caso normal
                    continue
                
                # Verificar si ya existe un reporte para esta respuesta
                existing_report = self.env['survey.calculate.report'].search([
                    ('user_input_id', '=', record.id)
                ], limit=1)
                if existing_report:
                    # No es necesario loggear cuando ya existe un reporte - es un caso normal
                    continue
                
                # Crear el reporte con nombre apropiado
                report_name = f"Reporte de {record.survey_id.title or 'Encuesta'}"
                if record.partner_id and record.partner_id.name:
                    report_name += f" - {record.partner_id.name}"
                elif record.employee_id and record.employee_id.name:
                    report_name += f" - {record.employee_id.name}"
                else:
                    report_name += " - Anónimo"
                
                report = self.env['survey.calculate.report'].create({
                    'user_input_id': record.id,
                    'category_id': category.id,
                    'name': report_name,
                })
                # Usar category.code para lógica en el cálculo de métricas
                report.compute_metrics()
            except Exception as e:
                _logger.error(f"Error al calcular y guardar métricas para la respuesta {record.id}: {str(e)}")

    def write(self, vals):
        result = super(SurveyUserInput, self).write(vals)
        # Solo cuando la encuesta esté completamente terminada (state='done'), vincular a la asignación
        if 'state' in vals and vals['state'] == 'done':
            for record in self:
                try:
                    # Vincular user_input a la asignación de campaña y marcar como respondida
                    if record.assignment_id:
                        record.assignment_id.user_input_id = record.id
                        record.assignment_id.state = 'answered'

                    # Vincular user_input a la visita a sucursal y marcar como completada
                    if record.branch_visit_id:
                        record.branch_visit_id.user_input_id = record.id
                        record.branch_visit_id.state = 'completada'

                    record._compute_and_save_metrics()
                    if record.survey_id.is_anonymous:
                        record.write({
                            'partner_id': False,
                            'employee_id': False,
                        })
                except Exception as e:
                    _logger.error(f"Error al calcular métricas para la respuesta {record.id}: {str(e)}")
        return result

    def action_assign_survey(self):
        self.ensure_one()
        return {
            'name': _('Assign Survey'),
            'type': 'ir.actions.act_window',
            'res_model': 'survey.user_input.assign',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_survey_id': self.survey_id.id,
                'default_user_input_id': self.id,
            }
        }

    def action_export_pdf(self):
        self.ensure_one()
        try:
            report = self.env.ref('internal_control.action_report_survey_user_input')
            if not report:
                raise UserError(_("PDF Report template not found. Please contact your administrator."))
            # Solo pasar el ID de la participación actual para que el PDF muestre solo esta participación
            pdf_content, _ = report.with_context(discard_logo_check=True)._render_qweb_pdf(
                report.id, [self.id]
            )
            if not pdf_content:
                raise UserError(_("Failed to generate PDF. Please try again."))
            filename = f"Reporte_Respuesta_Individual_{self.survey_id.title or 'Encuesta'}_{self.partner_id.name or 'Anonimo'}.pdf"
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/pdf'
            })
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'self',
            }
        except Exception as e:
            _logger.error("PDF Export Error: %s", str(e))
            raise UserError(_("Failed to export PDF: %s") % str(e))

    def action_send_email_survey(self):
        self.ensure_one()
        if not self.partner_id.email:
            _logger.error("[SurveyUserInput] El participante no tiene email definido (user_input_id=%s)", self.id)
            raise UserError(_("The participant has no email defined."))
        try:
            report = self.env.ref('internal_control.action_report_survey_user_input')
            if not report:
                _logger.error("[SurveyUserInput] No se encontró el template de reporte PDF (user_input_id=%s)", self.id)
                raise UserError(_("PDF Report template not found. Please contact your administrator."))
            pdf_content, _ = report.with_context(discard_logo_check=True)._render_qweb_pdf(
                report.id, [self.id]
            )
            if not pdf_content:
                _logger.error("[SurveyUserInput] No se pudo generar el PDF (user_input_id=%s)", self.id)
                raise UserError(_("Failed to generate PDF. Please try again."))
            filename = f"Reporte_Respuesta_Individual_{self.survey_id.title or 'Encuesta'}_{self.partner_id.name or 'Anonimo'}.pdf"
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/pdf'
            })
            template = self.env.ref('internal_control.email_template_survey_response')
            rendered_body = template._render_template(template.body_html, template.model, self.ids)[self.id]
            rendered_subject = template._render_template(template.subject, template.model, self.ids)[self.id]
            mail_values = {
                'subject': rendered_subject,
                'body_html': rendered_body,
                'email_to': self.partner_id.email,
                'attachment_ids': [(6, 0, [attachment.id])],
                'auto_delete': True,
            }
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
            return True
        except Exception as e:
            _logger.error("[SurveyUserInput] Error enviando correo para user_input_id=%s: %s", self.id, str(e))
            raise UserError(_("Failed to send survey email: %s") % str(e))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        campaign_id = self.env.context.get('default_campaign_id')
        assignment_id = self.env.context.get('default_assignment_id')
        if campaign_id:
            res['campaign_id'] = campaign_id
        if assignment_id:
            res['assignment_id'] = assignment_id
        return res

class SurveyUserInputAssign(models.TransientModel):
    _name = 'survey.user_input.assign'
    _description = 'Asignar Encuesta a Empleados'

    survey_id = fields.Many2one('survey.survey', string='Encuesta', required=True)
    user_input_id = fields.Many2one('survey.user_input', string='Respuesta de Encuesta', required=True)
    job_ids = fields.Many2many('hr.job', string='Asignar por Cargo', required=True)

    def action_assign(self):
        self.ensure_one()
        current_user = self.env.user
        employees = self.env['hr.employee'].search([
            ('job_id', 'in', self.job_ids.ids),
            ('user_id', '!=', False)
        ])
        if not employees:
            raise UserError(_("No se encontraron empleados con los cargos seleccionados."))
        assigned_count = 0
        for employee in employees:
            if employee.user_id and employee.user_id.partner_id:
                new_input = self.user_input_id.copy({
                    'partner_id': employee.user_id.partner_id.id,
                    'employee_id': employee.id,
                    'is_admin_assigned': True,
                    'assigned_by_id': current_user.id,
                    'assigned_to_ids': [(4, employee.user_id.partner_id.id)],
                    'state': 'done',
                    'email': employee.user_id.email or current_user.email,
                })
                try:
                    new_input._compute_and_save_metrics()
                except Exception as e:
                    _logger.warning(f"Error al calcular métricas para empleado {employee.name}: {str(e)}")
                assigned_count += 1
        if assigned_count > 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Asignación Completada'),
                    'message': _('Se asignó la encuesta a %d empleado(s) con los cargos seleccionados y se generaron los reportes de métricas.') % assigned_count,
                    'type': 'success',
                    'sticky': False,
                }
            }
        return {'type': 'ir.actions.act_window_close'}

