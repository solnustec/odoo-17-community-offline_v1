# -*- coding: utf-8 -*-
"""
Extensión del modelo survey.user_input para manejar subida de archivos.
IMPORTANTE: Este modelo NO interfiere con el cálculo de métricas existente.
"""
from odoo import models
import logging

_logger = logging.getLogger(__name__)


class SurveyUserInput(models.Model):
    """
    Extiende 'survey.user_input' para manejar preguntas de tipo 'upload_file'.
    PRESERVA la funcionalidad existente de métricas.
    """
    _inherit = "survey.user_input"

    def _save_lines(self, question, answer, comment=None, overwrite_existing=False):
        """
        Guarda la respuesta del usuario para una pregunta específica.
        PRESERVA la lógica existente de métricas.
        """
        

        if question.question_type == 'upload_file':
            old_answers = self.env['survey.user_input.line'].search([
                ('user_input_id', '=', self.id),
                ('question_id', '=', question.id),
            ])
            result = self._save_line_simple_answer(question, old_answers, answer)
        else:
            result = super(SurveyUserInput, self)._save_lines(question, answer, comment, overwrite_existing)
        
        # PRESERVAR: Verificar si la encuesta está completa y calcular métricas
        # Esta lógica NO se modifica para mantener la funcionalidad existente
        try:
            if hasattr(self, '_compute_and_save_metrics') and self.state == 'done':
                _logger.info("📊 Calculando métricas para respuesta %s", self.id)
                self._compute_and_save_metrics()
            elif self.state == 'done':
                _logger.info("📊 Encuesta completada pero método _compute_and_save_metrics no disponible")
        except Exception as e:
            _logger.error("❌ Error al calcular métricas para respuesta %s: %s", self.id, str(e))
        
        return result

    def _save_line_simple_answer(self, question, old_answers, answer):
        """
        Guarda la respuesta de archivo del usuario para la pregunta.
        PRESERVA la funcionalidad existente.
        """
        if question.question_type != 'upload_file':
            return super()._save_line_simple_answer(question, old_answers, answer)
            
        vals = self._get_line_answer_file_upload_values(
            question,
            question.question_type,
            answer
        )
        _logger.debug("📦 Valores para guardar respuesta archivo: %s", vals)

        if not vals:
            _logger.warning("⚠️ No se guardó la respuesta porque 'vals' está vacío para la pregunta %s", question.id)
            return  # No guardar nada

        if old_answers:
            old_answers.write(vals)
            return old_answers
        else:
            return self.env['survey.user_input.line'].with_context(question=question).create(vals)

    def _get_line_answer_file_upload_values(self, question, answer_type, answer, *args, **kwargs):
        """
        Prepara los valores para guardar una respuesta de archivo.
        """
        if answer_type != 'upload_file':
            _logger.warning("⚠️ _get_line_answer_file_upload_values fue llamado para un tipo distinto a 'upload_file' (tipo: %s, pregunta: %s). Esto no debería ocurrir.", answer_type, question.id)
            return None

        # Validar que la respuesta tenga el formato correcto para archivos
        if not isinstance(answer, (list, tuple)) or len(answer) != 2:
            _logger.warning("⚠️ Formato inválido para archivo en pregunta %s: %s", question.id, answer)
            return {}

        file_data_list = answer[0]
        file_name_list = answer[1]

        if not (isinstance(file_data_list, list) and isinstance(file_name_list, list)):
            _logger.error("❌ Formato inválido para archivos. Se esperaban listas.")
            return {}

        if not file_name_list:
            _logger.warning("⚠️ No hay archivos para procesar en pregunta %s", question.id)
            return {}

        attachment_ids = []
        for file_data, file_name in zip(file_data_list, file_name_list):
            try:
                attachment = self.env['ir.attachment'].create({
                    'name': file_name,
                    'type': 'binary',
                    'datas': file_data,
                })
                attachment_ids.append(attachment.id)
                _logger.debug("✅ Archivo creado: %s", file_name)
            except Exception as e:
                _logger.error("❌ Error al crear archivo %s: %s", file_name, str(e))

        return {
            'user_input_id': self.id,
            'question_id': question.id,
            'skipped': False,
            'answer_type': answer_type,
            'value_file_data_ids': attachment_ids,
        } 