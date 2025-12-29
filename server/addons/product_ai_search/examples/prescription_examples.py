# -*- coding: utf-8 -*-
"""
Exemplo de uso do sistema de análise de receitas médicas

Este arquivo demonstra como usar as funcionalidades de análise
de receitas médicas através de imagem.
"""

import base64
import logging
from odoo import api, models, _

_logger = logging.getLogger(__name__)


class PrescriptionAnalysisExample(models.TransientModel):
    """Modelo de exemplo para demonstrar uso da análise de receitas"""
    _name = 'prescription.analysis.example'
    _description = 'Exemplo de Análise de Receita Médica'

    @api.model
    def example_analyze_prescription_from_file(self, file_path):
        """
        Exemplo: Análise de receita médica a partir de arquivo
        
        Args:
            file_path (str): Caminho para o arquivo de imagem
            
        Returns:
            dict: Resultado da análise
        """
        try:
            # Lê arquivo
            with open(file_path, 'rb') as f:
                image_data = f.read()
            
            # Obtém serviço de IA
            ai_service = self.env['product.ai.search.service']
            
            # Analisa apenas a receita (sem buscar produtos)
            prescription_analysis = ai_service.analyze_prescription_image(image_data)
            
            _logger.info("Análise de receita completada:")
            _logger.info("- Medicamentos encontrados: %d", len(prescription_analysis.get('medicamentos', [])))
            _logger.info("- Confiança: %.2f", prescription_analysis.get('confianza', 0))
            
            return prescription_analysis
            
        except Exception as e:
            _logger.error("Erro no exemplo de análise: %s", str(e))
            return {'error': str(e)}

    @api.model
    def example_complete_prescription_analysis(self, file_path, top_k=10):
        """
        Exemplo: Análise completa (receita + busca de produtos)
        
        Args:
            file_path (str): Caminho para o arquivo de imagem
            top_k (int): Número máximo de produtos por medicamento
            
        Returns:
            dict: Resultado completo
        """
        try:
            # Lê arquivo
            with open(file_path, 'rb') as f:
                image_data = f.read()
            
            # Obtém serviço de IA
            ai_service = self.env['product.ai.search.service']
            
            # Análise completa
            complete_result = ai_service.process_prescription_image_complete(
                image_data, 
                top_k=top_k
            )
            
            if complete_result.get('exito'):
                _logger.info("Análise completa bem-sucedida:")
                
                # Informações da receita
                prescription = complete_result['receta_analizada']
                medicamentos = prescription.get('medicamentos', [])
                _logger.info("- Medicamentos na receita: %d", len(medicamentos))
                
                # Resultados da busca
                search_results = complete_result['busqueda_productos']
                encontrados = len(search_results.get('medicamentos_encontrados', []))
                total = search_results.get('total_medicamentos', 0)
                _logger.info("- Medicamentos encontrados no sistema: %d/%d", encontrados, total)
                
                # Detalha produtos encontrados
                for med_result in search_results.get('medicamentos_encontrados', []):
                    medicamento = med_result['medicamento_original']
                    produtos = med_result['produtos']
                    _logger.info("  * %s: %d produtos encontrados", 
                               medicamento.get('nome', 'N/A'), len(produtos))
                    
                    # Mostra top 3 produtos
                    for i, produto in enumerate(produtos[:3], 1):
                        _logger.info("    %d. %s (Score: %.2f)", 
                                   i, produto['product_name'], produto['score'])
            else:
                _logger.error("Falha na análise: %s", complete_result.get('error'))
            
            return complete_result
            
        except Exception as e:
            _logger.error("Erro no exemplo completo: %s", str(e))
            return {'error': str(e)}

    @api.model
    def example_analyze_prescription_base64(self, image_base64, image_format='jpeg'):
        """
        Exemplo: Análise de receita a partir de base64
        
        Args:
            image_base64 (str): Imagem codificada em base64
            image_format (str): Formato da imagem
            
        Returns:
            dict: Resultado da análise
        """
        try:
            # Decodifica base64
            image_data = base64.b64decode(image_base64)
            
            # Obtém serviço de IA
            ai_service = self.env['product.ai.search.service']
            
            # Analisa receita
            result = ai_service.analyze_prescription_image(image_data, image_format)
            
            return result
            
        except Exception as e:
            _logger.error("Erro no exemplo base64: %s", str(e))
            return {'error': str(e)}

    @api.model
    def example_search_by_medicine_list(self, medicine_names, top_k=5):
        """
        Exemplo: Busca produtos por lista de medicamentos
        
        Args:
            medicine_names (list): Lista de nomes de medicamentos
            top_k (int): Número máximo de produtos por medicamento
            
        Returns:
            dict: Resultados da busca
        """
        try:
            ai_service = self.env['product.ai.search.service']
            
            # Simula dados de receita
            fake_prescription_data = {
                'medicamentos': [
                    {
                        'nome': name,
                        'principio_activo': name,
                        'dosificacion': 'N/A',
                        'forma_farmaceutica': 'N/A',
                        'frecuencia': 'N/A',
                        'duracion': 'N/A'
                    }
                    for name in medicine_names
                ]
            }
            
            # Busca produtos
            search_results = ai_service.search_products_from_prescription(
                fake_prescription_data, 
                top_k=top_k
            )
            
            # Log resultados
            _logger.info("Busca por lista de medicamentos:")
            for med_result in search_results.get('medicamentos_encontrados', []):
                medicamento = med_result['medicamento_original']['nome']
                produtos = med_result['produtos']
                _logger.info("- %s: %d produtos encontrados", medicamento, len(produtos))
            
            return search_results
            
        except Exception as e:
            _logger.error("Erro na busca por lista: %s", str(e))
            return {'error': str(e)}


# Exemplos de uso em shell do Odoo:
"""
# 1. Análise simples de receita
env['prescription.analysis.example'].example_analyze_prescription_from_file('/caminho/para/receita.jpg')

# 2. Análise completa com busca de produtos  
env['prescription.analysis.example'].example_complete_prescription_analysis('/caminho/para/receita.jpg', top_k=15)

# 3. Análise de base64
with open('/caminho/para/receita.jpg', 'rb') as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')
env['prescription.analysis.example'].example_analyze_prescription_base64(image_b64)

# 4. Busca por lista de medicamentos
medicamentos = ['Paracetamol', 'Ibuprofeno', 'Amoxicilina']
env['prescription.analysis.example'].example_search_by_medicine_list(medicamentos)

# 5. Uso direto do serviço
ai_service = env['product.ai.search.service']

# Verifica status do índice
status = ai_service.check_index_status()
print("Status do índice:", status)

# Busca por texto natural
resultados = ai_service.search_products("antibiótico para infecção", top_k=10)
for r in resultados:
    print(f"- {r['product_name']} (Score: {r['score']:.2f})")
"""
