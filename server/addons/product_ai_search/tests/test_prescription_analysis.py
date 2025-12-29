#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de teste para funcionalidades de análise de receitas médicas

Execute este script no shell do Odoo para testar as funcionalidades:
python test_prescription_analysis.py
"""

import base64
import logging
import sys
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_dependencies():
    """Testa se todas as dependências estão instaladas"""
    logger.info("🔍 Testando dependências...")
    
    missing_deps = []
    
    try:
        import llama_index
        logger.info("✅ LlamaIndex: OK")
    except ImportError:
        missing_deps.append("llama-index")
        logger.error("❌ LlamaIndex: FALTANDO")
    
    try:
        import elasticsearch
        logger.info("✅ Elasticsearch: OK") 
    except ImportError:
        missing_deps.append("elasticsearch")
        logger.error("❌ Elasticsearch: FALTANDO")
    
    try:
        import openai
        logger.info("✅ OpenAI: OK")
    except ImportError:
        missing_deps.append("openai")
        logger.error("❌ OpenAI: FALTANDO")
    
    try:
        from PIL import Image
        logger.info("✅ Pillow (PIL): OK")
    except ImportError:
        missing_deps.append("Pillow")
        logger.error("❌ Pillow (PIL): FALTANDO")
    
    try:
        import requests
        logger.info("✅ Requests: OK")
    except ImportError:
        missing_deps.append("requests")
        logger.error("❌ Requests: FALTANDO")
    
    if missing_deps:
        logger.error("🚨 Dependências faltando: %s", ", ".join(missing_deps))
        logger.info("💡 Para instalar: pip install %s", " ".join(missing_deps))
        return False
    else:
        logger.info("🎉 Todas as dependências estão instaladas!")
        return True

def test_service_availability(env):
    """Testa se o serviço está disponível no Odoo"""
    logger.info("🔍 Testando disponibilidade do serviço...")
    
    try:
        ai_service = env['product.ai.search.service']
        logger.info("✅ Serviço product.ai.search.service: DISPONÍVEL")
        return ai_service
    except Exception as e:
        logger.error("❌ Serviço product.ai.search.service: INDISPONÍVEL - %s", str(e))
        return None

def test_configuration(ai_service):
    """Testa configurações do sistema"""
    logger.info("🔍 Testando configurações...")
    
    try:
        # Testa configuração OpenAI
        openai_config = ai_service._get_openai_config()
        if openai_config.get('api_key') and openai_config['api_key'] != 'sua_chave_openai_aqui':
            logger.info("✅ Configuração OpenAI: OK")
        else:
            logger.error("❌ Configuração OpenAI: Chave não configurada")
            return False
    except Exception as e:
        logger.error("❌ Configuração OpenAI: ERRO - %s", str(e))
        return False
    
    try:
        # Testa configuração Elasticsearch
        es_config = ai_service._get_elasticsearch_config()
        logger.info("✅ Configuração Elasticsearch: %s", es_config['url'])
    except Exception as e:
        logger.error("❌ Configuração Elasticsearch: ERRO - %s", str(e))
        return False
    
    return True

def test_index_status(ai_service):
    """Testa status do índice Elasticsearch"""
    logger.info("🔍 Testando status do índice...")
    
    try:
        status = ai_service.check_index_status()
        if status.get('exists'):
            logger.info("✅ Índice Elasticsearch: EXISTE")
            if status.get('has_data'):
                logger.info("✅ Dados no índice: DISPONÍVEIS")
            else:
                logger.warning("⚠️ Dados no índice: VAZIOS")
        else:
            logger.error("❌ Índice Elasticsearch: NÃO EXISTE - %s", status.get('error', 'Erro desconhecido'))
            return False
    except Exception as e:
        logger.error("❌ Status do índice: ERRO - %s", str(e))
        return False
    
    return True

def create_test_image():
    """Cria uma imagem de teste simples"""
    logger.info("🔍 Criando imagem de teste...")
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        
        # Cria imagem básica simulando receita
        img = Image.new('RGB', (800, 600), color='white')
        draw = ImageDraw.Draw(img)
        
        # Texto simulando receita médica
        test_text = [
            "Dr. João Silva - CRM 12345",
            "Clinica Médica",
            "",
            "Paciente: Maria Santos",
            "Data: 08/09/2025",
            "",
            "Prescrição:",
            "1. Paracetamol 500mg - 1 comp cada 8h por 7 dias",
            "2. Ibuprofeno 400mg - 1 comp cada 12h por 5 dias", 
            "3. Amoxicilina 500mg - 1 caps cada 8h por 10 dias",
            "",
            "Diagnóstico: Infecção respiratória",
            "",
            "________________________",
            "Dr. João Silva"
        ]
        
        y_offset = 50
        for line in test_text:
            draw.text((50, y_offset), line, fill='black')
            y_offset += 30
        
        # Converte para bytes
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        image_data = buffer.getvalue()
        
        logger.info("✅ Imagem de teste criada (Tamanho: %d bytes)", len(image_data))
        return image_data
        
    except Exception as e:
        logger.error("❌ Erro ao criar imagem de teste: %s", str(e))
        return None

def test_prescription_analysis(ai_service, image_data):
    """Testa análise de receita médica"""
    logger.info("🔍 Testando análise de receita médica...")
    
    try:
        result = ai_service.analyze_prescription_image(image_data)
        
        if result:
            logger.info("✅ Análise de receita: SUCESSO")
            
            medicamentos = result.get('medicamentos', [])
            logger.info("📋 Medicamentos encontrados: %d", len(medicamentos))
            
            for i, med in enumerate(medicamentos, 1):
                nome = med.get('nome', 'N/A')
                principio = med.get('principio_activo', 'N/A')
                logger.info("   %d. %s (%s)", i, nome, principio)
            
            confianca = result.get('confianza', 0)
            logger.info("🎯 Confiança: %.2f", confianca)
            
            return True
        else:
            logger.error("❌ Análise de receita: FALHOU - Resultado vazio")
            return False
            
    except Exception as e:
        logger.error("❌ Análise de receita: ERRO - %s", str(e))
        return False

def test_product_search(ai_service):
    """Testa busca de produtos"""
    logger.info("🔍 Testando busca de produtos...")
    
    try:
        # Busca simples
        query = "paracetamol"
        results = ai_service.search_products(query, top_k=5)
        
        if results:
            logger.info("✅ Busca de produtos: SUCESSO")
            logger.info("🔍 Produtos encontrados para '%s': %d", query, len(results))
            
            for i, produto in enumerate(results, 1):
                nome = produto.get('product_name', 'N/A')
                score = produto.get('score', 0)
                logger.info("   %d. %s (Score: %.2f)", i, nome, score)
            
            return True
        else:
            logger.warning("⚠️ Busca de produtos: Nenhum resultado para '%s'", query)
            return False
            
    except Exception as e:
        logger.error("❌ Busca de produtos: ERRO - %s", str(e))
        return False

def test_complete_analysis(ai_service, image_data):
    """Testa análise completa (receita + busca)"""
    logger.info("🔍 Testando análise completa...")
    
    try:
        result = ai_service.process_prescription_image_complete(image_data, top_k=5)
        
        if result.get('exito'):
            logger.info("✅ Análise completa: SUCESSO")
            
            # Dados da receita
            prescription = result.get('receta_analizada', {})
            medicamentos = prescription.get('medicamentos', [])
            logger.info("📋 Medicamentos na receita: %d", len(medicamentos))
            
            # Resultados da busca
            search_results = result.get('busqueda_productos', {})
            encontrados = len(search_results.get('medicamentos_encontrados', []))
            total = search_results.get('total_medicamentos', 0)
            taxa_sucesso = search_results.get('resumen', {}).get('tasa_exito', 0)
            
            logger.info("🎯 Produtos encontrados: %d/%d (%.1f%%)", encontrados, total, taxa_sucesso * 100)
            
            return True
        else:
            error = result.get('error', 'Erro desconhecido')
            logger.error("❌ Análise completa: FALHOU - %s", error)
            return False
            
    except Exception as e:
        logger.error("❌ Análise completa: ERRO - %s", str(e))
        return False

def run_all_tests(env):
    """Executa todos os testes"""
    logger.info("🚀 Iniciando testes do sistema de análise de receitas médicas...")
    
    tests_passed = 0
    total_tests = 6
    
    # 1. Teste de dependências
    if test_dependencies():
        tests_passed += 1
    
    # 2. Teste de disponibilidade do serviço
    ai_service = test_service_availability(env)
    if ai_service:
        tests_passed += 1
    else:
        logger.error("🚨 Não é possível continuar sem o serviço. Interrompendo testes.")
        return False
    
    # 3. Teste de configuração
    if test_configuration(ai_service):
        tests_passed += 1
    
    # 4. Teste de status do índice
    if test_index_status(ai_service):
        tests_passed += 1
    
    # 5. Criar imagem de teste e testar análise
    image_data = create_test_image()
    if image_data:
        if test_prescription_analysis(ai_service, image_data):
            tests_passed += 1
    
    # 6. Teste de busca de produtos
    if test_product_search(ai_service):
        tests_passed += 1
    
    # Teste adicional completo
    if image_data:
        logger.info("🔍 Executando teste completo adicional...")
        test_complete_analysis(ai_service, image_data)
    
    # Resultados finais
    logger.info("=" * 50)
    logger.info("📊 RESULTADOS DOS TESTES")
    logger.info("=" * 50)
    logger.info("✅ Testes aprovados: %d/%d", tests_passed, total_tests)
    logger.info("📈 Taxa de sucesso: %.1f%%", (tests_passed / total_tests) * 100)
    
    if tests_passed == total_tests:
        logger.info("🎉 TODOS OS TESTES PASSARAM! O sistema está funcionando corretamente.")
        return True
    else:
        logger.warning("⚠️ Alguns testes falharam. Verifique as configurações e dependências.")
        return False

# Exemplo de uso no shell do Odoo:
"""
# 1. No shell do Odoo, execute:
exec(open('test_prescription_analysis.py').read())
run_all_tests(env)

# 2. Ou importe e use funções específicas:
exec(open('test_prescription_analysis.py').read())
ai_service = env['product.ai.search.service']
test_dependencies()
test_configuration(ai_service)
"""

if __name__ == "__main__":
    print("Este script deve ser executado no shell do Odoo.")
    print("Exemplo:")
    print("1. Inicie o shell: sudo docker exec -it odoo-erp odoo shell -d sua_database")
    print("2. Execute: exec(open('test_prescription_analysis.py').read())")
    print("3. Execute: run_all_tests(env)")
