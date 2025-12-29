# -*- coding: utf-8 -*-
"""
Extensión del modelo survey.question para soportar subida de archivos.
"""
from odoo import fields, models


class SurveyQuestion(models.Model):
    """
    Extiende el modelo 'survey.question' para agregar funcionalidad
    de subida de archivos.
    """
    _inherit = 'survey.question'

    question_type = fields.Selection(
        selection_add=[('upload_file', 'Subir Archivo')],
        help='Selecciona el tipo de pregunta a crear.')
    upload_multiple_file = fields.Boolean(
        string='Subir Múltiples Archivos',
        help='Marca esta casilla si quieres permitir a los usuarios '
             'subir múltiples archivos') 