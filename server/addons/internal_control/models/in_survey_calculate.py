# -*- coding: utf-8 -*-
"""
Reporte de cálculo y métodos asociados.
Incluye: SurveyCalculateReport y lógica asociada.
"""
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class SurveyCalculateReport(models.Model):
    _name = 'survey.calculate.report'
    _description = 'Reporte de Cálculo'
    _rec_name = 'name'

    name = fields.Char(string="Nombre del Reporte", required=True, readonly=True)
    user_input_id = fields.Many2one('survey.user_input', string='Respuesta de la Encuesta', ondelete='cascade')
    category_id = fields.Many2one('survey.category', string='Categoría', ondelete='set null')
    calculated_date = fields.Date(string='Fecha de Cálculo', default=fields.Date.context_today)

    def compute_metrics(self):
        for report in self:
            try:
                category = report.category_id
                if not category:
                    _logger.warning(f"No se encontró categoría para el reporte {report.id}")
                    continue

                # Usar category.code para lógica
                if category.code == 'revision_items':
                    self._compute_metrics_for_revised_items(report)
                elif category.code == 'compliance':
                    self._compute_metrics_for_compliance(report)
                elif category.code == 'satisfaction':
                    self._compute_metrics_for_satisfaction(report)
                elif category.code == 'participation':
                    self._compute_metrics_for_participation(report)
                else:
                    _logger.warning(f"Categoría no reconocida: {category.code}")

            except Exception as e:
                _logger.error(f"Error al calcular métricas para el reporte {report.id}: {str(e)}")

    def _compute_metrics_for_revised_items(self, report):
        user_input = report.user_input_id
        if not user_input:
            _logger.error("No se encontró user_input")
            return

        # Obtener todas las páginas (secciones) de la encuesta
        pages = self.env['survey.question'].search([
            ('survey_id', '=', user_input.survey_id.id),
            ('is_page', '=', True)
        ])

        # Eliminar registros existentes si los hay
        existing_items = self.env['survey.revised.items'].search([
            ('calculate_report_id', '=', report.id)
        ])
        if existing_items:
            existing_items.unlink()

        for page in pages:
            total_revisados = 0
            total_sin_novedad = 0

            # Buscar todas las respuestas de la encuesta para esta sección
            respuestas = self.env['survey.user_input.line'].search([
                ('user_input_id', '=', user_input.id),
                ('question_id.question_type', '=', 'numerical_box'),
                ('question_id.page_id', '=', page.id)
            ])

            for resp in respuestas:
                # Obtener el título de la pregunta
                pregunta = resp.question_id.title
                if isinstance(pregunta, dict):
                    pregunta = pregunta.get('es_EC', '')
                pregunta = pregunta.lower()

                if resp.value_numerical_box is not None:
                    valor = float(resp.value_numerical_box)

                    # Clasificar según el tipo de pregunta
                    if "revisados" in pregunta and "sin novedad" in pregunta:
                        total_sin_novedad += valor
                    elif "revisados" in pregunta:
                        total_revisados += valor

            # Solo crear métricas si la página tiene preguntas relevantes (con datos)
            if total_revisados > 0 or total_sin_novedad > 0:
                # Calcular el porcentaje de cumplimiento
                porcentaje = 0
                if total_revisados > 0:
                    porcentaje = (total_sin_novedad / total_revisados) * 100

                # Obtener el título de la página
                page_title = page.title
                if isinstance(page_title, dict):
                    page_title = page_title.get('es_EC', '')

                # Crear el registro de métricas para esta sección
                try:
                    vals = {
                        'calculate_report_id': report.id,
                        'page_id': page.id,
                        'page_name': page_title,
                        'total_items_revisados': total_revisados,
                        'total_items_sin_novedad': total_sin_novedad,
                        'porcentaje_cumplimiento': porcentaje
                    }
                    self.env['survey.revised.items'].create(vals)
                except Exception as e:
                    _logger.error(f"Error al crear registro para sección {page_title}: {str(e)}")
                    raise
                
        # Actualizar registros de resumen después de crear todas las métricas
        self._update_revised_items_summary(user_input.survey_id)

    def _update_compliance_summary(self, survey_id):
        """Actualiza los registros de resumen de cumplimiento para una encuesta"""
        try:
            # Obtener todas las métricas de cumplimiento para esta encuesta
            metrics = self.env['survey.compliance'].search([
                ('survey_id', '=', survey_id.id)
            ])
            
            if not metrics:
                _logger.info(f"No se encontraron métricas de cumplimiento para la encuesta {survey_id.title}")
                return
            
            # Agrupar métricas por sección (page_name)
            section_summary = {}
            for metric in metrics:
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
            
            # Eliminar registros de resumen existentes para esta encuesta
            existing_summary = self.env['survey.compliance.summary'].search([
                ('survey_id', '=', survey_id.id)
            ])
            if existing_summary:
                existing_summary.unlink()
            
            # Crear nuevos registros de resumen
            for section_name, data in section_summary.items():
                # Calcular porcentaje de cumplimiento
                total = data['total_responses']
                cumple = data['cumple_count']
                porcentaje_cumplimiento = (cumple / total * 100) if total > 0 else 0
                
                # Determinar estado general de la sección basado en porcentaje de cumplimiento
                # LÓGICA CORREGIDA: Usar umbrales de porcentaje en lugar de lógica binaria
                if porcentaje_cumplimiento >= 90:
                    estado_general = 'cumple'  # Excelente cumplimiento
                elif porcentaje_cumplimiento >= 70:
                    estado_general = 'cumple'  # Buen cumplimiento
                elif porcentaje_cumplimiento >= 50:
                    estado_general = 'no_cumple'  # Cumplimiento parcial
                else:
                    estado_general = 'no_cumple'  # Bajo cumplimiento
                
                # Unir observaciones únicas
                observaciones_unicas = '; '.join(data['observations']) if data['observations'] else ''
                
                summary_record = self.env['survey.compliance.summary'].create({
                    'survey_id': survey_id.id,
                    'page_name': section_name,
                    'compliance_status': estado_general,
                    'total_responses': total,
                    'cumple_count': cumple,
                    'no_cumple_count': data['no_cumple_count'],
                    'na_count': data['na_count'],
                    'porcentaje_cumplimiento': porcentaje_cumplimiento,
                    'observations': observaciones_unicas
                    # Los campos de riesgo se calculan automáticamente basados en porcentaje_cumplimiento
                })
            
            
        except Exception as e:
            _logger.error(f"Error al actualizar resumen de cumplimiento para encuesta {survey_id.title}: {str(e)}")

    def _update_revised_items_summary(self, survey_id):
        """Actualiza los registros de resumen de items revisados para una encuesta"""
        try:
            # Obtener todas las métricas de items revisados para esta encuesta
            metrics = self.env['survey.revised.items'].search([
                ('survey_id', '=', survey_id.id)
            ])
            
            if not metrics:
                _logger.info(f"No se encontraron métricas de items revisados para la encuesta {survey_id.title}")
                return
            
            # Eliminar registros de resumen existentes
            existing_summary = self.env['survey.revised.items.summary'].search([
                ('survey_id', '=', survey_id.id)
            ])
            if existing_summary:
                existing_summary.unlink()
            
            # Crear nuevos registros de resumen
            for metric in metrics:
                summary_record = self.env['survey.revised.items.summary'].create({
                    'survey_id': survey_id.id,
                    'page_name': metric.page_name,
                    'total_items_revisados': metric.total_items_revisados,
                    'total_items_sin_novedad': metric.total_items_sin_novedad,
                    'porcentaje_cumplimiento': metric.porcentaje_cumplimiento,
                    'observations': metric.observations
                    # Los campos de riesgo se calculan automáticamente basados en porcentaje_cumplimiento
                })
            
        except Exception as e:
            _logger.error(f"Error al actualizar resumen de items revisados para encuesta {survey_id.title}: {str(e)}")

    def _update_satisfaction_summary(self, survey_id):
        """Actualiza los registros de resumen de satisfacción para una encuesta"""
        try:
            # Obtener todas las métricas de satisfacción para esta encuesta
            metrics = self.env['survey.satisfaction'].search([
                ('survey_id', '=', survey_id.id)
            ])
            
            if not metrics:
                _logger.info(f"No se encontraron métricas de satisfacción para la encuesta {survey_id.title}")
                return
            
            # Eliminar registros de resumen existentes
            existing_summary = self.env['survey.satisfaction.summary'].search([
                ('survey_id', '=', survey_id.id)
            ])
            if existing_summary:
                existing_summary.unlink()
            
            # Crear nuevos registros de resumen
            for metric in metrics:
                summary_record = self.env['survey.satisfaction.summary'].create({
                    'survey_id': survey_id.id,
                    'page_name': metric.page_name,
                    'total_encuestas': metric.total_encuestas,
                    'encuestas_positivas': metric.encuestas_positivas,
                    'satisfaccion': metric.satisfaccion,
                    'porcentaje_satisfaccion': metric.porcentaje_satisfaccion,
                    'porcentaje_cumplimiento': metric.porcentaje_cumplimiento,
                    'observations': metric.observations
                    # Los campos de riesgo se calculan automáticamente basados en porcentaje_satisfaccion
                })
                
                # Log para verificar qué datos se están copiando (solo en debug)
                # _logger.info(f"[SUMMARY] Copiando datos: {metric.page_name} - Total: {metric.total_encuestas}, Positivas: {metric.encuestas_positivas}, %: {metric.porcentaje_satisfaccion}")
            
        except Exception as e:
            _logger.error(f"Error al actualizar resumen de satisfacción para encuesta {survey_id.title}: {str(e)}")

    @api.model
    def create(self, vals):
        if not vals.get('name'):
            vals['name'] = f"Reporte #{vals.get('user_input_id', 'Nuevo')}"
        record = super().create(vals)
        return record

    def _compute_metrics_for_compliance(self, report):
        user_input = report.user_input_id
        if not user_input:
            _logger.error("No se encontró user_input")
            return
        pages = self.env['survey.question'].search([
            ('survey_id', '=', user_input.survey_id.id),
            ('is_page', '=', True)
        ])
        existing_compliance = self.env['survey.compliance'].search([
            ('calculate_report_id', '=', report.id)
        ])
        if existing_compliance:
            existing_compliance.unlink()
        for page in pages:
            preguntas = self.env['survey.question'].search([
                ('page_id', '=', page.id),
                ('is_page', '=', False)
            ])
            respuesta_cumplimiento = self.env['survey.user_input.line'].search([
                ('user_input_id', '=', user_input.id),
                ('question_id', 'in', preguntas.filtered(lambda q: q.question_type == 'simple_choice').ids)
            ], limit=1)
            respuesta_observaciones = self.env['survey.user_input.line'].search([
                ('user_input_id', '=', user_input.id),
                ('question_id', 'in', preguntas.filtered(lambda q: q.question_type == 'text_box').ids)
            ], limit=1)

            # Solo crear métricas si hay respuestas relevantes en esta página
            if respuesta_cumplimiento or respuesta_observaciones:
                estado = 'na'  # Por defecto N/A (pregunta omitida)
                if respuesta_cumplimiento and respuesta_cumplimiento.answer_type == 'suggestion':
                    suggested_answer = self.env['survey.question.answer'].search([
                        ('id', '=', respuesta_cumplimiento.suggested_answer_id.id)
                    ], limit=1)
                    if suggested_answer and suggested_answer.value:
                        try:
                            valor_raw = suggested_answer.value
                            valor = valor_raw.get('es_EC', '') if isinstance(valor_raw, dict) else valor_raw
                            if valor == 'Cumple':
                                estado = 'cumple'
                            elif valor == 'No cumple':
                                estado = 'no_cumple'
                            # Si no es ninguno de los anteriores, se mantiene como 'na' (pregunta omitida)
                        except Exception as e:
                            _logger.error(f"Error al procesar el valor: {str(e)}")
                            _logger.error(f"Valor que causó el error: {suggested_answer.value}")
                observaciones = ''
                if respuesta_observaciones and respuesta_observaciones.answer_type == 'text_box':
                    observaciones = respuesta_observaciones.value_text_box or ''
                page_title = page.title
                if isinstance(page_title, dict):
                    page_title = page_title.get('es_EC', '')
                self.env['survey.compliance'].create({
                    'calculate_report_id': report.id,
                    'page_id': page.id,
                    'page_name': page_title,
                    'compliance_status': estado,
                    'observations': observaciones
                })
                
        # Actualizar registros de resumen después de crear todas las métricas
        self._update_compliance_summary(user_input.survey_id)

    def _compute_metrics_for_satisfaction(self, report):
        """
        Calcular métricas de satisfacción usando estándar CSAT (Customer Satisfaction Score)
        
        Estándar CSAT:
        - Escala: 1-5
        - Satisfecho: 4-5 (respuestas positivas)
        - Neutral: 3
        - Insatisfecho: 1-2
        
        Métricas calculadas:
        - total_encuestas: Número de respuestas válidas (1-5)
        - encuestas_positivas: Número de respuestas ≥ 4
        - satisfaccion: Promedio de calificaciones
        - porcentaje_satisfaccion: % de respuestas ≥ 4 (CSAT Score)
        """
        user_input = report.user_input_id
        if not user_input:
            _logger.error("No se encontró user_input")
            return

        # Obtener todas las páginas (secciones) de la encuesta
        pages = self.env['survey.question'].search([
            ('survey_id', '=', user_input.survey_id.id),
            ('is_page', '=', True)
        ])

        # Eliminar registros existentes si los hay
        existing_satisfaction = self.env['survey.satisfaction'].search([
            ('calculate_report_id', '=', report.id)
        ])
        if existing_satisfaction:
            existing_satisfaction.unlink()

        for page in pages:
            # Buscar preguntas de satisfacción (simple_choice con valores 1-5) en esta sección
            preguntas_satisfaccion = self.env['survey.question'].search([
                ('page_id', '=', page.id),
                ('is_page', '=', False),
                ('question_type', '=', 'simple_choice')
            ])

            # Buscar pregunta de observaciones (text_box) en esta sección
            pregunta_observaciones = self.env['survey.question'].search([
                ('page_id', '=', page.id),
                ('is_page', '=', False),
                ('question_type', '=', 'text_box')
            ], limit=1)

            # Solo procesar si hay preguntas de satisfacción en esta página
            if preguntas_satisfaccion:
                # ===== VARIABLES BASE PARA CÁLCULOS =====
                total_respuestas = 0          # Contador de respuestas válidas (1-5)
                suma_calificaciones = 0       # Suma de todas las calificaciones
                respuestas_positivas = 0      # Contador de calificaciones ≥ 4 (CSAT)

                for pregunta in preguntas_satisfaccion:
                    respuesta = self.env['survey.user_input.line'].search([
                        ('user_input_id', '=', user_input.id),
                        ('question_id', '=', pregunta.id),
                        ('answer_type', '=', 'suggestion')
                    ], limit=1)

                    if respuesta:
                        suggested_answer = self.env['survey.question.answer'].search([
                            ('id', '=', respuesta.suggested_answer_id.id)
                        ], limit=1)

                        if suggested_answer and suggested_answer.value:
                            try:
                                valor_raw = suggested_answer.value
                                valor = valor_raw.get('es_EC', '') if isinstance(valor_raw, dict) else valor_raw
                                
                                calificacion = int(valor)
                                if 1 <= calificacion <= 5:
                                    # ===== PROCESAMIENTO DE CALIFICACIÓN =====
                                    total_respuestas += 1                    # Incrementar contador de respuestas
                                    suma_calificaciones += calificacion      # Sumar calificación al total
                                    # Estándar CSAT: Satisfecho = 4-5, Neutral = 3, Insatisfecho = 1-2
                                    if calificacion >= 4:
                                        respuestas_positivas += 1            # Incrementar contador de positivas
                                    
                                    # Verificar que la calificación esté en el rango correcto (1-5)
                                    if calificacion < 1 or calificacion > 5:
                                        _logger.warning(f"[SATISFACTION] Valor fuera de rango 1-5: {valor} en pregunta {pregunta.title}")
                                        continue
                            except (ValueError, TypeError) as e:
                                # Ignorar valores que no son numéricos del 1-5
                                _logger.error(f"Error al procesar el valor de satisfacción: {str(e)}")
                                _logger.error(f"Valor que causó el error: {suggested_answer.value}")
                                continue

                # Obtener observaciones si existen
                observaciones = ''
                if pregunta_observaciones:
                    respuesta_observaciones = self.env['survey.user_input.line'].search([
                        ('user_input_id', '=', user_input.id),
                        ('question_id', '=', pregunta_observaciones.id),
                        ('answer_type', '=', 'text_box')
                    ], limit=1)
                    
                    if respuesta_observaciones and respuesta_observaciones.answer_type == 'text_box':
                        observaciones = respuesta_observaciones.value_text_box or ''

                # Solo crear métricas si hay respuestas de satisfacción en esta página
                if total_respuestas > 0 or observaciones:
                    # ===== CÁLCULO DE SATISFACCIÓN =====
                    # promedio_satisfaccion: Promedio aritmético de todas las calificaciones (1-5)
                    # Ejemplo: Si calificó 3.5, entonces promedio_satisfaccion = 3.5
                    promedio_satisfaccion = suma_calificaciones / total_respuestas if total_respuestas > 0 else 0.0
                    
                    # Asegurar que el promedio esté en el rango 1-5
                    promedio_satisfaccion = max(1.0, min(5.0, promedio_satisfaccion))
                    
                    # ===== CÁLCULO DE PORCENTAJE DE SATISFACCIÓN (CSAT) =====
                    # porcentaje_satisfaccion: % de respuestas que son ≥ 4 (estándar CSAT)
                    # Ejemplo: Si calificó 3.5, entonces respuestas_positivas = 0, porcentaje_satisfaccion = 0%
                    # Solo calificaciones 4-5 se consideran "satisfechas" según CSAT
                    porcentaje_satisfaccion = (respuestas_positivas / total_respuestas) * 100 if total_respuestas > 0 else 0.0

                    # Obtener el título de la página
                    page_title = page.title
                    if isinstance(page_title, dict):
                        page_title = page_title.get('es_EC', '')
                    
                    # Log del cálculo final para debugging (solo en debug)
                    # _logger.info(f"[SATISFACTION] Sección: {page_title}, Total respuestas: {total_respuestas}, Suma calificaciones: {suma_calificaciones}, Promedio: {promedio_satisfaccion}")

                    try:
                        vals = {
                            'calculate_report_id': report.id,
                            'page_id': page.id,
                            'page_name': page_title,
                            'total_encuestas': total_respuestas,
                            'encuestas_positivas': respuestas_positivas,
                            'satisfaccion': promedio_satisfaccion,
                            'porcentaje_satisfaccion': porcentaje_satisfaccion,
                            'observations': observaciones
                        }
                        record = self.env['survey.satisfaction'].create(vals)
                        _logger.info(f"Satisfaction record created: {page_title} - Total: {total_respuestas}, Positivas: {respuestas_positivas}, %: {porcentaje_satisfaccion}")
                    except Exception as e:
                        _logger.error(f"Error al crear registro de satisfacción para sección {page_title}: {str(e)}")
                        raise
                
        # Actualizar registros de resumen después de crear todas las métricas
        self._update_satisfaction_summary(user_input.survey_id)

    def _compute_metrics_for_participation(self, report):
        """
        Calcular métricas de participación usando preguntas Sí/No
        
        Métricas calculadas:
        - respuestas_si: Número de respuestas "Sí"
        - respuestas_no: Número de respuestas "No" 
        - no_respondieron: Número de preguntas sin respuesta
        - total_respuestas: Total de preguntas en la sección
        - porcentaje_participacion: % de preguntas respondidas (Sí + No)
        """
        user_input = report.user_input_id
        if not user_input:
            _logger.error("No se encontró user_input")
            return

        # Obtener todas las páginas (secciones) de la encuesta
        pages = self.env['survey.question'].search([
            ('survey_id', '=', user_input.survey_id.id),
            ('is_page', '=', True)
        ])

        # Eliminar registros existentes si los hay
        existing_participation = self.env['survey.participation'].search([
            ('calculate_report_id', '=', report.id)
        ])
        if existing_participation:
            existing_participation.unlink()

        for page in pages:
            # Buscar preguntas de tipo Sí/No en esta sección
            preguntas_si_no = self.env['survey.question'].search([
                ('page_id', '=', page.id),
                ('is_page', '=', False),
                ('question_type', '=', 'simple_choice')
            ])

            # Solo procesar si hay preguntas de tipo Sí/No en esta página
            if preguntas_si_no:
                # ===== VARIABLES BASE PARA CÁLCULOS =====
                respuestas_si = 0          # Contador de respuestas "Sí"
                respuestas_no = 0          # Contador de respuestas "No"
                no_respondieron = 0        # Contador de preguntas sin respuesta
                for pregunta in preguntas_si_no:
                    respuesta = self.env['survey.user_input.line'].search([
                        ('user_input_id', '=', user_input.id),
                        ('question_id', '=', pregunta.id)
                    ], limit=1)
                    if respuesta:
                        if respuesta.answer_type == 'suggestion':
                            suggested_answer = self.env['survey.question.answer'].search([
                                ('id', '=', respuesta.suggested_answer_id.id)
                            ], limit=1)
                            valor = None
                            if suggested_answer and suggested_answer.value:
                                valor_raw = suggested_answer.value
                                valor = valor_raw.get('es_EC', '') if isinstance(valor_raw, dict) else valor_raw
                            # ===== PROCESAMIENTO DE RESPUESTA SÍ/NO =====
                            if valor == 'Sí':
                                respuestas_si += 1          # Incrementar contador de "Sí"
                            elif valor == 'No':
                                respuestas_no += 1          # Incrementar contador de "No"
                            else:
                                no_respondieron += 1        # Incrementar contador de no respondió
                        else:
                            no_respondieron += 1
                    else:
                        no_respondieron += 1
                # ===== CÁLCULO FINAL DE MÉTRICAS =====
                # Los campos total_respuestas y porcentaje_participacion se calculan automáticamente
                # en el modelo SurveyParticipation usando los métodos _compute_totals y _compute_porcentaje_participacion
                
                # Obtener observaciones si existen
                observaciones = ''
                pregunta_observaciones = self.env['survey.question'].search([
                    ('page_id', '=', page.id),
                    ('is_page', '=', False),
                    ('question_type', '=', 'text_box')
                ], limit=1)
                
                if pregunta_observaciones:
                    respuesta_observaciones = self.env['survey.user_input.line'].search([
                        ('user_input_id', '=', user_input.id),
                        ('question_id', '=', pregunta_observaciones.id),
                        ('answer_type', '=', 'text_box')
                    ], limit=1)
                    
                    if respuesta_observaciones and respuesta_observaciones.answer_type == 'text_box':
                        observaciones = respuesta_observaciones.value_text_box or ''
                
                self.env['survey.participation'].create({
                    'calculate_report_id': report.id,
                    'page_id': page.id,
                    'page_name': page.title,
                    'respuestas_si': respuestas_si,
                    'respuestas_no': respuestas_no,
                    'no_respondieron': no_respondieron,
                    'observations': observaciones
                })
                
        # Actualizar registros de resumen después de crear todas las métricas
        self._update_participation_summary(user_input.survey_id)

    @api.model
    def create(self, vals):
        record = super().create(vals)
        if not record.name:
            record.name = f"Participación #{record.id}"
        return record

    def _update_participation_summary(self, survey_id):
        """Actualiza los registros de resumen de participación para una encuesta"""
        try:
            # Obtener todas las métricas de participación para esta encuesta
            metrics = self.env['survey.participation'].search([
                ('survey_id', '=', survey_id.id)
            ])
            
            if not metrics:
                _logger.info(f"No se encontraron métricas de participación para la encuesta {survey_id.title}")
                return
            
            # Eliminar registros de resumen existentes
            existing_summary = self.env['survey.participation.summary'].search([
                ('survey_id', '=', survey_id.id)
            ])
            if existing_summary:
                existing_summary.unlink()
            
            # Crear nuevos registros de resumen
            for metric in metrics:
                summary_record = self.env['survey.participation.summary'].create({
                    'survey_id': survey_id.id,
                    'page_name': metric.page_name,
                    'respuestas_si': metric.respuestas_si,
                    'respuestas_no': metric.respuestas_no,
                    'no_respondieron': metric.no_respondieron,
                    'total_respuestas': metric.total_respuestas,
                    'porcentaje_participacion': metric.porcentaje_participacion,
                    'porcentaje_cumplimiento': metric.porcentaje_cumplimiento,
                    'observations': metric.observations
                    # Los campos de riesgo se calculan automáticamente basados en porcentaje_participacion
                })
            
        except Exception as e:
            _logger.error(f"Error al actualizar resumen de participación para encuesta {survey_id.title}: {str(e)}")