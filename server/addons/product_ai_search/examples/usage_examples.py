# -*- coding: utf-8 -*-
"""
Ejemplos de cómo usar Product AI Search en otros módulos
"""

from odoo import models, fields, api


class ProductAISearchExamples(models.TransientModel):
    """
    Ejemplos prácticos de uso de Product AI Search
    """
    _name = 'product.ai.search.examples'
    _description = 'Ejemplos de Uso de Product AI Search'

    def example_basic_search(self):
        """Ejemplo 1: Búsqueda básica de productos"""
        search_service = self.env['product.ai.search.service']
        
        # Búsqueda simple de productos
        results = search_service.search_products("camiseta azul", top_k=5)
        
        print("\n=== EJEMPLO 1: Búsqueda Básica ===")
        print(f"Consulta: 'camiseta azul'")
        print(f"Resultados encontrados: {len(results)}")
        
        for result in results:
            print(f"- {result['product_name']} (Puntaje: {result['score']:.3f}) - ${result['list_price']}")
        
        return results

    def example_filtered_search(self):
        """Ejemplo 2: Búsqueda con filtros específicos"""
        search_service = self.env['product.ai.search.service']
        
        # Primero, indexa solo productos de una categoría
        domain = [
            ('active', '=', True),
            ('sale_ok', '=', True),
            ('list_price', '>', 0),
            ('categ_id.name', 'ilike', 'Electrodomésticos')
        ]
        
        # Indexa con filtro
        index_result = search_service.index_products(domain=domain, limit=50)
        
        if index_result['success']:
            # Ahora busca dentro de esa categoría
            results = search_service.search_products("refrigerador eficiente", top_k=3)
            
            print("\n=== EJEMPLO 2: Búsqueda Filtrada ===")
            print(f"Categoría: Electrodomésticos")
            print(f"Productos indexados: {index_result['indexed_products']}")
            print(f"Consulta: 'refrigerador eficiente'")
            
            for result in results:
                product = result['product']
                print(f"- {product.name}")
                print(f"  Categoría: {product.categ_id.name}")
                print(f"  Precio: ${product.list_price}")
                print(f"  Puntaje: {result['score']:.3f}")
        
        return results if index_result['success'] else []

    def example_multilingual_search(self):
        """Ejemplo 3: Búsqueda multilingüe"""
        search_service = self.env['product.ai.search.service']
        
        queries = [
            "zapatos deportivos",
            "chaussures de sport", 
            "sports shoes",
            "scarpe sportive"
        ]
        
        print("\n=== EJEMPLO 3: Búsqueda Multilingüe ===")
        
        all_results = {}
        for query in queries:
            results = search_service.search_products(query, top_k=3)
            all_results[query] = results
            
            print(f"\nConsulta: '{query}'")
            for result in results:
                print(f"- {result['product_name']} (Puntaje: {result['score']:.3f})")
        
        return all_results

    def example_pos_integration(self):
        """Ejemplo 4: Integración con POS"""
        search_service = self.env['product.ai.search.service']
        
        def search_for_pos(query, max_results=10):
            """Función que puede ser usada en el POS"""
            try:
                results = search_service.search_products(query, top_k=max_results)
                
                # Formatea para el POS
                pos_products = []
                for result in results:
                    product = result['product']
                    
                    # Verifica si tiene stock (ejemplo)
                    qty_available = sum(product.stock_quant_ids.mapped('quantity'))
                    
                    pos_products.append({
                        'id': product.id,
                        'name': product.name,
                        'display_name': f"{product.name} ({result['score']:.2f})",
                        'list_price': product.list_price,
                        'default_code': product.default_code or '',
                        'barcode': product.barcode or '',
                        'qty_available': qty_available,
                        'ai_score': result['score'],
                        'category': product.categ_id.name,
                    })
                
                return pos_products
                
            except Exception as e:
                print(f"Error en la búsqueda POS: {e}")
                return []
        
        # Prueba de la función
        test_queries = ["bebida refrescante", "snack salado", "café premium"]
        
        print("\n=== EJEMPLO 4: Integración POS ===")
        
        for query in test_queries:
            pos_results = search_for_pos(query, max_results=5)
            
            print(f"\nConsulta POS: '{query}'")
            print(f"Productos para POS: {len(pos_results)}")
            
            for product in pos_results:
                print(f"- {product['display_name']}")
                print(f"  Código: {product['default_code']}")
                print(f"  Precio: ${product['list_price']}")
                print(f"  Stock: {product['qty_available']}")
        
        return pos_results

    def example_intelligent_recommendations(self):
        """Ejemplo 5: Recomendaciones inteligentes"""
        search_service = self.env['product.ai.search.service']
        
        def get_product_recommendations(product_id, num_recommendations=5):
            """Encuentra productos similares"""
            try:
                # Busca el producto base
                base_product = self.env['product.template'].browse(product_id)
                if not base_product.exists():
                    return []
                
                # Usa características del producto para buscar similares
                search_text = f"{base_product.name} {base_product.categ_id.name}"
                if base_product.description_sale:
                    search_text += f" {base_product.description_sale[:100]}"
                
                results = search_service.search_products(search_text, top_k=num_recommendations + 1)
                
                # Elimina el producto original de los resultados
                recommendations = []
                for result in results:
                    if result['product_id'] != product_id:
                        recommendations.append(result)
                
                return recommendations[:num_recommendations]
                
            except Exception as e:
                print(f"Error en las recomendaciones: {e}")
                return []
        
        # Prueba con un producto aleatorio
        random_product = self.env['product.template'].search([
            ('active', '=', True),
            ('sale_ok', '=', True)
        ], limit=1)
        
        if random_product:
            recommendations = get_product_recommendations(random_product.id)
            
            print("\n=== EJEMPLO 5: Recomendaciones Inteligentes ===")
            print(f"Producto base: {random_product.name}")
            print(f"Recomendaciones encontradas: {len(recommendations)}")
            
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec['product_name']}")
                print(f"   Similaridad: {rec['score']:.3f}")
                print(f"   Precio: ${rec['list_price']}")
        
        return recommendations if random_product else []

    def example_smart_query_with_ai(self):
        """Ejemplo 6: Consulta con respuesta inteligente"""
        search_service = self.env['product.ai.search.service']
        
        questions = [
            "¿Qué productos azules tienes disponibles?",
            "¿Cuáles son los productos más baratos?",
            "¿Tienes productos para deportes?",
            "¿Qué opciones hay para regalar?",
        ]
        
        print("\n=== EJEMPLO 6: Consultas con IA ===")
        
        answers = {}
        for question in questions:
            try:
                answer = search_service.query_with_answer(question)
                answers[question] = answer
                
                print(f"\nPregunta: {question}")
                print(f"Respuesta IA: {answer}")
                
            except Exception as e:
                print(f"Error en la consulta '{question}': {e}")
                answers[question] = f"Error: {e}"
        
        return answers

    def example_batch_operations(self):
        """Ejemplo 7: Operaciones en lote"""
        search_service = self.env['product.ai.search.service']
        
        print("\n=== EJEMPLO 7: Operaciones en Lote ===")
        
        # 1. Indexación en lote
        print("1. Indexando productos en lotes...")
        index_result = search_service.index_products(
            limit=100,  # Límite para prueba
            batch_size=20  # Lotes más pequeños para demo
        )
        
        print(f"Resultado de la indexación:")
        print(f"- Éxito: {index_result['success']}")
        print(f"- Productos indexados: {index_result.get('indexed_products', 0)}")
        print(f"- Tiempo transcurrido: {index_result.get('elapsed_time', 0):.2f}s")
        
        # 2. Múltiples búsquedas
        if index_result['success']:
            print("\n2. Realizando múltiples búsquedas...")
            search_queries = [
                "producto económico",
                "artículo premium",
                "herramienta útil",
                "accesorio moderno"
            ]
            
            batch_results = {}
            for query in search_queries:
                results = search_service.search_products(query, top_k=3)
                batch_results[query] = len(results)
                print(f"- '{query}': {len(results)} resultados")
        
        return index_result

    def run_all_examples(self):
        """Ejecuta todos los ejemplos"""
        print("🚀 EJECUTANDO TODOS LOS EJEMPLOS DE PRODUCT AI SEARCH\n")
        
        examples = [
            self.example_basic_search,
            self.example_filtered_search,
            self.example_multilingual_search,
            self.example_pos_integration,
            self.example_intelligent_recommendations,
            self.example_smart_query_with_ai,
            self.example_batch_operations,
        ]
        
        results = {}
        for example in examples:
            try:
                result = example()
                results[example.__name__] = {
                    'success': True,
                    'data': result
                }
            except Exception as e:
                print(f"❌ Error en el ejemplo {example.__name__}: {e}")
                results[example.__name__] = {
                    'success': False,
                    'error': str(e)
                }
        
        print("\n🎉 EJEMPLOS CONCLUIDOS!")
        print("="*50)
        
        success_count = sum(1 for r in results.values() if r['success'])
        total_count = len(results)
        
        print(f"Éxitos: {success_count}/{total_count}")
        
        for name, result in results.items():
            status = "✅" if result['success'] else "❌"
            print(f"{status} {name}")
        
        return results


# ============================================================================
# EJEMPLO DE HERENCIA EN MODELOS EXISTENTES
# ============================================================================

class ProductTemplate(models.Model):
    """Ejemplo de cómo extender product.template con búsqueda IA"""
    _inherit = 'product.template'

    def action_find_similar_products(self):
        """Acción para encontrar productos similares"""
        search_service = self.env['product.ai.search.service']
        
        # Usa nombre y categoría para buscar similares
        search_text = f"{self.name} {self.categ_id.name if self.categ_id else ''}"
        
        similar_products = search_service.search_products(search_text, top_k=10)
        
        # Elimina el producto actual de los resultados
        similar_products = [p for p in similar_products if p['product_id'] != self.id]
        
        # Retorna acción para mostrar productos similares
        if similar_products:
            product_ids = [p['product_id'] for p in similar_products]
            
            return {
                'name': f'Productos Similares a {self.name}',
                'type': 'ir.actions.act_window',
                'res_model': 'product.template',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', product_ids)],
                'context': {'search_default_filter_to_sell': 1}
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'No se encontraron productos similares.',
                    'type': 'info',
                }
            }


class SaleOrder(models.Model):
    """Ejemplo de integración con pedidos de venta"""
    _inherit = 'sale.order'

    def suggest_products_by_description(self, description):
        """Sugiere productos basado en descripción del cliente"""
        if not description:
            return []
        
        search_service = self.env['product.ai.search.service']
        
        try:
            results = search_service.search_products(description, top_k=10)
            
            suggestions = []
            for result in results:
                product = result['product']
                
                suggestions.append({
                    'product_id': product.id,
                    'name': product.name,
                    'default_code': product.default_code,
                    'list_price': product.list_price,
                    'uom_id': product.uom_id.id,
                    'ai_confidence': result['score'],
                    'suggested_qty': 1,
                })
            
            return suggestions
            
        except Exception as e:
            return []

    def auto_add_suggested_products(self, customer_description):
        """Agrega automáticamente productos sugeridos al pedido"""
        suggestions = self.suggest_products_by_description(customer_description)
        
        added_products = []
        for suggestion in suggestions[:3]:  # Agrega solo los 3 mejores
            if suggestion['ai_confidence'] > 0.7:  # Solo sugerencias con alta confianza
                
                # Crea línea del pedido
                order_line = self.env['sale.order.line'].create({
                    'order_id': self.id,
                    'product_id': suggestion['product_id'],
                    'product_uom_qty': suggestion['suggested_qty'],
                    'price_unit': suggestion['list_price'],
                })
                
                added_products.append(order_line)
        
        return added_products
