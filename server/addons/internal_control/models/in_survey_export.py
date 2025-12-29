# -*- coding: utf-8 -*-
"""
Modelos y lógica para exportación de reportes de encuestas.
Incluye: wizard de exportar reportes.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging

_logger = logging.getLogger(__name__)

class SurveyExportReport(models.TransientModel):
    _name = 'survey.export.report'
    _description = 'Exportar Reporte de Encuesta'

    survey_id = fields.Many2one('survey.survey', string='Encuesta', required=True)
    campaign_id = fields.Many2one('in.survey.campaign', string='Campaña', domain="[('survey_id', '=', survey_id)]")
    observations = fields.Text(string='Observaciones', help='Observaciones adicionales para el reporte')
    report_type = fields.Selection([
        ('general', 'Reporte General'),
        ('campaign', 'Reporte por Campaña')
    ], string='Tipo de Reporte', default='general', required=True)

    @api.onchange('report_type')
    def _onchange_report_type(self):
        if self.report_type == 'general':
            self.campaign_id = False

    def action_export_pdf(self):
        self.ensure_one()
        category = self.survey_id.category_id
        
        if not category:
            raise UserError(_("La encuesta no tiene categoría asignada."))
            
        if self.report_type == 'campaign':
            campaigns = self.env['in.survey.campaign'].search([
                ('survey_id', '=', self.survey_id.id)
            ])
            if not campaigns:
                raise UserError(_("No hay campañas asociadas a esta encuesta. No se puede generar un reporte por campaña."))

        if category.code == 'revision_items':
            return self._export_revised_items_report(self.report_type)
        elif category.code == 'compliance':
            return self._export_compliance_report(self.report_type)
        elif category.code == 'satisfaction':
            return self._export_satisfaction_report(self.report_type)
        elif category.code == 'participation':
            return self._export_participation_report(self.report_type)
        else:
            raise UserError(_("Categoría de encuesta no soportada para reportes: %s") % category.code)

    def _get_campaign_summary(self):
        self.ensure_one()
        campaign = self.campaign_id
        total_asignados = len(campaign.assignment_ids)
        total_respondieron = len(campaign.assignment_ids.filtered(lambda a: a.user_input_id))
        porcentaje_cumplimiento = 0.0
        if total_asignados:
            porcentaje_cumplimiento = (total_respondieron / total_asignados) * 100
        
        return {
            'departamento': campaign.department_id.name or '',
            'campania': campaign.name or '',
            'total_asignados': total_asignados,
            'total_respondieron': total_respondieron,
            'porcentaje_cumplimiento': porcentaje_cumplimiento,
        }

    def _export_revised_items_report(self, report_type='general'):
        try:
            metrics = self.env['survey.revised.items'].search([
                ('survey_id', '=', self.survey_id.id)
            ])

            if self.report_type == 'campaign' and self.campaign_id:
                campaign_metrics = metrics.filtered(lambda m: m.campaign_id == self.campaign_id)

                if not campaign_metrics:
                    empty_summary = self.env['survey.revised.items.summary'].create({
                        'survey_id': self.survey_id.id,
                        'page_name': 'Sin datos de items revisados',
                        'total_items_revisados': 0,
                        'total_items_sin_novedad': 0,
                        'porcentaje_cumplimiento': 0.0,
                        'observations': f'Campaña: {self.campaign_id.name} - No hay métricas de items revisados disponibles'
                    })
                    summary_records = self.env['survey.revised.items.summary']
                else:
                    metrics_to_use = campaign_metrics
            else:
                metrics_to_use = metrics
            
            if not metrics_to_use and not (self.report_type == 'campaign' and self.campaign_id):
                raise UserError(_("No se encontraron métricas de items revisados para esta encuesta."))

            if self.observations:
                metrics_to_use.write({'observations': self.observations})

            section_summary = {}
            
            for metric in metrics_to_use:
                section_name = metric.page_name or 'Sin nombre'
                if section_name not in section_summary:
                    section_summary[section_name] = {
                        'total_items_revisados': 0,
                        'total_items_sin_novedad': 0,
                        'observations': set()
                    }
                
                section_summary[section_name]['total_items_revisados'] += metric.total_items_revisados
                section_summary[section_name]['total_items_sin_novedad'] += metric.total_items_sin_novedad
                
                if metric.observations:
                    section_summary[section_name]['observations'].add(metric.observations)

            summary_records = self.env['survey.revised.items.summary']
            for section_name, data in section_summary.items():
                total_revisados = data['total_items_revisados']
                sin_novedad = data['total_items_sin_novedad']
                porcentaje_cumplimiento = (sin_novedad / total_revisados * 100) if total_revisados > 0 else 0

                observaciones_unicas = '; '.join(data['observations']) if data['observations'] else ''
                
                summary_record = self.env['survey.revised.items.summary'].create({
                    'survey_id': self.survey_id.id,
                    'page_name': section_name,
                    'total_items_revisados': total_revisados,
                    'total_items_sin_novedad': sin_novedad,
                    'porcentaje_cumplimiento': porcentaje_cumplimiento,
                    'observations': observaciones_unicas
                })
                summary_records |= summary_record

            assigned_info = []
            campaigns = self.env['in.survey.campaign'].search([('survey_id', '=', self.survey_id.id)])
            
            if self.report_type == 'campaign' and self.campaign_id:
                assignments = self.campaign_id.assignment_ids
                for assignment in assignments:
                    employee = assignment.employee_id
                    if employee:
                        assigned_info.append({
                            'name': employee.name,
                            'job': employee.job_id.name if employee.job_id else None,
                            'department': employee.department_id.name if employee.department_id else None
                        })
            else:
                for campaign in campaigns:
                    for assignment in campaign.assignment_ids:
                        employee = assignment.employee_id
                        if employee:
                            assigned_info.append({
                                'name': employee.name,
                                'job': employee.job_id.name if employee.job_id else None,
                                'department': employee.department_id.name if employee.department_id else None
                            })

            if report_type == 'campaign':
                if self.campaign_id:
                    campaigns = [self.campaign_id]
                else:
                    campaigns = self.env['in.survey.campaign'].search([
                        ('survey_id', '=', self.survey_id.id)
                    ])
                
                if campaigns:
                    for campaign in campaigns:
                        assignments = campaign.assignment_ids
                        
                        if assignments:
                            total_asignados = len(assignments)
                            respondieron = len(assignments.filtered(lambda a: bool(a.user_input_id)))
                            porcentaje_participacion = (respondieron / total_asignados * 100) if total_asignados > 0 else 0

                            campaign_summary = self.env['survey.revised.items.summary'].create({
                                'survey_id': self.survey_id.id,
                                'page_name': f"Campaña: {campaign.name}",
                                'total_items_revisados': total_asignados,
                                'total_items_sin_novedad': respondieron,
                                'porcentaje_cumplimiento': porcentaje_participacion,
                                'observations': f"Departamento: {campaign.department_id.name}",
                                'department_id': campaign.department_id.id,
                                'campaign_id': campaign.id,
                                'total_asignados': total_asignados,
                                'total_respondieron': respondieron,
                                'participation_percentage': porcentaje_participacion
                            })
                            summary_records |= campaign_summary

                            for assignment in assignments:
                                employee = assignment.employee_id
                                responded = bool(assignment.user_input_id)
                                status = "Respondió" if responded else "No respondió"
                                
                                participant_detail = self.env['survey.revised.items.summary'].create({
                                    'survey_id': self.survey_id.id,
                                    'page_name': f"Participante: {employee.name}",
                                    'total_items_revisados': 1,
                                    'total_items_sin_novedad': 1 if responded else 0,
                                    'porcentaje_cumplimiento': 100.0 if responded else 0.0,
                                    'observations': f"Cargo: {employee.job_id.name or 'Sin cargo'} | {status}",
                                    'department_id': campaign.department_id.id,
                                    'campaign_id': campaign.id
                                })
                                summary_records |= participant_detail

            if report_type == 'campaign':
                report = self.env.ref('internal_control.action_report_survey_revised_items_campaign')
            else:
                report = self.env.ref('internal_control.action_report_survey_revised_items')
            
            pdf_content, _ = report.with_context(
                discard_logo_check=True,
                assigned_info=assigned_info
            )._render_qweb_pdf(report.id, summary_records.ids)
            
            if not pdf_content:
                raise UserError(_("Failed to generate PDF. Please try again."))
            
            filename = f"Reporte_Items_Revisados_{self.survey_id.title}_{report_type}.pdf"
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

    def _export_compliance_report(self, report_type='general'):
        try:
            metrics = self.env['survey.compliance'].search([
                ('survey_id', '=', self.survey_id.id)
            ])

            if self.report_type == 'campaign' and self.campaign_id:
                campaign_metrics = metrics.filtered(lambda m: m.campaign_id == self.campaign_id)

                if not campaign_metrics:
                    empty_summary = self.env['survey.compliance.summary'].create({
                        'survey_id': self.survey_id.id,
                        'page_name': 'Sin datos de cumplimiento',
                        'compliance_status': 'na',
                        'total_responses': 0,
                        'cumple_count': 0,
                        'no_cumple_count': 0,
                        'na_count': 0,
                        'porcentaje_cumplimiento': 0.0,
                        'observations': f'Campaña: {self.campaign_id.name} - No hay métricas de cumplimiento disponibles'
                    })
                    summary_records = self.env['survey.compliance.summary']
                    summary_records |= empty_summary
                    metrics_to_use = self.env['survey.compliance']
                else:
                    metrics_to_use = campaign_metrics
            else:
                metrics_to_use = metrics
            
            if not metrics_to_use and not (self.report_type == 'campaign' and self.campaign_id):
                raise UserError(_("No se encontraron métricas de cumplimiento para esta encuesta."))

            if self.observations:
                metrics_to_use.write({'observations': self.observations})

            section_summary = {}
            
            for metric in metrics_to_use:
                section_name = metric.page_name or 'Sin nombre'
                if section_name not in section_summary:
                    section_summary[section_name] = {
                        'total_responses': 0,
                        'cumple_count': 0,
                        'no_cumple_count': 0,
                        'na_count': 0,
                        'observations': set()
                    }
                
                section_summary[section_name]['total_responses'] += 1
                
                if metric.compliance_status == 'cumple':
                    section_summary[section_name]['cumple_count'] += 1
                elif metric.compliance_status == 'no_cumple':
                    section_summary[section_name]['no_cumple_count'] += 1
                else:
                    section_summary[section_name]['na_count'] += 1
                
                if metric.observations:
                    section_summary[section_name]['observations'].add(metric.observations)

            summary_records = self.env['survey.compliance.summary']
            for section_name, data in section_summary.items():
                total = data['total_responses']
                cumple = data['cumple_count']
                porcentaje_cumplimiento = (cumple / total * 100) if total > 0 else 0

                if cumple == total:
                    estado_general = 'cumple'
                elif data['no_cumple_count'] > 0:
                    estado_general = 'no_cumple'
                else:
                    estado_general = 'na'

                observaciones_unicas = '; '.join(data['observations']) if data['observations'] else ''
                
                summary_record = self.env['survey.compliance.summary'].create({
                    'survey_id': self.survey_id.id,
                    'page_name': section_name,
                    'compliance_status': estado_general,
                    'total_responses': total,
                    'cumple_count': cumple,
                    'no_cumple_count': data['no_cumple_count'],
                    'na_count': data['na_count'],
                    'porcentaje_cumplimiento': porcentaje_cumplimiento,
                    'observations': observaciones_unicas
                })
                summary_records |= summary_record

            if report_type == 'campaign':
                if self.campaign_id:
                    campaigns = [self.campaign_id]
                else:
                    campaigns = self.env['in.survey.campaign'].search([
                        ('survey_id', '=', self.survey_id.id)
                    ])
                
                if campaigns:
                    for campaign in campaigns:
                        assignments = campaign.assignment_ids
                        
                        if assignments:
                            total_asignados = len(assignments)
                            respondieron = len(assignments.filtered(lambda a: bool(a.user_input_id)))
                            no_respondieron = total_asignados - respondieron
                            porcentaje_participacion = (respondieron / total_asignados * 100) if total_asignados > 0 else 0

                            campaign_summary = self.env['survey.compliance.summary'].create({
                                'survey_id': self.survey_id.id,
                                'page_name': f"Campaña: {campaign.name}",
                                'compliance_status': 'na',
                                'total_responses': total_asignados,
                                'cumple_count': respondieron,
                                'no_cumple_count': no_respondieron,
                                'na_count': 0,
                                'porcentaje_cumplimiento': porcentaje_participacion,
                                'observations': f"Departamento: {campaign.department_id.name}",
                                'department_id': campaign.department_id.id,
                                'campaign_id': campaign.id,
                                'total_asignados': total_asignados,
                                'total_respondieron': respondieron,
                                'participation_percentage': porcentaje_participacion
                            })
                            summary_records |= campaign_summary

                            for assignment in assignments:
                                employee = assignment.employee_id
                                responded = bool(assignment.user_input_id)
                                status = "Respondió" if responded else "No respondió"
                                
                                participant_detail = self.env['survey.compliance.summary'].create({
                                    'survey_id': self.survey_id.id,
                                    'page_name': f"Participante: {employee.name}",
                                    'compliance_status': 'na',
                                    'total_responses': 1,
                                    'cumple_count': 1 if responded else 0,
                                    'no_cumple_count': 0 if responded else 1,
                                    'na_count': 0,
                                    'porcentaje_cumplimiento': 100.0 if responded else 0.0,
                                    'observations': f"Cargo: {employee.job_id.name or 'Sin cargo'} | {status}",
                                    'department_id': campaign.department_id.id,
                                    'campaign_id': campaign.id
                                })
                                summary_records |= participant_detail

            if report_type == 'campaign':
                report = self.env.ref('internal_control.action_report_survey_compliance_campaign')
                if not report:
                    report = self.env.ref('internal_control.action_report_survey_compliance_summary')
            else:
                report = self.env.ref('internal_control.action_report_survey_compliance_summary')
                
            if not report:
                raise UserError(_("PDF Report template not found. Please contact your administrator."))

            assigned_info = []
            campaigns = self.env['in.survey.campaign'].search([
                ('survey_id', '=', self.survey_id.id)
            ])
            
            if self.report_type == 'campaign' and self.campaign_id:
                assignments = self.campaign_id.assignment_ids
                for assignment in assignments:
                    employee = assignment.employee_id
                    if employee:
                        assigned_info.append({
                            'name': employee.name,
                            'job': employee.job_id.name if employee.job_id else None,
                            'department': employee.department_id.name if employee.department_id else None
                        })
            elif self.report_type == 'campaign':
                for campaign in campaigns:
                    for assignment in campaign.assignment_ids:
                        employee = assignment.employee_id
                        if employee:
                            assigned_info.append({
                                'name': employee.name,
                                'job': employee.job_id.name if employee.job_id else None,
                                'department': employee.department_id.name if employee.department_id else None
                            })
            else:
                for campaign in campaigns:
                    for assignment in campaign.assignment_ids:
                        employee = assignment.employee_id
                        if employee:
                            assigned_info.append({
                                'name': employee.name,
                                'job': employee.job_id.name if employee.job_id else None,
                                'department': employee.department_id.name if employee.department_id else None
                            })
            
            pdf_content, _ = report.with_context(
                discard_logo_check=True,
                assigned_info=assigned_info
            )._render_qweb_pdf(report.id, summary_records.ids)

            if not pdf_content:
                raise UserError(_("Failed to generate PDF. Please try again."))

            filename = f"Reporte_Cumplimiento_{self.survey_id.title}_{report_type}.pdf"

            summary_records.unlink()

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

    def _export_satisfaction_report(self, report_type='general'):
        try:
            metrics = self.env['survey.satisfaction'].search([
                ('survey_id', '=', self.survey_id.id)
            ])

            if self.report_type == 'campaign' and self.campaign_id:
                campaign_metrics = metrics.filtered(lambda m: m.campaign_id == self.campaign_id)

                if not campaign_metrics:
                    empty_summary = self.env['survey.satisfaction.summary'].create({
                        'survey_id': self.survey_id.id,
                        'page_name': 'Sin datos de satisfacción',
                        'total_encuestas': 0,
                        'encuestas_positivas': 0,
                        'satisfaccion': 0.0,
                        'porcentaje_satisfaccion': 0.0,
                        'porcentaje_cumplimiento': 0.0,
                        'observations': f'Campaña: {self.campaign_id.name} - No hay métricas de satisfacción disponibles'
                    })
                    summary_records = self.env['survey.satisfaction.summary']
                else:
                    metrics_to_use = campaign_metrics
            else:
                metrics_to_use = metrics
            
            if not metrics_to_use and not (self.report_type == 'campaign' and self.campaign_id):
                raise UserError(_("No se encontraron métricas de satisfacción para esta encuesta."))

            if self.observations:
                metrics_to_use.write({'observations': self.observations})

            section_summary = {}
            
            for metric in metrics_to_use:
                section_name = metric.page_name or 'Sin nombre'
                if section_name not in section_summary:
                    section_summary[section_name] = {
                        'total_encuestas': 0,
                        'encuestas_positivas': 0,
                        'satisfaccion': 0.0,
                        'observations': set()
                    }
                
                section_summary[section_name]['total_encuestas'] += metric.total_encuestas
                section_summary[section_name]['encuestas_positivas'] += metric.encuestas_positivas
                section_summary[section_name]['satisfaccion'] += metric.satisfaccion
                
                if metric.observations:
                    section_summary[section_name]['observations'].add(metric.observations)

            summary_records = self.env['survey.satisfaction.summary']
            for section_name, data in section_summary.items():
                total_encuestas = data['total_encuestas']
                encuestas_positivas = data['encuestas_positivas']
                porcentaje_satisfaccion = (encuestas_positivas / total_encuestas * 100) if total_encuestas > 0 else 0

                observaciones_unicas = '; '.join(data['observations']) if data['observations'] else ''
                
                summary_record = self.env['survey.satisfaction.summary'].create({
                    'survey_id': self.survey_id.id,
                    'page_name': section_name,
                    'total_encuestas': total_encuestas,
                    'encuestas_positivas': encuestas_positivas,
                    'satisfaccion': data['satisfaccion'],
                    'porcentaje_satisfaccion': porcentaje_satisfaccion,
                    'porcentaje_cumplimiento': 100.0 if total_encuestas > 0 else 0.0,
                    'observations': observaciones_unicas
                })
                summary_records |= summary_record

            assigned_info = []
            campaigns = self.env['in.survey.campaign'].search([('survey_id', '=', self.survey_id.id)])
            
            if self.report_type == 'campaign' and self.campaign_id:
                assignments = self.campaign_id.assignment_ids
                for assignment in assignments:
                    employee = assignment.employee_id
                    if employee:
                        assigned_info.append({
                            'name': employee.name,
                            'job': employee.job_id.name if employee.job_id else None,
                            'department': employee.department_id.name if employee.department_id else None
                        })
            else:
                for campaign in campaigns:
                    for assignment in campaign.assignment_ids:
                        employee = assignment.employee_id
                        if employee:
                            assigned_info.append({
                                'name': employee.name,
                                'job': employee.job_id.name if employee.job_id else None,
                                'department': employee.department_id.name if employee.department_id else None
                            })

            if report_type == 'campaign':
                if self.campaign_id:
                    campaigns = [self.campaign_id]
                else:
                    campaigns = self.env['in.survey.campaign'].search([
                        ('survey_id', '=', self.survey_id.id)
                    ])
                
                if campaigns:
                    for campaign in campaigns:
                        assignments = campaign.assignment_ids
                        
                        if assignments:
                            total_asignados = len(assignments)
                            respondieron = len(assignments.filtered(lambda a: bool(a.user_input_id)))
                            porcentaje_participacion = (respondieron / total_asignados * 100) if total_asignados > 0 else 0

                            campaign_satisfaction_metrics = metrics_to_use.filtered(lambda m: m.campaign_id == campaign)
                            
                            if campaign_satisfaction_metrics:
                                total_encuestas_satisfaccion = sum(campaign_satisfaction_metrics.mapped('total_encuestas'))
                                total_positivas_satisfaccion = sum(campaign_satisfaction_metrics.mapped('encuestas_positivas'))
                                promedio_satisfaccion = sum(campaign_satisfaction_metrics.mapped('satisfaccion')) / len(campaign_satisfaction_metrics) if campaign_satisfaction_metrics else 0.0
                                porcentaje_satisfaccion_real = (total_positivas_satisfaccion / total_encuestas_satisfaccion * 100) if total_encuestas_satisfaccion > 0 else 0.0
                            else:
                                total_encuestas_satisfaccion = respondieron
                                total_positivas_satisfaccion = 0
                                promedio_satisfaccion = 0.0
                                porcentaje_satisfaccion_real = 0.0

                            campaign_summary = self.env['survey.satisfaction.summary'].create({
                                'survey_id': self.survey_id.id,
                                'page_name': f"Campaña: {campaign.name}",
                                'total_encuestas': total_encuestas_satisfaccion,
                                'encuestas_positivas': total_positivas_satisfaccion,
                                'satisfaccion': promedio_satisfaccion,
                                'porcentaje_satisfaccion': porcentaje_satisfaccion_real,
                                'porcentaje_cumplimiento': porcentaje_participacion,
                                'observations': f"Departamento: {campaign.department_id.name}",
                                'department_id': campaign.department_id.id,
                                'campaign_id': campaign.id,
                                'total_asignados': total_asignados,
                                'total_respondieron': respondieron,
                                'participation_percentage': porcentaje_participacion
                            })
                            summary_records |= campaign_summary

                            for assignment in assignments:
                                employee = assignment.employee_id
                                responded = bool(assignment.user_input_id)
                                status = "Respondió" if responded else "No respondió"
                                
                                participant_detail = self.env['survey.satisfaction.summary'].create({
                                    'survey_id': self.survey_id.id,
                                    'page_name': f"Participante: {employee.name}",
                                    'total_encuestas': 1,
                                    'encuestas_positivas': 1 if responded else 0,
                                    'satisfaccion': 100.0 if responded else 0.0,
                                    'porcentaje_satisfaccion': 100.0 if responded else 0.0,
                                    'porcentaje_cumplimiento': 100.0 if responded else 0.0,
                                    'observations': f"Cargo: {employee.job_id.name or 'Sin cargo'} | {status}",
                                    'department_id': campaign.department_id.id,
                                    'campaign_id': campaign.id
                                })
                                summary_records |= participant_detail

            if report_type == 'campaign':
                report = self.env.ref('internal_control.action_report_survey_satisfaction_campaign')
            else:
                report = self.env.ref('internal_control.action_report_survey_satisfaction')
            
            pdf_content, _ = report.with_context(
                discard_logo_check=True,
                assigned_info=assigned_info
            )._render_qweb_pdf(report.id, summary_records.ids)
            
            if not pdf_content:
                raise UserError(_("Failed to generate PDF. Please try again."))
            
            filename = f"Reporte_Satisfaccion_{self.survey_id.title}_{report_type}.pdf"
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

    def _export_participation_report(self, report_type='general'):
        try:
            metrics = self.env['survey.participation'].search([
                ('survey_id', '=', self.survey_id.id)
            ])

            if self.report_type == 'campaign' and self.campaign_id:
                campaign_metrics = metrics.filtered(lambda m: m.campaign_id == self.campaign_id)

                if not campaign_metrics:
                    empty_summary = self.env['survey.participation.summary'].create({
                        'survey_id': self.survey_id.id,
                        'page_name': 'Sin datos de participación',
                        'respuestas_si': 0,
                        'respuestas_no': 0,
                        'no_respondieron': 0,
                        'total_respuestas': 0,
                        'porcentaje_participacion': 0.0,
                        'observations': f'Campaña: {self.campaign_id.name} - No hay métricas de participación disponibles'
                    })
                    summary_records = self.env['survey.participation.summary']
                else:
                    metrics_to_use = campaign_metrics
            else:
                metrics_to_use = metrics
            
            if not metrics_to_use and not (self.report_type == 'campaign' and self.campaign_id):
                raise UserError(_("No se encontraron métricas de participación para esta encuesta."))

            if self.observations:
                metrics_to_use.write({'observations': self.observations})

            section_summary = {}
            
            for metric in metrics_to_use:
                section_name = metric.page_name or 'Sin nombre'
                if section_name not in section_summary:
                    section_summary[section_name] = {
                        'respuestas_si': 0,
                        'respuestas_no': 0,
                        'no_respondieron': 0,
                        'observations': set()
                    }
                
                section_summary[section_name]['respuestas_si'] += metric.respuestas_si
                section_summary[section_name]['respuestas_no'] += metric.respuestas_no
                section_summary[section_name]['no_respondieron'] += metric.no_respondieron
                
                if metric.observations:
                    section_summary[section_name]['observations'].add(metric.observations)

            summary_records = self.env['survey.participation.summary']
            for section_name, data in section_summary.items():
                total_respuestas = data['respuestas_si'] + data['respuestas_no'] + data['no_respondieron']
                porcentaje_participacion = (data['respuestas_si'] / total_respuestas * 100) if total_respuestas > 0 else 0

                observaciones_unicas = '; '.join(data['observations']) if data['observations'] else ''
                
                summary_record = self.env['survey.participation.summary'].create({
                    'survey_id': self.survey_id.id,
                    'page_name': section_name,
                    'respuestas_si': data['respuestas_si'],
                    'respuestas_no': data['respuestas_no'],
                    'no_respondieron': data['no_respondieron'],
                    'total_respuestas': total_respuestas,
                    'porcentaje_participacion': porcentaje_participacion,
                    'observations': observaciones_unicas
                })
                summary_records |= summary_record

            assigned_info = []
            campaigns = self.env['in.survey.campaign'].search([('survey_id', '=', self.survey_id.id)])
            
            if self.report_type == 'campaign' and self.campaign_id:
                assignments = self.campaign_id.assignment_ids
                for assignment in assignments:
                    employee = assignment.employee_id
                    if employee:
                        assigned_info.append({
                            'name': employee.name,
                            'job': employee.job_id.name if employee.job_id else None,
                            'department': employee.department_id.name if employee.department_id else None
                        })
            else:
                for campaign in campaigns:
                    for assignment in campaign.assignment_ids:
                        employee = assignment.employee_id
                        if employee:
                            assigned_info.append({
                                'name': employee.name,
                                'job': employee.job_id.name if employee.job_id else None,
                                'department': employee.department_id.name if employee.department_id else None
                            })

            if report_type == 'campaign':
                if self.campaign_id:
                    campaigns = [self.campaign_id]
                else:
                    campaigns = self.env['in.survey.campaign'].search([
                        ('survey_id', '=', self.survey_id.id)
                    ])
                
                if campaigns:
                    for campaign in campaigns:
                        assignments = campaign.assignment_ids
                        
                        if assignments:
                            total_asignados = len(assignments)
                            respondieron = len(assignments.filtered(lambda a: bool(a.user_input_id)))
                            no_respondieron = total_asignados - respondieron
                            porcentaje_participacion = (respondieron / total_asignados * 100) if total_asignados > 0 else 0

                            campaign_summary = self.env['survey.participation.summary'].create({
                                'survey_id': self.survey_id.id,
                                'page_name': f"Campaña: {campaign.name}",
                                'respuestas_si': respondieron,
                                'respuestas_no': 0,
                                'no_respondieron': no_respondieron,
                                'total_respuestas': total_asignados,
                                'porcentaje_participacion': porcentaje_participacion,
                                'observations': f"Departamento: {campaign.department_id.name}",
                                'department_id': campaign.department_id.id,
                                'campaign_id': campaign.id,
                                'total_asignados': total_asignados,
                                'total_respondieron': respondieron,
                                'participation_percentage': porcentaje_participacion
                            })
                            summary_records |= campaign_summary

                            for assignment in assignments:
                                employee = assignment.employee_id
                                responded = bool(assignment.user_input_id)
                                status = "Respondió" if responded else "No respondió"
                                
                                participant_detail = self.env['survey.participation.summary'].create({
                                    'survey_id': self.survey_id.id,
                                    'page_name': f"Participante: {employee.name}",
                                    'respuestas_si': 1 if responded else 0,
                                    'respuestas_no': 0,
                                    'no_respondieron': 0 if responded else 1,
                                    'total_respuestas': 1,
                                    'porcentaje_participacion': 100.0 if responded else 0.0,
                                    'observations': f"Cargo: {employee.job_id.name or 'Sin cargo'} | {status}",
                                    'department_id': campaign.department_id.id,
                                    'campaign_id': campaign.id
                                })
                                summary_records |= participant_detail

            if report_type == 'campaign':
                report = self.env.ref('internal_control.action_report_survey_participation_campaign')
            else:
                report = self.env.ref('internal_control.action_report_survey_participation')
            
            pdf_content, _ = report.with_context(
                discard_logo_check=True,
                assigned_info=assigned_info
            )._render_qweb_pdf(report.id, summary_records.ids)
            
            if not pdf_content:
                raise UserError(_("Failed to generate PDF. Please try again."))
            
            filename = f"Reporte_Participacion_{self.survey_id.title}_{report_type}.pdf"
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

