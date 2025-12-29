# -*- coding: utf-8 -*-

import json
import base64
import logging
from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PrescriptionController(http.Controller):
    """Controlador para análisis de receitas médicas"""

    @http.route('/product_ai_search/upload_prescription', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_prescription(self, **kwargs):
        """
        Endpoint para subir y analizar imagen de receta médica
        """
        try:
            # Verifica si se subió archivo
            if 'prescription_image' not in request.httprequest.files:
                return request.make_response(
                    json.dumps({
                        'success': False,
                        'error': _('No se encontró archivo de imagen')
                    }),
                    headers={'Content-Type': 'application/json'}
                )
            
            uploaded_file = request.httprequest.files['prescription_image']
            
            if uploaded_file.filename == '':
                return request.make_response(
                    json.dumps({
                        'success': False,
                        'error': _('No se seleccionó archivo')
                    }),
                    headers={'Content-Type': 'application/json'}
                )
            
            # Lee contenido del archivo
            file_content = uploaded_file.read()
            file_name = uploaded_file.filename
            content_type = uploaded_file.content_type
            
            # Valida tipo de archivo
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
            if content_type not in allowed_types:
                return request.make_response(
                    json.dumps({
                        'success': False,
                        'error': _('Tipo de archivo no permitido. Use JPEG, PNG o WEBP')
                    }),
                    headers={'Content-Type': 'application/json'}
                )
            
            # Valida tamaño (max 20MB)
            if len(file_content) > 20 * 1024 * 1024:
                return request.make_response(
                    json.dumps({
                        'success': False,
                        'error': _('Archivo muy grande. Máximo 20MB')
                    }),
                    headers={'Content-Type': 'application/json'}
                )
            
            # Obtiene parámetros adicionales
            top_k = int(kwargs.get('top_k', 10))
            analysis_only = kwargs.get('analysis_only', 'false').lower() == 'true'
            
            # Procesa la imagen
            ai_service = request.env['product.ai.search.service']
            
            if analysis_only:
                # Solo análisis de receta
                result = ai_service.analyze_prescription_image(file_content)
                response_data = {
                    'success': True,
                    'prescription_analysis': result,
                    'message': _('Receta analizada exitosamente')
                }
            else:
                # Análisis completo + búsqueda de productos
                result = ai_service.process_prescription_image_complete(
                    file_content, 
                    top_k=top_k
                )
                
                if result.get('exito'):
                    response_data = {
                        'success': True,
                        'complete_analysis': result,
                        'message': _('Receta procesada y productos encontrados')
                    }
                else:
                    response_data = {
                        'success': False,
                        'error': result.get('error', _('Error desconocido'))
                    }
            
            return request.make_response(
                json.dumps(response_data, ensure_ascii=False, indent=2),
                headers={'Content-Type': 'application/json; charset=utf-8'}
            )
            
        except Exception as e:
            _logger.error("Error en upload_prescription: %s", str(e))
            return request.make_response(
                json.dumps({
                    'success': False,
                    'error': str(e)
                }),
                headers={'Content-Type': 'application/json'}
            )

    @http.route('/product_ai_search/prescription_form', type='http', auth='user')
    def prescription_form(self, **kwargs):
        """
        Página web para subir receitas médicas
        """
        return request.render('product_ai_search.prescription_upload_form')

    @http.route('/product_ai_search/analyze_prescription_base64', type='json', auth='user', methods=['POST'])
    def analyze_prescription_base64(self, image_base64, image_format='jpeg', top_k=10, analysis_only=False):
        """
        Analiza receta médica desde imagen en base64
        
        Args:
            image_base64 (str): Imagen codificada en base64
            image_format (str): Formato de la imagen
            top_k (int): Número máximo de productos
            analysis_only (bool): Solo análisis, sin búsqueda
        """
        try:
            # Decodifica imagen
            image_data = base64.b64decode(image_base64)
            
            # Procesa la imagen
            ai_service = request.env['product.ai.search.service']
            
            if analysis_only:
                result = ai_service.analyze_prescription_image(image_data, image_format)
                return {
                    'success': True,
                    'prescription_analysis': result
                }
            else:
                result = ai_service.process_prescription_image_complete(
                    image_data, 
                    image_format=image_format,
                    top_k=top_k
                )
                return {
                    'success': result.get('exito', False),
                    'data': result
                }
                
        except Exception as e:
            _logger.error("Error en analyze_prescription_base64: %s", str(e))
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/product_ai_search/prescription_search_json', type='json', auth='user', methods=['POST'])
    def prescription_search_json(self, prescription_data, top_k=10):
        """
        Busca productos basándose en datos de receta ya procesados
        
        Args:
            prescription_data (dict): Datos de receta procesados
            top_k (int): Número máximo de productos
        """
        try:
            ai_service = request.env['product.ai.search.service']
            result = ai_service.search_products_from_prescription(prescription_data, top_k)
            
            return {
                'success': True,
                'search_results': result
            }
            
        except Exception as e:
            _logger.error("Error en prescription_search_json: %s", str(e))
            return {
                'success': False,
                'error': str(e)
            }
