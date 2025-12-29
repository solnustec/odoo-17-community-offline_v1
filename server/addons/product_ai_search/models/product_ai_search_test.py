# -*- coding: utf-8 -*-

import time
import base64

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ProductAISearchTest(models.TransientModel):
    """
    Wizard para probar la búsqueda IA de productos
    """
    _name = 'product.ai.search.test'
    _description = 'Prueba de Búsqueda IA para Productos'

    search_query = fields.Char(
        string='Consulta de Búsqueda',
        required=False,
        placeholder='Ej: camiseta azul, zapatos deportivos, producto económico...'
    )
    
    max_results = fields.Integer(
        string='Máximo de Resultados',
        default=10,
        help='Número máximo de productos a retornar'
    )
    
    search_type = fields.Selection([
        ('search', 'Búsqueda por Similitud'),
        ('answer', 'Pregunta y Respuesta'),
        ('prescription', 'Análise de Receita Médica'),
    ], string='Tipo de Búsqueda', default='search', required=True)
    
    # Campos para análise de receita médica
    prescription_image = fields.Binary(string='Imagem da Receita')
    prescription_filename = fields.Char(string='Nome do Arquivo')
    prescription_top_k = fields.Integer(string='Máximo de produtos por medicamento', default=3)
    prescription_analysis_only = fields.Boolean(string='Apenas analisar receita', default=False)
    
    # Resultados
    result_ids = fields.One2many(
        'product.ai.search.test.result',
        'test_id',
        string='Resultados'
    )
    
    ai_answer = fields.Text(
        string='Respuesta IA',
        readonly=True
    )
    
    search_executed = fields.Boolean(
        string='Búsqueda Ejecutada',
        default=False
    )
    
    total_results = fields.Integer(
        string='Total de Resultados',
        readonly=True
    )
    
    search_time = fields.Float(
        string='Tiempo de Búsqueda (segundos)',
        readonly=True
    )

    def action_search(self):
        """Executar búsqueda AI"""
        if not self.search_query and self.search_type != 'prescription':
            raise ValidationError("Por favor ingrese un término de búsqueda")
        
        if self.search_type == 'prescription':
            return self.action_prescription_analysis()
            
        start_time = time.time()
        
        try:
            service = self.env['product.ai.search.service']
            
            if self.search_type == 'search':
                # Búsqueda por similitud
                results = service.search_products(
                    query=self.search_query,
                    top_k=self.max_results
                )
                
                # Limpiar resultados anteriores
                self.result_ids.unlink()
                
                # Crear nuevos resultados
                for i, result in enumerate(results):
                    product = self.env['product.template'].browse(result['product_id'])
                    self.env['product.ai.search.test.result'].create({
                        'test_id': self.id,
                        'product_id': product.id,
                        'product_name': product.name,
                        'default_code': product.default_code or '',
                        'list_price': product.list_price,
                        'category_name': product.categ_id.complete_name if product.categ_id else '',
                        'ai_score': result['score'],
                        'rank': i + 1,
                        'matched_text': result.get('matched_text', ''),
                    })
                
                self.total_results = len(results)
                
            elif self.search_type == 'answer':
                # Pregunta y respuesta
                answer = service.query_with_answer(self.search_query)
                self.ai_answer = answer
                self.total_results = 1
            
            end_time = time.time()
            self.search_time = round(end_time - start_time, 2)
            self.search_executed = True
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'product.ai.search.test',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': self.env.context,
            }
            
        except Exception as e:
            raise ValidationError(f"Error en la búsqueda: {str(e)}")

    def action_clear_results(self):
        """Limpia todos los resultados y resetea el formulario"""
        self.ensure_one()
        
        # Invalida cache
        self.env.invalidate_all()
        
        # Limpia resultados
        old_results = self.env['product.ai.search.test.result'].search([('test_id', '=', self.id)])
        if old_results:
            old_results.unlink()
        
        # Reset campos
        self.write({
            'search_executed': False,
            'ai_answer': False,
            'total_results': 0,
            'search_time': 0.0,
            'search_query': '',
        })
        
        # Força commit e invalida cache
        self.env.cr.commit()
        self.env.invalidate_all()
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.ai.search.test',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'notification': {
                    'title': _("Resultados Limpiados"),
                    'message': _("Formulario reseteado con éxito"),
                    'type': 'info',
                }
            }
        }

    def action_index_products(self):
        """Indexa productos para prueba"""
        search_service = self.env['product.ai.search.service']
        
        try:
            result = search_service.index_products(limit=100, batch_size=20)
            
            if result['success']:
                message = _("¡Indexación completada! %d productos indexados.") % result['indexed_products']
                notification_type = 'success'
            else:
                message = _("Error en la indexación: %s") % result['message']
                notification_type = 'danger'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Indexación de Productos"),
                    'message': message,
                    'type': notification_type,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Error en la Indexación"),
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def action_check_status(self):
        """Verifica status del índice"""
        search_service = self.env['product.ai.search.service']
        
        try:
            status = search_service.check_index_status()
            
            if status.get('exists'):
                if status.get('has_data'):
                    message = _("El índice existe y contiene datos. ¡Listo para búsqueda!")
                else:
                    message = _("El índice existe pero está vacío. Ejecute la indexación primero.")
                notification_type = 'info'
            else:
                message = _("El índice no existe o error: %s") % status.get('error', 'Error desconocido')
                notification_type = 'warning'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Estado del Índice"),
                    'message': message,
                    'type': notification_type,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Error en la Verificación"),
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def action_prescription_analysis(self):
        """Analisar receita médica e buscar produtos correspondentes"""
        if not self.prescription_image:
            raise ValidationError("Por favor, suba uma imagem da receita médica")
        
        start_time = time.time()
        
        try:
            service = self.env['product.ai.search.service']
            
            # Decodificar a imagem
            image_data = base64.b64decode(self.prescription_image)
            
            if self.prescription_analysis_only:
                # Apenas analisar a receita sem buscar produtos
                analysis = service.analyze_prescription_image(image_data)
                self.ai_answer = "Análise da Receita:\n\n" + analysis
                self.total_results = 1
            else:
                # Analisar e buscar produtos correspondentes
                results = service.process_prescription_image_complete(
                    image_data=image_data,
                    top_k=self.prescription_top_k
                )
                
                # Limpiar resultados anteriores
                self.result_ids.unlink()
                
                # Criar resultados para cada medicamento encontrado
                position = 1
                total_products = 0
                
                analysis_text = "📋 Análise da Receita Médica:\n\n"
                
                if results.get('receta_analizada'):
                    analysis_text += f"Paciente: {results['receta_analizada'].get('paciente', 'N/A')}\n"
                    analysis_text += f"Médico: {results['receta_analizada'].get('medico', 'N/A')}\n"
                    analysis_text += f"Data: {results['receta_analizada'].get('fecha', 'N/A')}\n\n"
                
                analysis_text += "🔍 Produtos Encontrados:\n\n"
                
                search_data = results.get('busqueda_productos', {})
                medicamentos_encontrados = search_data.get('medicamentos_encontrados', [])
                
                for med_result in medicamentos_encontrados:
                    medicamento = med_result['medicamento_original']
                    productos = med_result.get('productos', [])
                    
                    med_name = medicamento.get('nombre', 'Medicamento desconhecido')
                    analysis_text += f"💊 {med_name}:\n"
                    
                    if productos:
                        for product_data in productos:
                            product = self.env['product.template'].browse(product_data['product_id'])
                            self.env['product.ai.search.test.result'].create({
                                'test_id': self.id,
                                'product_id': product.id,
                                'product_name': product.name,
                                'default_code': product.default_code or '',
                                'list_price': product.list_price,
                                'category_name': product.categ_id.complete_name if product.categ_id else '',
                                'ai_score': product_data['score'],
                                'rank': position,
                                'matched_text': f"Medicamento: {med_name}",
                            })
                            position += 1
                            total_products += 1
                            analysis_text += f"  • {product.name} (Score: {product_data['score']:.3f})\n"
                    else:
                        analysis_text += "  • Nenhum produto encontrado\n"
                    
                    analysis_text += "\n"
                
                self.ai_answer = analysis_text
                self.total_results = total_products
            
            end_time = time.time()
            self.search_time = round(end_time - start_time, 2)
            self.search_executed = True
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'product.ai.search.test',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': self.env.context,
            }
            
        except Exception as e:
            raise ValidationError(f"Erro na análise da receita: {str(e)}")


class ProductAISearchTestResult(models.TransientModel):
    """
    Resultado individual de búsqueda
    """
    _name = 'product.ai.search.test.result'
    _description = 'Resultado de Prueba de Búsqueda IA'
    _order = 'rank'

    test_id = fields.Many2one(
        'product.ai.search.test',
        string='Prueba',
        ondelete='cascade'
    )
    
    rank = fields.Integer(
        string='Posición',
        help='Posición en el ranking de búsqueda'
    )
    
    product_id = fields.Many2one(
        'product.template',
        string='Produto',
        readonly=True
    )
    
    product_name = fields.Char(
        string='Nombre del Producto',
        readonly=True
    )
    
    default_code = fields.Char(
        string='Código',
        readonly=True
    )
    
    list_price = fields.Float(
        string='Precio',
        readonly=True
    )
    
    category_name = fields.Char(
        string='Categoría',
        readonly=True
    )
    
    ai_score = fields.Float(
        string='Score IA',
        readonly=True,
        help='Score de similitud (0-1)'
    )
    
    matched_text = fields.Text(
        string='Texto Coincidente',
        readonly=True
    )

    def action_open_product(self):
        """Abre el producto"""
        self.ensure_one()
        
        if not self.product_id:
            return
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Producto: %s') % self.product_name,
            'res_model': 'product.template',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
