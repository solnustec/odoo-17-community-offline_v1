# -*- coding: utf-8 -*-
"""
Extensión del modelo survey.user_input.line para soportar archivos adjuntos.
"""
from odoo import api, fields, models


class SurveyUserInputLine(models.Model):
    """
    Extiende el modelo 'survey.user_input.line' para agregar campos
    y restricciones para subida de archivos.
    """
    _inherit = "survey.user_input.line"

    answer_type = fields.Selection(
        selection_add=[('upload_file', 'Subir Archivo')],
        help="El tipo de respuesta para esta pregunta (upload_file si el usuario "
             "está subiendo un archivo).")
    value_file_data_ids = fields.Many2many(
        'ir.attachment',
        help="Los archivos adjuntos correspondientes a la respuesta "
             "de subida de archivo del usuario, si los hay.")

    @api.constrains('skipped', 'answer_type')
    def _check_answer_type_skipped(self):
        """ 
        Verifica que el tipo de respuesta de una línea no esté configurado 
        como 'upload_file' si la línea está omitida.
        """
        for line in self:
            if line.answer_type != 'upload_file':
                super(SurveyUserInputLine, line)._check_answer_type_skipped() 