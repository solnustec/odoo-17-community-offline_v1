# -*- coding: utf-8 -*-
"""
Herencia de survey.survey, modelos de categoría y etiquetas de encuestas.
Incluye: SurveySurvey, SurveyCategory, SurveyTag.
"""
from odoo import models, fields, api, _
import logging
from odoo.exceptions import UserError
import base64
import json
import re

_logger = logging.getLogger(__name__)

class SurveySurvey(models.Model):
    _inherit = 'survey.survey'

    # Campo survey_type heredado de Odoo Survey (Selection: survey, live_session, assessment, custom)
    category_id = fields.Many2one('survey.category', string='Categoría', required=False)
    tag_ids = fields.Many2many('survey.tag', string='Etiquetas')
    is_anonymous = fields.Boolean(string='Encuesta Anónima', default=False)

    start_date = fields.Datetime(string='Fecha de Inicio')
    end_date = fields.Datetime(string='Fecha de Fin')
    department_id = fields.Many2one('hr.department', string='Departamento')
    
    is_survey_manager = fields.Boolean(string='Es Survey Manager', compute='_compute_is_survey_manager', store=False)
    
    is_department_locked = fields.Boolean(string='Departamento Bloqueado', default=False, help='Indica si el departamento ya no puede ser modificado')

    questions_layout = fields.Selection(
        [
            ('one_page', 'All questions on one page'),
            ('page_per_section', 'Page per section'),
            ('page_per_question', 'Page per question'),
        ],
        string='Questions Layout',
        default=lambda self: self._default_questions_layout(),
    )

    def _default_questions_layout(self):
        """Retorna el layout por defecto basado en si tiene categoría"""
        # Si tiene categoría, usar page_per_section, sino one_page
        return 'page_per_section' if self.category_id else 'one_page'

    @api.model
    def default_get(self, fields_list):
        """Establecer valores por defecto, incluyendo el departamento para survey managers"""
        res = super().default_get(fields_list)
        
        # Si el usuario es survey manager, establecer su departamento por defecto
        if self.env.user.has_group('survey.group_survey_manager'):
            user_employee = self.env.user.employee_id
            if user_employee and user_employee.department_id and 'department_id' in fields_list:
                res['department_id'] = user_employee.department_id.id
                # Marcar que el departamento está bloqueado desde el inicio para survey managers
                res['is_department_locked'] = True
            # Asegurar que is_department_locked se establezca incluso si no hay department_id en fields_list
            if 'is_department_locked' in fields_list:
                res['is_department_locked'] = True
        
        return res

    def _compute_is_survey_manager(self):
        """Computar si el usuario actual es survey manager"""
        is_manager = self.env.user.has_group('survey.group_survey_manager')
        for record in self:
            record.is_survey_manager = is_manager

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """Actualizar el layout cuando cambie la categoría"""
        if self.category_id:
            # Si se asigna una categoría, usar page_per_section
            self.questions_layout = 'page_per_section'
        else:
            # Si se quita la categoría, usar one_page
            self.questions_layout = 'one_page'

    def is_active(self):
        """Verificar si la encuesta está activa según las fechas"""
        self.ensure_one()
        now = fields.Datetime.now()
        
        if not self.start_date and not self.end_date:
            return True
            
        # Verificar fecha de inicio
        if self.start_date and now < self.start_date:
            return False
            
        # Verificar fecha de fin
        if self.end_date and now > self.end_date:
            return False
            
        return True

    def action_create_survey_by_category(self):
        """Abre el wizard para crear encuestas por categoría"""
        return {
            'name': _('Crear Encuesta por Categoría'),
            'type': 'ir.actions.act_window',
            'res_model': 'survey.create.by.category.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {},
        }

    def action_export_results(self):
        """Abre el wizard para exportar resultados de la encuesta"""
        self.ensure_one()
        return {
            'name': _('Exportar Resultados'),
            'type': 'ir.actions.act_window',
            'res_model': 'survey.export.report',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_survey_id': self.id,
            }
        }

    def action_exportar_estructura(self):
        """Exporta la estructura de la encuesta como JSON (sin respuestas de usuarios)"""
        self.ensure_one()
        datos = {}
        datos['encuesta'] = {
            'title': self.title,
            'description': self.description,
            'category': self.category_id and {
                'name': self.category_id.name,
                'code': self.category_id.code,
                'description': self.category_id.description,
            } or {},
            'tags': [
                {'name': tag.name, 'color': tag.color}
                for tag in self.tag_ids
            ],
            'questions': []
        }
        questions = self.env['survey.question'].search([('survey_id', '=', self.id)])
        for q in questions:
            question_data = {
                'title': q.title,
                'description': q.description,
                'question_type': q.question_type,
                'sequence': q.sequence,
                'is_page': q.is_page,
                'matrix_subtype': q.matrix_subtype,
                'question_placeholder': q.question_placeholder,
                'comments_message': q.comments_message,
                'validation_error_msg': q.validation_error_msg,
                'constr_error_msg': q.constr_error_msg,
                'is_scored_question': q.is_scored_question,
                'save_as_email': q.save_as_email,
                'save_as_nickname': q.save_as_nickname,
                'is_time_limited': q.is_time_limited,
                'comments_allowed': q.comments_allowed,
                'comment_count_as_answer': q.comment_count_as_answer,
                'validation_required': q.validation_required,
                'validation_email': q.validation_email,
                'constr_mandatory': q.constr_mandatory,
                'answer_numerical_box': q.answer_numerical_box,
                'answer_score': q.answer_score,
                'validation_length_min': q.validation_length_min,
                'validation_length_max': q.validation_length_max,
                'validation_min_date': q.validation_min_date,
                'validation_max_date': q.validation_max_date,
                'validation_min_float_value': q.validation_min_float_value,
                'validation_max_float_value': q.validation_max_float_value,
                'answers': []
            }
            answers = self.env['survey.question.answer'].search([('question_id', '=', q.id)])
            for a in answers:
                answer_data = {
                    'value': a.value,
                    'is_correct': getattr(a, 'is_correct', False),
                    'suggested_score': getattr(a, 'suggested_score', 0),
                    'sequence': a.sequence,
                }
                question_data['answers'].append(answer_data)
            datos['encuesta']['questions'].append(question_data)
        # Generar archivo JSON
        json_data = json.dumps(datos, ensure_ascii=False, indent=2, default=str)
        # Nombre del archivo: solo el nombre de la encuesta, sin espacios, minúsculas
        nombre = self.title
        if isinstance(nombre, dict):
            nombre = nombre.get('es_EC') or nombre.get('en_US') or list(nombre.values())[0]
        nombre_archivo = re.sub(r'\W+', '_', nombre).lower() + '.json'
        # Crear adjunto temporal
        adjunto = self.env['ir.attachment'].create({
            'name': nombre_archivo,
            'type': 'binary',
            'datas': base64.b64encode(json_data.encode('utf-8')),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/json',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{adjunto.id}?download=true',
            'target': 'self',
        }

class SurveyCreateByCategoryWizard(models.TransientModel):
    _name = 'survey.create.by.category.wizard'
    _description = 'Wizard para crear encuestas por categoría'

    name = fields.Char(string='Nombre de la Encuesta', required=True)
    description = fields.Text(string='Descripción')
    category_id = fields.Many2one('survey.category', string='Categoría', required=True)
    

    section_method = fields.Selection([
        ('manual', 'Agregar Secciones Manualmente'),
        ('file', 'Cargar Secciones desde Archivo')
    ], string='Método de Creación', default='manual', required=True)
    

    num_sections = fields.Integer(string='Número de Secciones', default=1, min=1, max=100)
    

    section_file = fields.Binary(string='Archivo de Secciones', attachment=True)
    section_filename = fields.Char(string='Nombre del Archivo')
    
    department_id = fields.Many2one('hr.department', string='Departamento')
    is_anonymous = fields.Boolean(string='Encuesta Anónima', default=False)
    
    # Opciones adicionales para la encuesta
    add_file_question_per_section = fields.Boolean(string='Agregar pregunta de archivo a cada sección', default=False, 
                                                   help='Agrega una pregunta de tipo "Subir archivo" al final de cada sección')
    add_image_section_at_end = fields.Boolean(string='Agregar sección final con pregunta de imagen', default=False,
                                             help='Agrega una sección final con una pregunta de tipo "Subir imagen"')
    
    # Campo computado para detectar si el usuario es survey manager
    is_survey_manager = fields.Boolean(string='Es Survey Manager', compute='_compute_is_survey_manager', store=False)
    
    # Campo para controlar si el departamento es editable
    is_department_locked = fields.Boolean(string='Departamento Bloqueado', default=False, help='Indica si el departamento ya no puede ser modificado')

    @api.model
    def default_get(self, fields_list):
        """Establecer valores por defecto, incluyendo el departamento para survey managers"""
        res = super().default_get(fields_list)
        
        # Si el usuario es survey manager, establecer su departamento por defecto
        if self.env.user.has_group('survey.group_survey_manager'):
            user_employee = self.env.user.employee_id
            if user_employee and user_employee.department_id and 'department_id' in fields_list:
                res['department_id'] = user_employee.department_id.id
                # Marcar que el departamento está bloqueado desde el inicio para survey managers
                res['is_department_locked'] = True
            # Asegurar que is_department_locked se establezca incluso si no hay department_id en fields_list
            if 'is_department_locked' in fields_list:
                res['is_department_locked'] = True
        
        return res

    def _compute_is_survey_manager(self):
        """Computar si el usuario actual es survey manager"""
        is_manager = self.env.user.has_group('survey.group_survey_manager')
        for record in self:
            record.is_survey_manager = is_manager

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """Actualizar descripción según la categoría seleccionada"""
        if self.category_id:
            if self.category_id.code == 'revision_items':
                self.description = 'Encuesta para revisión de items y auditoría'
            elif self.category_id.code == 'compliance':
                self.description = 'Encuesta para evaluación de cumplimiento normativo'
            elif self.category_id.code == 'satisfaction':
                self.description = 'Encuesta para medir satisfacción de usuarios'
            elif self.category_id.code == 'participation':
                self.description = 'Encuesta para medir participación y engagement'

    @api.onchange('section_method')
    def _onchange_section_method(self):

        if self.section_method == 'manual':
            self.section_file = False
            self.section_filename = False
        else:
            self.num_sections = 1

    def _process_section_file(self):
        """Procesar archivo de secciones y retornar lista de nombres"""
        if not self.section_file:
            raise UserError(_('Por favor, seleccione un archivo.'))
        
        import base64
        import csv
        import io
        from xlrd import open_workbook
        
        file_content = base64.b64decode(self.section_file)
        section_names = []
        
        # Determinar tipo de archivo por extensión
        filename = self.section_filename or ''
        
        if filename.lower().endswith('.csv'):
            # Procesar CSV
            try:
                csv_content = file_content.decode('utf-8')
                csv_reader = csv.reader(io.StringIO(csv_content))
                for row in csv_reader:
                    if row and row[0].strip():  # Ignorar filas vacías
                        section_names.append(row[0].strip())
            except Exception as e:
                raise UserError(_('Error al procesar archivo CSV: %s') % str(e))
                
        elif filename.lower().endswith(('.xlsx', '.xls')):
            # Procesar Excel
            try:
                workbook = open_workbook(file_contents=file_content)
                sheet = workbook.sheet_by_index(0)  # Primera hoja
                for row_idx in range(sheet.nrows):
                    cell_value = sheet.cell_value(row_idx, 0)
                    if cell_value and str(cell_value).strip():
                        section_names.append(str(cell_value).strip())
            except Exception as e:
                raise UserError(_('Error al procesar archivo Excel: %s') % str(e))
        else:
            raise UserError(_('Formato de archivo no soportado. Use CSV o Excel (.xlsx, .xls)'))
        
        if not section_names:
            raise UserError(_('No se encontraron nombres de secciones en el archivo.'))
        
        return section_names

    def _create_survey_from_sections(self, survey, section_names):
        """Crear encuesta con secciones personalizadas según la categoría"""
        for i, section_name in enumerate(section_names, 1):
            # Crear sección
            section = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': section_name,
                'is_page': True,
                'sequence': i * 10,
            })
            
            # Crear preguntas según la categoría
            if self.category_id.code == 'revision_items':
                self._create_revision_items_questions(survey, section, i)
            elif self.category_id.code == 'compliance':
                self._create_compliance_questions(survey, section, i)
            elif self.category_id.code == 'satisfaction':
                self._create_satisfaction_questions(survey, section, i)
            elif self.category_id.code == 'participation':
                self._create_participation_questions(survey, section, i)
            
            # Agregar pregunta de archivo si está habilitada
            self._add_file_question_to_section(survey, section, i * 10)
        
        # Agregar sección final con imagen si está habilitada
        self._add_image_section_at_end(survey, len(section_names))

    def _create_revision_items_questions(self, survey, section, section_num):
        """Crear preguntas para sección de items revisados"""
        # Pregunta de cumplimiento
        question_compliance = self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Cumplimiento',
            'question_type': 'simple_choice',
            'page_id': section.id,
            'sequence': section_num * 10 + 1,
            'constr_mandatory': True,
        })
        
        # Opciones de respuesta
        self.env['survey.question.answer'].create([
            {'question_id': question_compliance.id, 'value': 'Cumple'},
            {'question_id': question_compliance.id, 'value': 'No cumple'},
        ])
        
        # Pregunta de items revisados (numerical_box)
        self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Ítems Revisados',
            'question_type': 'numerical_box',
            'page_id': section.id,
            'sequence': section_num * 10 + 2,
            'constr_mandatory': True,
        })
        
        # Pregunta de items sin novedad (numerical_box)
        self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Ítems Revisados Sin Novedad',
            'question_type': 'numerical_box',
            'page_id': section.id,
            'sequence': section_num * 10 + 3,
            'constr_mandatory': True,
        })

    def _create_compliance_questions(self, survey, section, section_num):
        """Crear preguntas para sección de cumplimiento"""
        # Pregunta de evaluación
        question_eval = self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Cumplimiento',
            'question_type': 'simple_choice',
            'page_id': section.id,
            'sequence': section_num * 10 + 1,
            'constr_mandatory': True,
        })
        
        # Opciones de respuesta
        self.env['survey.question.answer'].create([
            {'question_id': question_eval.id, 'value': 'Alto'},
            {'question_id': question_eval.id, 'value': 'Medio'},
            {'question_id': question_eval.id, 'value': 'Bajo'},
        ])
        
        # Pregunta de comentarios
        self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Observaciones',
            'question_type': 'text_box',
            'page_id': section.id,
            'sequence': section_num * 10 + 2,
            'constr_mandatory': False,
        })

    def _create_satisfaction_questions(self, survey, section, section_num):
        """Crear preguntas para sección de satisfacción"""
        # Pregunta de satisfacción (simple_choice con valores 1-5)
        question_satisfaction = self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': f'¿Qué tan satisfecho está con el aspecto {section_num}?',
            'question_type': 'simple_choice',
            'page_id': section.id,
            'sequence': section_num * 10 + 1,
            'constr_mandatory': True,
        })
        
        # Opciones de respuesta (valores numéricos del 1 al 5)
        self.env['survey.question.answer'].create([
            {'question_id': question_satisfaction.id, 'value': '1', 'sequence': 1},
            {'question_id': question_satisfaction.id, 'value': '2', 'sequence': 2},
            {'question_id': question_satisfaction.id, 'value': '3', 'sequence': 3},
            {'question_id': question_satisfaction.id, 'value': '4', 'sequence': 4},
            {'question_id': question_satisfaction.id, 'value': '5', 'sequence': 5},
        ])
        
        # Pregunta de observaciones (text_box)
        self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Observaciones',
            'question_type': 'text_box',
            'page_id': section.id,
            'sequence': section_num * 10 + 2,
            'constr_mandatory': False,
        })

    def _create_participation_questions(self, survey, section, section_num):
        """Crear preguntas para sección de participación"""
        # Pregunta de participación
        question_participation = self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Nivel de Participación',
            'question_type': 'simple_choice',
            'page_id': section.id,
            'sequence': section_num * 10 + 1,
            'constr_mandatory': True,
        })
        
        # Opciones de respuesta
        self.env['survey.question.answer'].create([
            {'question_id': question_participation.id, 'value': 'Alto'},
            {'question_id': question_participation.id, 'value': 'Medio'},
            {'question_id': question_participation.id, 'value': 'Bajo'},
        ])
        
        # Pregunta de comentarios
        self.env['survey.question'].create({
            'survey_id': survey.id,
            'title': 'Comentarios',
            'question_type': 'text_box',
            'page_id': section.id,
            'sequence': section_num * 10 + 2,
            'constr_mandatory': False,
        })

    def _add_file_question_to_section(self, survey, section, sequence_offset):
        """Agregar pregunta de archivo a una sección"""
        if self.add_file_question_per_section:
            self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': 'Adjuntar archivo de respaldo',
                'question_type': 'upload_file',
                'page_id': section.id,
                'sequence': sequence_offset + 4,  # Después de las preguntas normales
                'constr_mandatory': False,
            })

    def _add_image_section_at_end(self, survey, total_sections):
        """Agregar sección final con pregunta de imagen"""
        if self.add_image_section_at_end:
            # Crear sección final
            final_section = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': 'Evidencia Fotográfica',
                'is_page': True,
                'sequence': (total_sections + 1) * 10,
            })
            
            # Crear pregunta de imagen
            self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': 'Subir imagen de evidencia',
                'question_type': 'upload_file',
                'page_id': final_section.id,
                'sequence': (total_sections + 1) * 10 + 1,
                'constr_mandatory': False,
            })

    def action_create_survey(self):
        """Crear la encuesta con la estructura predefinida según la categoría"""
        self.ensure_one()
        

        if self.section_method == 'file':
            if not self.section_file:
                raise UserError(_('Por favor, seleccione un archivo de secciones.'))
        
        # Crear la encuesta base
        survey_vals = {
            'title': self.name,
            'description': self.description,
            'category_id': self.category_id.id,
            'department_id': self.department_id.id if self.department_id else False,
            'is_anonymous': self.is_anonymous,
            'questions_layout': 'page_per_section',
        }
        
        # Si el usuario es survey manager, bloquear el departamento
        if self.env.user.has_group('survey.group_survey_manager'):
            survey_vals['is_department_locked'] = True
        
        survey = self.env['survey.survey'].create(survey_vals)
        

        if self.section_method == 'manual':

            if self.category_id.code == 'revision_items':
                self._create_revision_items_survey(survey)
            elif self.category_id.code == 'compliance':
                self._create_compliance_survey(survey)
            elif self.category_id.code == 'satisfaction':
                self._create_satisfaction_survey(survey)
            elif self.category_id.code == 'participation':
                self._create_participation_survey(survey)
        else:

            section_names = self._process_section_file()
            self._create_survey_from_sections(survey, section_names)
        
        # Retornar a la vista de la encuesta creada
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'survey.survey',
            'res_id': survey.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_revision_items_survey(self, survey):
        """Crear estructura para encuesta de items revisados"""
        for i in range(1, self.num_sections + 1):
            # Crear sección
            section = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'Sección {i}',
                'is_page': True,
                'sequence': i * 10,
            })
            
            # Crear pregunta de cumplimiento (simple_choice)
            question_compliance = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'Cumplimiento',
                'question_type': 'simple_choice',
                'page_id': section.id,
                'sequence': i * 10 + 1,
                'constr_mandatory': True,
            })
            
            # Crear opciones de respuesta para cumplimiento
            self.env['survey.question.answer'].create([
                {
                    'question_id': question_compliance.id,
                    'value': 'Cumple',
                    'sequence': 1,
                },
                {
                    'question_id': question_compliance.id,
                    'value': 'No cumple',
                    'sequence': 2,
                }
            ])
            
            # Crear pregunta de items revisados (numerical_box)
            self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'Ítems Revisados',
                'question_type': 'numerical_box',
                'page_id': section.id,
                'sequence': i * 10 + 2,
                'constr_mandatory': True,
            })
            
            # Crear pregunta de items sin novedad (numerical_box)
            self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'Ítems Revisados Sin Novedad',
                'question_type': 'numerical_box',
                'page_id': section.id,
                'sequence': i * 10 + 3,
                'constr_mandatory': True,
            })
            
            # Agregar pregunta de archivo si está habilitada
            self._add_file_question_to_section(survey, section, i * 10)
        
        # Agregar sección final con imagen si está habilitada
        self._add_image_section_at_end(survey, self.num_sections)

    def _create_compliance_survey(self, survey):
        """Crear estructura para encuesta de cumplimiento"""
        for i in range(1, self.num_sections + 1):
            # Crear sección
            section = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'Sección {i}',
                'is_page': True,
                'sequence': i * 10,
            })
            
            # Crear pregunta de cumplimiento (simple_choice)
            question_compliance = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'Cumplimiento',
                'question_type': 'simple_choice',
                'page_id': section.id,
                'sequence': i * 10 + 1,
                'constr_mandatory': True,
            })
            
            # Crear opciones de respuesta para cumplimiento
            self.env['survey.question.answer'].create([
                {
                    'question_id': question_compliance.id,
                    'value': 'Cumple',
                    'sequence': 1,
                },
                {
                    'question_id': question_compliance.id,
                    'value': 'No cumple',
                    'sequence': 2,
                }
            ])
            
            # Crear pregunta de observaciones (text_box)
            self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'Observaciones',
                'question_type': 'text_box',
                'page_id': section.id,
                'sequence': i * 10 + 2,
                'constr_mandatory': False,
            })
            
            # Agregar pregunta de archivo si está habilitada
            self._add_file_question_to_section(survey, section, i * 10)
        
        # Agregar sección final con imagen si está habilitada
        self._add_image_section_at_end(survey, self.num_sections)

    def _create_satisfaction_survey(self, survey):
        """Crear estructura para encuesta de satisfacción"""
        for i in range(1, self.num_sections + 1):
            # Crear sección
            section = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'Sección {i}',
                'is_page': True,
                'sequence': i * 10,
            })
            
            # Crear pregunta de satisfacción (simple_choice con valores 1-5)
            question_satisfaction = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'¿Qué tan satisfecho está con el aspecto {i}?',
                'question_type': 'simple_choice',
                'page_id': section.id,
                'sequence': i * 10 + 1,
                'constr_mandatory': True,
            })
            
            # Crear opciones de respuesta (valores numéricos del 1 al 5)
            self.env['survey.question.answer'].create([
                {
                    'question_id': question_satisfaction.id,
                    'value': '1',
                    'sequence': 1,
                },
                {
                    'question_id': question_satisfaction.id,
                    'value': '2',
                    'sequence': 2,
                },
                {
                    'question_id': question_satisfaction.id,
                    'value': '3',
                    'sequence': 3,
                },
                {
                    'question_id': question_satisfaction.id,
                    'value': '4',
                    'sequence': 4,
                },
                {
                    'question_id': question_satisfaction.id,
                    'value': '5',
                    'sequence': 5,
                }
            ])
            
            # Crear pregunta de observaciones (text_box)
            self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': 'Observaciones',
                'question_type': 'text_box',
                'page_id': section.id,
                'sequence': i * 10 + 2,
                'constr_mandatory': False,
            })
            
            # Agregar pregunta de archivo si está habilitada
            self._add_file_question_to_section(survey, section, i * 10)
        
        # Agregar sección final con imagen si está habilitada
        self._add_image_section_at_end(survey, self.num_sections)

    def _create_participation_survey(self, survey):
        """Crear estructura para encuesta de participación"""
        for i in range(1, self.num_sections + 1):
            # Crear sección
            section = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'Sección {i}',
                'is_page': True,
                'sequence': i * 10,
            })
            
            # Crear pregunta de participación
            question = self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': f'¿Participó activamente en la sección {i}?',
                'question_type': 'simple_choice',
                'page_id': section.id,
                'sequence': i * 10 + 1,
                'constr_mandatory': True,
            })
            
            # Crear opciones de respuesta
            self.env['survey.question.answer'].create([
                {
                    'question_id': question.id,
                    'value': 'Sí',
                    'sequence': 1,
                },
                {
                    'question_id': question.id,
                    'value': 'No',
                    'sequence': 2,
                }
            ])
            
            # Crear pregunta de observaciones (text_box)
            self.env['survey.question'].create({
                'survey_id': survey.id,
                'title': 'Observaciones',
                'question_type': 'text_box',
                'page_id': section.id,
                'sequence': i * 10 + 2,
                'constr_mandatory': False,
            })
            
            # Agregar pregunta de archivo si está habilitada
            self._add_file_question_to_section(survey, section, i * 10)
        
        # Agregar sección final con imagen si está habilitada
        self._add_image_section_at_end(survey, self.num_sections)





class SurveyCategory(models.Model):
    _name = 'survey.category'
    _description = 'Categoría de Encuesta'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código')
    description = fields.Text(string='Descripción')
    active = fields.Boolean(string='Activo', default=True)
    require_metrics = fields.Boolean(string='Requiere Métricas', default=False)

class SurveyTag(models.Model):
    _name = 'survey.tag'
    _description = 'Etiqueta de Encuesta'

    name = fields.Char(string='Nombre', required=True)
    color = fields.Integer(string='Índice de Color')
    active = fields.Boolean(string='Activo', default=True)

