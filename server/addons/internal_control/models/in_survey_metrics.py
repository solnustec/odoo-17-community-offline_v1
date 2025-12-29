# -*- coding: utf-8 -*-
"""
Modelos de métricas de encuestas: revisados, cumplimiento, satisfacción, participación.
Incluye: SurveyRevisedItems, SurveyCompliance, SurveySatisfaction, SurveyParticipation.
"""
from odoo import models, fields, api

def clamp(value, low, high):
    return max(low, min(high, value))

def calcular_riesgo_simplificado(metrica):
    """
    Calcula el nivel de riesgo según el porcentaje de aceptación/cumplimiento.
    Args:
        metrica (float): valor entre 0 y 100.
    Returns:
        dict: Diccionario con clasificación, acción recomendada y valores numéricos.
    """
    if metrica is None or metrica < 0:
        return {
            'clasificacion': 'desconocido',
            'accion': 'Datos insuficientes para evaluar el riesgo. Se requiere información adicional para determinar las acciones necesarias.',
            'probabilidad': 0.0,
            'impacto': 0.0,
            'nivel': 0.0
        }
    
    # Calcular probabilidad basada en el porcentaje de cumplimiento invertido
    # A menor cumplimiento, mayor probabilidad de riesgo
    probabilidad = max(0.5, min(5.0, (100.0 - metrica) / 20.0))
    
    # Calcular impacto basado en el porcentaje de cumplimiento invertido
    # A menor cumplimiento, mayor impacto
    impacto = max(1.0, min(5.0, 5.0 - (metrica / 20.0)))
    
    # Calcular nivel de riesgo como P × I
    nivel = round(probabilidad * impacto, 2)
    nivel = max(0.0, min(25.0, nivel))
    
    # Determinar clasificación basada en el nivel calculado
    if nivel >= 20.0:
        clasificacion = 'extremo'
        accion = 'Plan de acción emergente requerido. Revisión inmediata de controles y procesos. Implementar acciones correctivas urgentes, reforzar supervisión, establecer controles adicionales y definir plazos específicos para la mejora.'
    elif nivel >= 12.0:
        clasificacion = 'alto'
        accion = 'Plan de acción emergente requerido. Revisión inmediata de controles y procesos. Implementar acciones correctivas urgentes, reforzar supervisión, establecer controles adicionales y definir plazos específicos para la mejora.'
    elif nivel >= 6.0:
        clasificacion = 'moderado'
        accion = 'Acciones correctivas necesarias. Implementar controles adicionales. Establecer plan de mejora con fechas límite, aumentar frecuencia de monitoreo y capacitar al personal en áreas críticas.'
    else:
        clasificacion = 'bajo'
        accion = 'Mantener control actual. Seguimiento rutinario. Continuar con las buenas prácticas establecidas, realizar auditorías periódicas y documentar lecciones aprendidas para mantener el alto nivel de cumplimiento.'
    
    return {
        'clasificacion': clasificacion,
        'accion': accion,
        'probabilidad': round(probabilidad, 2),
        'impacto': round(impacto, 2),
        'nivel': nivel
    }

class SurveyRevisedItems(models.Model):
    _name = 'survey.revised.items'
    _description = 'Métricas de Items Revisados'

    calculate_report_id = fields.Many2one('survey.calculate.report', string='Reporte de Cálculo', ondelete='cascade')
    page_id = fields.Many2one('survey.question', string='Sección', domain=[('is_page', '=', True)], ondelete='set null')
    page_name = fields.Char(string='Nombre de Sección')
    total_items_revisados = fields.Integer(string='Total Items Revisados')
    total_items_sin_novedad = fields.Integer(string='Total Items Sin Novedad')
    porcentaje_cumplimiento = fields.Float(string='Porcentaje de Cumplimiento', group_operator='avg')
    observations = fields.Text(string='Observaciones')

    survey_id = fields.Many2one(
        'survey.survey',
        string='Encuesta',
        related='calculate_report_id.user_input_id.survey_id',
        store=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Participante',
        related='calculate_report_id.user_input_id.partner_id',
        store=True
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Departamento',
        related='campaign_id.department_id',
        store=True
    )
    campaign_id = fields.Many2one(
        'in.survey.campaign',
        string='Campaña',
        related='calculate_report_id.user_input_id.campaign_id',
        store=True
    )

class SurveyCompliance(models.Model):
    _name = 'survey.compliance'
    _description = 'Métricas de Cumplimiento'
    calculate_report_id = fields.Many2one('survey.calculate.report', string='Reporte de Cálculo', ondelete='cascade')
    page_id = fields.Many2one('survey.question', string='Sección', domain=[('is_page', '=', True)], ondelete='set null')
    page_name = fields.Char(string='Nombre de Sección')
    compliance_status = fields.Selection([
        ('cumple', 'Cumple'),
        ('no_cumple', 'No Cumple'),
        ('na', 'N/A')
    ], string='Estado')
    observations = fields.Text(string='Observaciones')
    porcentaje_cumplimiento = fields.Float(
        string='Porcentaje de Cumplimiento',
        compute='_compute_porcentaje_cumplimiento',
        store=True,
        group_operator='avg'
    )
    survey_id = fields.Many2one('survey.survey', string='Encuesta', related='calculate_report_id.user_input_id.survey_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Participante', related='calculate_report_id.user_input_id.partner_id', store=True)
    department_id = fields.Many2one('hr.department', string='Departamento', related='campaign_id.department_id', store=True)
    campaign_id = fields.Many2one(
        'in.survey.campaign',
        string='Campaña',
        related='calculate_report_id.user_input_id.campaign_id',
        store=True
    )

    @api.depends('compliance_status')
    def _compute_porcentaje_cumplimiento(self):
        for record in self:
            if record.compliance_status == 'cumple':
                record.porcentaje_cumplimiento = 100.0
            elif record.compliance_status == 'no_cumple':
                record.porcentaje_cumplimiento = 0.0
            else:
                record.porcentaje_cumplimiento = 0.0

class SurveyComplianceSummary(models.Model):
    _name = 'survey.compliance.summary'
    _description = 'Resumen de Cumplimiento Agrupado por Sección'
    _rec_name = 'page_name'

    survey_id = fields.Many2one('survey.survey', string='Encuesta', required=True)
    page_name = fields.Char(string='Nombre de Sección', required=True)
    compliance_status = fields.Selection([('cumple','Cumple'),('no_cumple','No Cumple'),('na','N/A')], string='Estado General')
    total_responses = fields.Integer(string='Total Respuestas', default=0)
    cumple_count = fields.Integer(string='Cantidad Cumple', default=0)
    no_cumple_count = fields.Integer(string='Cantidad No Cumple', default=0)
    na_count = fields.Integer(string='Cantidad N/A', default=0)

    porcentaje_cumplimiento = fields.Float(
        string='Porcentaje de Cumplimiento',
        compute='_compute_porcentaje_cumplimiento',
        store=True
    )

    observations = fields.Text(string='Observaciones')
    department_id = fields.Many2one('hr.department', string='Departamento')
    campaign_id = fields.Many2one('in.survey.campaign', string='Campaña')

    total_asignados = fields.Integer(string='Personas Asignadas', default=0)
    total_respondieron = fields.Integer(string='Personas que Respondieron', default=0)
    participation_percentage = fields.Float(string='% Participación', default=0.0)

    hallazgos_auditoria = fields.Integer(string='Hallazgos de Auditoría', default=0)
    severidad_incumplimiento = fields.Selection([
        ('1','Muy Baja'),('2','Baja'),('3','Moderada'),('4','Alta'),('5','Muy Alta')
    ], string='Severidad de Incumplimiento', default='1')
    frecuencia_incumplimiento = fields.Selection([('anual','Anual'),('trimestral','Trimestral'),('mensual','Mensual')],
                                                string='Frecuencia de Incumplimiento', default='anual')

    probabilidad_riesgo = fields.Float(string='Probabilidad de Riesgo', compute='_compute_riesgo', store=True)
    impacto_riesgo = fields.Float(string='Impacto de Riesgo', compute='_compute_riesgo', store=True)
    nivel_riesgo = fields.Float(string='Nivel de Riesgo', compute='_compute_riesgo', store=True)

    probabilidad_porcentaje = fields.Float(string='% Probabilidad', compute='_compute_riesgo', store=True)
    impacto_porcentaje = fields.Float(string='% Impacto', compute='_compute_riesgo', store=True)
    nivel_riesgo_porcentaje = fields.Float(string='% Nivel de Riesgo', compute='_compute_riesgo', store=True)

    clasificacion_riesgo = fields.Selection([
        ('extremo','Riesgo Extremo'),('alto','Riesgo Alto'),('moderado','Riesgo Moderado'),('bajo','Riesgo Bajo')
    ], string='Clasificación de Riesgo', compute='_compute_riesgo', store=True)

    accion_recomendada = fields.Text(string='Acción Recomendada', compute='_compute_riesgo', store=True)

    @api.depends('total_responses', 'cumple_count')
    def _compute_porcentaje_cumplimiento(self):
        for rec in self:
            if rec.total_responses and rec.total_responses > 0:
                rec.porcentaje_cumplimiento = round((rec.cumple_count / rec.total_responses) * 100.0, 1)
            else:
                rec.porcentaje_cumplimiento = 0.0

    @api.depends('porcentaje_cumplimiento')
    def _compute_riesgo(self):
        """
        Calcula el nivel de riesgo según el porcentaje de cumplimiento/aceptación.
        Lógica simplificada basada en rangos de porcentaje:
        - Riesgo Alto: < 60% de aceptación
        - Riesgo Medio: >= 60% y < 85% de aceptación  
        - Riesgo Bajo: >= 85% de aceptación
        """
        for rec in self:
            pct = float(rec.porcentaje_cumplimiento or 0.0)
            
            # Usar función auxiliar para calcular riesgo
            riesgo_data = calcular_riesgo_simplificado(pct)
            
            # Asignar valores calculados
            rec.clasificacion_riesgo = riesgo_data['clasificacion']
            rec.accion_recomendada = riesgo_data['accion']
            rec.probabilidad_riesgo = riesgo_data['probabilidad']
            rec.impacto_riesgo = riesgo_data['impacto']
            rec.nivel_riesgo = riesgo_data['nivel']
            
            # Calcular porcentajes para el reporte
            rec.probabilidad_porcentaje = round((rec.probabilidad_riesgo / 5.0) * 100.0, 1)
            rec.impacto_porcentaje = round((rec.impacto_riesgo / 5.0) * 100.0, 1)
            rec.nivel_riesgo_porcentaje = round((rec.nivel_riesgo / 25.0) * 100.0, 1)

class SurveyRevisedItemsSummary(models.Model):
    _name = 'survey.revised.items.summary'
    _description = 'Resumen de Items Revisados Agrupado por Sección'
    _rec_name = 'page_name'

    survey_id = fields.Many2one('survey.survey', string='Encuesta', required=True)
    page_name = fields.Char(string='Nombre de Sección', required=True)
    total_items_revisados = fields.Integer(string='Total Items Revisados', default=0)
    total_items_sin_novedad = fields.Integer(string='Total Items Sin Novedad', default=0)
    porcentaje_cumplimiento = fields.Float(string='Porcentaje de Cumplimiento', default=0.0)
    observations = fields.Text(string='Observaciones')
    department_id = fields.Many2one('hr.department', string='Departamento')
    campaign_id = fields.Many2one('in.survey.campaign', string='Campaña')
    
    # Campos estandarizados para tabla de campaña
    total_asignados = fields.Integer(string='Personas Asignadas', default=0)
    total_respondieron = fields.Integer(string='Personas que Respondieron', default=0)
    participation_percentage = fields.Float(string='% Participación', default=0.0)
    
    # Campos para cálculo de riesgo
    probabilidad_riesgo = fields.Float(string='Probabilidad de Riesgo', compute='_compute_riesgo', store=True)
    impacto_riesgo = fields.Float(string='Impacto de Riesgo', compute='_compute_riesgo', store=True)
    nivel_riesgo = fields.Float(string='Nivel de Riesgo', compute='_compute_riesgo', store=True)

    probabilidad_porcentaje = fields.Float(string='% Probabilidad', compute='_compute_riesgo', store=True)
    impacto_porcentaje = fields.Float(string='% Impacto', compute='_compute_riesgo', store=True)
    nivel_riesgo_porcentaje = fields.Float(string='% Nivel de Riesgo', compute='_compute_riesgo', store=True)

    clasificacion_riesgo = fields.Selection([
        ('extremo','Riesgo Extremo'),('alto','Riesgo Alto'),('moderado','Riesgo Moderado'),('bajo','Riesgo Bajo')
    ], string='Clasificación de Riesgo', compute='_compute_riesgo', store=True)

    accion_recomendada = fields.Text(string='Acción Recomendada', compute='_compute_riesgo', store=True)

    @api.depends('total_items_revisados', 'total_items_sin_novedad')
    def _compute_porcentaje_cumplimiento(self):
        for record in self:
            if record.total_items_revisados > 0:
                record.porcentaje_cumplimiento = (record.total_items_sin_novedad / record.total_items_revisados) * 100
            else:
                record.porcentaje_cumplimiento = 0.0

    @api.depends('porcentaje_cumplimiento')
    def _compute_riesgo(self):
        """
        Calcula el nivel de riesgo según el porcentaje de cumplimiento de items revisados.
        Lógica simplificada basada en rangos de porcentaje:
        - Riesgo Alto: < 60% de aceptación
        - Riesgo Medio: >= 60% y < 85% de aceptación  
        - Riesgo Bajo: >= 85% de aceptación
        """
        for rec in self:
            pct = float(rec.porcentaje_cumplimiento or 0.0)
            
            # Usar función auxiliar para calcular riesgo
            riesgo_data = calcular_riesgo_simplificado(pct)
            
            # Asignar valores calculados
            rec.clasificacion_riesgo = riesgo_data['clasificacion']
            rec.accion_recomendada = riesgo_data['accion']
            rec.probabilidad_riesgo = riesgo_data['probabilidad']
            rec.impacto_riesgo = riesgo_data['impacto']
            rec.nivel_riesgo = riesgo_data['nivel']
            
            # Calcular porcentajes para el reporte
            rec.probabilidad_porcentaje = round((rec.probabilidad_riesgo / 5.0) * 100.0, 1)
            rec.impacto_porcentaje = round((rec.impacto_riesgo / 5.0) * 100.0, 1)
            rec.nivel_riesgo_porcentaje = round((rec.nivel_riesgo / 25.0) * 100.0, 1)

class SurveySatisfaction(models.Model):
    _name = 'survey.satisfaction'
    _description = 'Métricas de Satisfacción'
    calculate_report_id = fields.Many2one('survey.calculate.report', string='Reporte de Cálculo', ondelete='cascade')
    page_id = fields.Many2one('survey.question', string='Sección', domain=[('is_page', '=', True)], ondelete='set null')
    page_name = fields.Char(string='Nombre de Sección')
    total_encuestas = fields.Integer(string='Total Encuestas')
    encuestas_positivas = fields.Integer(string='Encuestas Positivas')
    satisfaccion = fields.Float(string='Satisfacción', group_operator='avg')
    porcentaje_satisfaccion = fields.Float(string='Porcentaje de Satisfacción', group_operator='avg')
    porcentaje_cumplimiento = fields.Float(string='Porcentaje de Cumplimiento', compute='_compute_porcentaje_cumplimiento', store=True)
    survey_id = fields.Many2one('survey.survey', string='Encuesta', related='calculate_report_id.user_input_id.survey_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Participante', related='calculate_report_id.user_input_id.partner_id', store=True)
    department_id = fields.Many2one('hr.department', string='Departamento', related='campaign_id.department_id', store=True)
    anonymous_token = fields.Char()
    campaign_id = fields.Many2one(
        'in.survey.campaign',
        string='Campaña',
        related='calculate_report_id.user_input_id.campaign_id',
        store=True
    )
    observations = fields.Text(string='Observaciones')

    @api.depends('total_encuestas')
    def _compute_porcentaje_cumplimiento(self):
        for record in self:
            # Si hay encuestas totales, significa que respondió la sección (cumple)
            if record.total_encuestas > 0:
                record.porcentaje_cumplimiento = 100.0
            else:
                record.porcentaje_cumplimiento = 0.0

class SurveySatisfactionSummary(models.Model):
    _name = 'survey.satisfaction.summary'
    _description = 'Resumen de Satisfacción Agrupado por Sección'
    _rec_name = 'page_name'

    survey_id = fields.Many2one('survey.survey', string='Encuesta', required=True)
    page_name = fields.Char(string='Nombre de Sección', required=True)
    total_encuestas = fields.Integer(string='Total Encuestas', default=0)
    encuestas_positivas = fields.Integer(string='Encuestas Positivas', default=0)
    satisfaccion = fields.Float(string='Satisfacción', default=0.0, group_operator='avg')
    porcentaje_satisfaccion = fields.Float(string='Porcentaje de Satisfacción', default=0.0)
    porcentaje_cumplimiento = fields.Float(string='Porcentaje de Cumplimiento', default=0.0)
    observations = fields.Text(string='Observaciones')
    department_id = fields.Many2one('hr.department', string='Departamento')
    campaign_id = fields.Many2one('in.survey.campaign', string='Campaña')
    
    # Campos estandarizados para tabla de campaña
    total_asignados = fields.Integer(string='Personas Asignadas', default=0)
    total_respondieron = fields.Integer(string='Personas que Respondieron', default=0)
    participation_percentage = fields.Float(string='% Participación', default=0.0)

    # Campos para cálculo de riesgo
    probabilidad_riesgo = fields.Float(string='Probabilidad de Riesgo', compute='_compute_riesgo', store=True)
    impacto_riesgo = fields.Float(string='Impacto de Riesgo', compute='_compute_riesgo', store=True)
    nivel_riesgo = fields.Float(string='Nivel de Riesgo', compute='_compute_riesgo', store=True)

    probabilidad_porcentaje = fields.Float(string='% Probabilidad', compute='_compute_riesgo', store=True)
    impacto_porcentaje = fields.Float(string='% Impacto', compute='_compute_riesgo', store=True)
    nivel_riesgo_porcentaje = fields.Float(string='% Nivel de Riesgo', compute='_compute_riesgo', store=True)

    clasificacion_riesgo = fields.Selection([
        ('extremo','Riesgo Extremo'),('alto','Riesgo Alto'),('moderado','Riesgo Moderado'),('bajo','Riesgo Bajo')
    ], string='Clasificación de Riesgo', compute='_compute_riesgo', store=True)

    accion_recomendada = fields.Text(string='Acción Recomendada', compute='_compute_riesgo', store=True)

    @api.depends('total_encuestas', 'encuestas_positivas')
    def _compute_porcentaje_satisfaccion(self):
        for record in self:
            if record.total_encuestas > 0:
                record.porcentaje_satisfaccion = (record.encuestas_positivas / record.total_encuestas) * 100
            else:
                record.porcentaje_satisfaccion = 0.0

    @api.depends('total_encuestas')
    def _compute_porcentaje_cumplimiento(self):
        for record in self:
            # Si hay encuestas totales, significa que respondió la sección (cumple)
            if record.total_encuestas > 0:
                record.porcentaje_cumplimiento = 100.0
            else:
                record.porcentaje_cumplimiento = 0.0

    @api.depends('porcentaje_satisfaccion')
    def _compute_riesgo(self):
        """
        Calcula el nivel de riesgo según el porcentaje de satisfacción.
        Lógica simplificada basada en rangos de porcentaje:
        - Riesgo Alto: < 60% de satisfacción
        - Riesgo Medio: >= 60% y < 85% de satisfacción
        - Riesgo Bajo: >= 85% de satisfacción
        """
        for rec in self:
            pct = float(rec.porcentaje_satisfaccion or 0.0)

            # Usar función auxiliar para calcular riesgo
            riesgo_data = calcular_riesgo_simplificado(pct)

            # Asignar valores calculados
            rec.clasificacion_riesgo = riesgo_data['clasificacion']
            rec.accion_recomendada = riesgo_data['accion']
            rec.probabilidad_riesgo = riesgo_data['probabilidad']
            rec.impacto_riesgo = riesgo_data['impacto']
            rec.nivel_riesgo = riesgo_data['nivel']

            # Calcular porcentajes para el reporte
            rec.probabilidad_porcentaje = round((rec.probabilidad_riesgo / 5.0) * 100.0, 1)
            rec.impacto_porcentaje = round((rec.impacto_riesgo / 5.0) * 100.0, 1)
            rec.nivel_riesgo_porcentaje = round((rec.nivel_riesgo / 25.0) * 100.0, 1)

class SurveyParticipation(models.Model):
    _name = 'survey.participation'
    _description = 'Métricas de Participación (Sí/No/No respondió)'
    calculate_report_id = fields.Many2one('survey.calculate.report', string='Reporte de Cálculo', ondelete='cascade')
    page_id = fields.Many2one('survey.question', string='Sección', domain=[('is_page', '=', True)], ondelete='set null')
    page_name = fields.Char(string='Nombre de Sección')
    respuestas_si = fields.Integer(string='Sí', default=0)
    respuestas_no = fields.Integer(string='No', default=0)
    no_respondieron = fields.Integer(string='No respondió', default=0)
    total_respuestas = fields.Integer(string='Total Respuestas', compute='_compute_totals', store=True)
    porcentaje_participacion = fields.Float(string='% de Participación', compute='_compute_porcentaje_participacion', store=True, group_operator='avg')
    observations = fields.Text(string='Observaciones')
    survey_id = fields.Many2one('survey.survey', string='Encuesta', related='calculate_report_id.user_input_id.survey_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Participante', related='calculate_report_id.user_input_id.partner_id', store=True)
    department_id = fields.Many2one('hr.department', string='Departamento', related='campaign_id.department_id', store=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', related='calculate_report_id.user_input_id.employee_id', store=True)
    anonymous_token = fields.Char()
    campaign_id = fields.Many2one(
        'in.survey.campaign',
        string='Campaña',
        related='calculate_report_id.user_input_id.campaign_id',
        store=True
    )

    @api.depends('respuestas_si', 'respuestas_no', 'no_respondieron')
    def _compute_totals(self):
        for record in self:
            record.total_respuestas = record.respuestas_si + record.respuestas_no + record.no_respondieron

    @api.depends('respuestas_si', 'respuestas_no', 'total_respuestas')
    def _compute_porcentaje_participacion(self):
        for record in self:
            if record.total_respuestas > 0:
                # % Participación = (Sí / Total) × 100
                # Muestra qué porcentaje de preguntas fueron respondidas con "Sí"
                record.porcentaje_participacion = (record.respuestas_si / record.total_respuestas) * 100
            else:
                record.porcentaje_participacion = 0.0


class SurveyParticipationSummary(models.Model):
    _name = 'survey.participation.summary'
    _description = 'Resumen de Participación Agrupado por Sección'
    _rec_name = 'page_name'

    survey_id = fields.Many2one('survey.survey', string='Encuesta', required=True)
    page_name = fields.Char(string='Nombre de Sección', required=True)
    respuestas_si = fields.Integer(string='Sí', default=0)
    respuestas_no = fields.Integer(string='No', default=0)
    no_respondieron = fields.Integer(string='No respondió', default=0)
    total_respuestas = fields.Integer(string='Total Respuestas', default=0)
    porcentaje_participacion = fields.Float(string='% de Participación', default=0.0)
    porcentaje_cumplimiento = fields.Float(string='Porcentaje de Cumplimiento', default=0.0)
    observations = fields.Text(string='Observaciones')
    department_id = fields.Many2one('hr.department', string='Departamento')
    campaign_id = fields.Many2one('in.survey.campaign', string='Campaña')
    
    # Campos estandarizados para tabla de campaña
    total_asignados = fields.Integer(string='Personas Asignadas', default=0)
    total_respondieron = fields.Integer(string='Personas que Respondieron', default=0)
    participation_percentage = fields.Float(string='% Participación', default=0.0)

    # Campos para cálculo de riesgo
    probabilidad_riesgo = fields.Float(string='Probabilidad de Riesgo', compute='_compute_riesgo', store=True)
    impacto_riesgo = fields.Float(string='Impacto de Riesgo', compute='_compute_riesgo', store=True)
    nivel_riesgo = fields.Float(string='Nivel de Riesgo', compute='_compute_riesgo', store=True)

    probabilidad_porcentaje = fields.Float(string='% Probabilidad', compute='_compute_riesgo', store=True)
    impacto_porcentaje = fields.Float(string='% Impacto', compute='_compute_riesgo', store=True)
    nivel_riesgo_porcentaje = fields.Float(string='% Nivel de Riesgo', compute='_compute_riesgo', store=True)

    clasificacion_riesgo = fields.Selection([
        ('extremo','Riesgo Extremo'),('alto','Riesgo Alto'),('moderado','Riesgo Moderado'),('bajo','Riesgo Bajo')
    ], string='Clasificación de Riesgo', compute='_compute_riesgo', store=True)

    accion_recomendada = fields.Text(string='Acción Recomendada', compute='_compute_riesgo', store=True)

    @api.depends('respuestas_si', 'respuestas_no', 'no_respondieron')
    def _compute_totals(self):
        for record in self:
            record.total_respuestas = record.respuestas_si + record.respuestas_no + record.no_respondieron

    @api.depends('respuestas_si', 'respuestas_no', 'total_respuestas')
    def _compute_porcentaje_participacion(self):
        for record in self:
            if record.total_respuestas > 0:
                # % Participación = (Sí / Total) × 100
                # Muestra qué porcentaje de preguntas fueron respondidas con "Sí"
                record.porcentaje_participacion = (record.respuestas_si / record.total_respuestas) * 100
            else:
                record.porcentaje_participacion = 0.0

    @api.depends('total_respuestas')
    def _compute_porcentaje_cumplimiento(self):
        for record in self:
            # Si hay respuestas totales, significa que respondió la sección (cumple)
            if record.total_respuestas > 0:
                record.porcentaje_cumplimiento = 100.0
            else:
                record.porcentaje_cumplimiento = 0.0

    @api.depends('porcentaje_participacion')
    def _compute_riesgo(self):
        """
        Calcula el nivel de riesgo según el porcentaje de participación.
        Lógica simplificada basada en rangos de porcentaje:
        - Riesgo Alto: < 60% de participación
        - Riesgo Medio: >= 60% y < 85% de participación
        - Riesgo Bajo: >= 85% de participación
        """
        for rec in self:
            pct = float(rec.porcentaje_participacion or 0.0)

            # Usar función auxiliar para calcular riesgo
            riesgo_data = calcular_riesgo_simplificado(pct)

            # Asignar valores calculados
            rec.clasificacion_riesgo = riesgo_data['clasificacion']
            rec.accion_recomendada = riesgo_data['accion']
            rec.probabilidad_riesgo = riesgo_data['probabilidad']
            rec.impacto_riesgo = riesgo_data['impacto']
            rec.nivel_riesgo = riesgo_data['nivel']

            # Calcular porcentajes para el reporte
            rec.probabilidad_porcentaje = round((rec.probabilidad_riesgo / 5.0) * 100.0, 1)
            rec.impacto_porcentaje = round((rec.impacto_riesgo / 5.0) * 100.0, 1)
            rec.nivel_riesgo_porcentaje = round((rec.nivel_riesgo / 25.0) * 100.0, 1)

