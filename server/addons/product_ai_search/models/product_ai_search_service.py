# -*- coding: utf-8 -*-

import os
import logging
import time
from typing import List, Dict, Any
from odoo import models, api, _
from odoo.exceptions import UserError, ValidationError

try:
    from llama_index.core.schema import TextNode
    from llama_index.core import StorageContext, VectorStoreIndex
    from llama_index.vector_stores.elasticsearch import ElasticsearchStore
    from llama_index.vector_stores.elasticsearch import AsyncDenseVectorStrategy
    import pandas as pd
    from tqdm import tqdm
    import base64
    import io
    from PIL import Image
    import openai
    import requests
except ImportError as e:
    logging.getLogger(__name__).warning(
        "No fue posible importar las dependencias de LlamaIndex/Elasticsearch: %s", str(e)
    )

_logger = logging.getLogger(__name__)


class ProductAISearchService(models.AbstractModel):
    """
    Servicio de búsqueda inteligente de productos usando LlamaIndex + Elasticsearch
    """
    _name = 'product.ai.search.service'
    _description = 'Servicio de Búsqueda IA para Productos'

    @api.model
    def _get_config_param(self, key, default=None):
        """Obtiene parámetro de configuración"""
        return self.env['ir.config_parameter'].sudo().get_param(
            f'product_ai_search.{key}', default
        )

    @api.model
    def _validate_dependencies(self):
        """Valida si las dependencias están instaladas"""
        try:
            import llama_index
            import openai
            from PIL import Image
            import requests
            import elasticsearch
            
            return True
        except ImportError as e:
            _logger.error("Dependencias no instaladas: %s", str(e))
            return False

    @api.model
    def _get_elasticsearch_config(self):
        """Obtiene configuración de Elasticsearch"""
        return {
            'url': self._get_config_param('elasticsearch_url', 'http://elasticsearch:9200'),
            'index_name': self._get_config_param('elasticsearch_index', 'products_llamaindex_es'),
            'strategy': self._get_config_param('elasticsearch_strategy', 'dense'),
            'auth_type': self._get_config_param('elasticsearch_auth_type', 'none'),
            'username': self._get_config_param('elasticsearch_username', ''),
            'password': self._get_config_param('elasticsearch_password', ''),
            'api_key': self._get_config_param('elasticsearch_api_key', ''),
            'verify_certs': self._get_config_param('elasticsearch_verify_certs', 'True') == 'True',
        }

    @api.model
    def _get_openai_config(self):
        """Obtiene configuración de OpenAI"""
        api_key = self._get_config_param('openai_api_key')
        if not api_key or api_key == 'sua_chave_openai_aqui':
            raise ValidationError(_("Configure la clave de OpenAI en los parámetros del sistema"))
        
        os.environ["OPENAI_API_KEY"] = api_key
        return {'api_key': api_key}

    @api.model
    def _create_vector_store(self):
        """Crea el vector store de Elasticsearch"""
        if not self._validate_dependencies():
            raise UserError(_("Dependencias de LlamaIndex no están instaladas"))
        
        return self._create_elasticsearch_store()

    @api.model
    def _create_elasticsearch_store(self):
        """Crea el vector store de Elasticsearch"""
        es_config = self._get_elasticsearch_config()
        
        # Define estrategia de recuperación
        if es_config['strategy'] == 'hybrid':
            retrieval_strategy = AsyncDenseVectorStrategy(hybrid=True)
        else:
            retrieval_strategy = AsyncDenseVectorStrategy()
        
        try:
            # Configuración básica
            es_kwargs = {
                'es_url': es_config['url'],
                'index_name': es_config['index_name'],
                'retrieval_strategy': retrieval_strategy,
            }
            
            # Configuración de autenticación
            if es_config['auth_type'] == 'basic' and es_config['username'] and es_config['password']:
                es_kwargs['es_user'] = es_config['username']
                es_kwargs['es_password'] = es_config['password']
            elif es_config['auth_type'] == 'api_key' and es_config['api_key']:
                es_kwargs['es_api_key'] = es_config['api_key']
            
            # Configuración de SSL
            if not es_config['verify_certs']:
                es_kwargs['es_ssl_verify'] = False
            
            vector_store = ElasticsearchStore(**es_kwargs)
            return vector_store
        except Exception as e:
            _logger.error("Error al crear vector store de Elasticsearch: %s", str(e))
            raise UserError(_("Error al conectar con Elasticsearch: %s") % str(e))

    @api.model
    def _get_products_data(self, domain=None, limit=None):
        """Busca productos para indexación"""
        if domain is None:
            domain = [
                ('sale_ok', '=', True),
                ('name', '!=', False),
            ]
        
        products = self.env['product.template'].search(domain, limit=limit)
        
        products_data = []
        for product in products:
            # Obtiene nombre en español si está disponible
            product_name = product.name
            if hasattr(product, 'name') and isinstance(product.name, dict):
                product_name = product.name.get('es_EC', product.name)
            
            product_data = {
                'id': product.id,
                'name': product_name,
                'default_code': product.default_code or '',
                'category_name': product.categ_id.complete_name if product.categ_id else '',
                'list_price': product.list_price,
                'type': product.type,
                'description_sale': product.description_sale or '',
                'active': product.active,
                'sale_ok': product.sale_ok,
            }
            products_data.append(product_data)
        
        return products_data

    @api.model
    def _create_text_nodes(self, products_data):
        """
        Convierte datos de productos en TextNodes de LlamaIndex
        
        EMBEDDING SIMPLIFICADO: Solo usa NOMBRE + CATEGORÍA
        - Nombre del producto (campo principal)
        - Categoría completa (contexto/clasificación)
        - Excluye: código, descripción, precios
        """
        text_nodes = []
        
        for product_data in products_data:
            try:
                # Arma texto para embedding - SOLO NOMBRE Y CATEGORÍA
                text_parts = [product_data['name']]
                
                #if product_data['category_name']:
                #    text_parts.append(f"Categoría: {product_data['category_name']}")
                
                text_for_embedding = " | ".join(text_parts)
                
                # Metadatos del producto
                metadata = {
                    "product_id": int(product_data['id']),
                    "product_name": product_data['name'],
                    "default_code": product_data['default_code'],
                    "category_name": product_data['category_name'],
                    "list_price": float(product_data['list_price']),
                    "product_type": product_data['type'],
                    "active": bool(product_data['active']),
                    "sale_ok": bool(product_data['sale_ok']),
                    "language": "es_EC"
                }
                
                # ID ESTÁVEL por produto para permitir overwrite (evita duplicar embeddings)
                # Se quiser múltiplos nós por produto, reintroduzir sufixos diferenciados.
                node_id = f"product_{product_data['id']}"
                node = TextNode(
                    text=text_for_embedding,
                    metadata=metadata,
                    id_=node_id  # ID único para evitar conflitos
                )
                
                text_nodes.append(node)
                
            except Exception as e:
                _logger.error("Error al procesar producto %s: %s", product_data['id'], str(e))
                continue
        
        return text_nodes

    @api.model
    def index_products(self, domain=None, limit=None, batch_size=50):
        """
        Indexa productos en Elasticsearch generando embeddings con OpenAI
        
        Args:
            domain: Dominio para filtrar productos
            limit: Límite de productos a indexar
            batch_size: Tamaño del lote para procesamiento
            
        Returns:
            dict: Resultado de la indexación
        """
        if not self._validate_dependencies():
            raise UserError(_("Dependencias de LlamaIndex/Elasticsearch no están instaladas"))
        
        try:
            # Valida configuración de OpenAI
            self._get_openai_config()
            
            # Busca productos
            _logger.info("Buscando productos para indexación...")
            products_data = self._get_products_data(domain=domain, limit=limit)
            
            if not products_data:
                return {
                    'success': False,
                    'message': _("Ningún producto encontrado para indexación"),
                    'total_products': 0,
                    'indexed_products': 0,
                }
            
            total_products = len(products_data)
            _logger.info("Productos encontrados: %d", total_products)
            
            # Convierte a TextNodes
            _logger.info("Creando TextNodes para productos...")
            text_nodes = self._create_text_nodes(products_data)
            if not text_nodes:
                return {
                    'success': False,
                    'message': _("Ningún TextNode creado"),
                    'total_products': total_products,
                    'indexed_products': 0,
                }
            
            _logger.info("TextNodes creados: %d", len(text_nodes))
            
            # Crea vector store
            _logger.info("Conectando con Elasticsearch...")
            vector_store = self._create_vector_store()
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            
            # Indexa productos - CREA EMBEDDINGS Y ALMACENA EN ELASTICSEARCH
            _logger.info("Iniciando indexación con generación de embeddings...")
            _logger.info("Este proceso puede tomar varios minutos dependiendo del número de productos...")
            start_time = time.time()
            
            successful_count = 0
            failed_count = 0
            
            try:
                # Procesamiento por lotes para mejor control de errores
                _logger.info("Procesando productos en lotes de %d...", batch_size)
                
                for i in range(0, len(text_nodes), batch_size):
                    batch_nodes = text_nodes[i:i + batch_size]
                    batch_num = (i // batch_size) + 1
                    total_batches = (len(text_nodes) + batch_size - 1) // batch_size
                    
                    try:
                        _logger.info("Procesando lote %d/%d (%d productos)", 
                                   batch_num, total_batches, len(batch_nodes))
                        
                        # Crear un índice para este lote específico
                        # Cada lote se indexa independientemente en Elasticsearch
                        batch_index = VectorStoreIndex(
                            batch_nodes, 
                            storage_context=storage_context, 
                            show_progress=True
                        )
                        
                        successful_count += len(batch_nodes)
                        _logger.info("Lote %d procesado con éxito", batch_num)
                        
                    except Exception as batch_error:
                        _logger.error("Error en lote %d: %s", batch_num, str(batch_error))
                        failed_count += len(batch_nodes)
                        continue
                        
                _logger.info("Indexación por lotes completada")
                
            except Exception as e:
                _logger.error("Error general en la indexación: %s", str(e))
                failed_count = len(text_nodes)
                successful_count = 0
            
            elapsed_time = time.time() - start_time
            
            result = {
                'success': successful_count > 0,
                'message': _("Indexación completada - Embeddings generados y almacenados en Elasticsearch"),
                'total_products': total_products,
                'indexed_products': successful_count,
                'failed_products': failed_count,
                'elapsed_time': elapsed_time,
                'rate_per_minute': (successful_count / elapsed_time * 60) if elapsed_time > 0 else 0,
                'embeddings_generated': True,
                'storage_backend': 'elasticsearch',
            }
            
            _logger.info("Indexación completada: %s", result)
            return result
            
        except Exception as e:
            _logger.error("Error en la indexación: %s", str(e))
            return {
                'success': False,
                'message': str(e),
                'total_products': 0,
                'indexed_products': 0,
                'embeddings_generated': False,
            }

    # --- NUEVO: Eliminación de embeddings de productos ---
    @api.model
    def delete_product_embeddings(self, product_ids):
        """Elimina documentos/embeddings de productos del índice Elasticsearch.

        :param product_ids: lista de IDs de product.template
        :type product_ids: list[int]
        :return: dict con chaves success, deleted, message (opcional)
        """
        if not product_ids:
            return {'success': True, 'deleted': 0}
        if not self._validate_dependencies():
            return {'success': False, 'message': 'Dependencias no instaladas', 'deleted': 0}
        try:
            es_config = self._get_elasticsearch_config()
            from elasticsearch import Elasticsearch
            es_kwargs = {}
            if es_config['auth_type'] == 'basic' and es_config['username'] and es_config['password']:
                es_kwargs['basic_auth'] = (es_config['username'], es_config['password'])
            elif es_config['auth_type'] == 'api_key' and es_config['api_key']:
                es_kwargs['api_key'] = es_config['api_key']
            if not es_config['verify_certs']:
                es_kwargs['verify_certs'] = False
            es = Elasticsearch(es_config['url'], **es_kwargs)
            index_name = es_config['index_name']

            # Usa uma única query terms para remover todos produtos de uma vez
            query = {"query": {"terms": {"product_id": product_ids}}}
            try:
                resp = es.delete_by_query(index=index_name, body=query, conflicts='proceed', refresh=True, ignore=[404])
                deleted = resp.get('deleted', 0)
            except Exception as inner_e:
                _logger.warning("Falha em delete_by_query terms, tentativa individual: %s", inner_e)
                deleted = 0
                for pid in product_ids:
                    q_single = {"query": {"term": {"product_id": pid}}}
                    try:
                        r2 = es.delete_by_query(index=index_name, body=q_single, conflicts='proceed', refresh=True, ignore=[404])
                        deleted += r2.get('deleted', 0)
                    except Exception as inner_e2:
                        _logger.warning("No se pudo eliminar embeddings de producto %s: %s", pid, inner_e2)
                        continue
            return {'success': True, 'deleted': deleted}
        except Exception as e:
            _logger.error("Error eliminando embeddings: %s", e)
            return {'success': False, 'message': str(e), 'deleted': 0}

    # @api.model
    # def search_products(self, query, top_k=5):
    #     """
    #     Busca productos usando consulta en lenguaje natural
    #
    #     Args:
    #         query (str): Consulta en lenguaje natural
    #         top_k (int): Número máximo de resultados
    #
    #     Returns:
    #         list: Lista de productos encontrados
    #     """
    #     if not self._validate_dependencies():
    #         raise UserError(_("Dependencias de LlamaIndex/Elasticsearch no están instaladas"))
    #
    #     if not query or not query.strip():
    #         return []
    #
    #     try:
    #         # Valida configuración de OpenAI
    #         self._get_openai_config()
    #
    #         # Crea vector store para búsqueda
    #         vector_store = self._create_vector_store()
    #         storage_context = StorageContext.from_defaults(vector_store=vector_store)
    #
    #         # Carga índice existente
    #         index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)
    #
    #         # Hace la búsqueda
    #         retriever = index.as_retriever(similarity_top_k=top_k)
    #         results = retriever.retrieve(query.strip())
    #
    #         # Procesa resultados
    #         search_results = []
    #         for i, result in enumerate(results, 1):
    #             metadata = result.metadata
    #
    #             # Busca el producto en Odoo para datos actualizados
    #             product = self.env['product.template'].browse(metadata.get('product_id'))
    #             if not product.exists():
    #                 continue
    #
    #             search_result = {
    #                 'rank': i,
    #                 'product_id': product.id,
    #                 'product': product,
    #                 'product_name': metadata.get('product_name', product.name),
    #                 'default_code': product.default_code or '',
    #                 'list_price': product.list_price,
    #                 'currency_id': product.currency_id,
    #                 'category_name': product.categ_id.complete_name if product.categ_id else '',
    #                 'score': result.get_score() if hasattr(result, 'get_score') else 0.0,
    #                 'matched_text': result.get_text(),
    #             }
    #             search_results.append(search_result)
    #
    #         _logger.info("Búsqueda realizada: '%s' - %d resultados encontrados", query, len(search_results))
    #         return search_results
    #
    #     except Exception as e:
    #         _logger.error("Error en la búsqueda: %s", str(e))
    #         raise UserError(_("Error en la búsqueda: %s") % str(e))


    @api.model
    def search_products(self, query, top_k=5):
        """
        Busca productos con IA (LlamaIndex) y retorna solo los publicados
        que tengan stock >= 1 en la bodega 386. Aplica top_k después del filtro.
        Incluye warehouse_id y warehouse_name en cada resultado.
        """
        if not self._validate_dependencies():
            raise UserError(_("Dependencias de LlamaIndex/Elasticsearch no están instaladas"))

        if not query or not query.strip():
            return []

        try:
            self._get_openai_config()

            vector_store = self._create_vector_store()
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            try:
                index = VectorStoreIndex.from_vector_store(
                    vector_store=vector_store,
                    storage_context=storage_context,
                )
            except Exception:
                raise UserError(_("No existe un índice de productos. Genéralo antes de buscar."))

            try:
                top_k = int(top_k or 5)
            except Exception:
                top_k = 5
            candidate_k = max(top_k * 5, top_k)

            retriever = index.as_retriever(similarity_top_k=candidate_k)
            results = retriever.retrieve(query.strip())

            candidates, product_ids = [], []
            for r in results:
                md = getattr(r, "metadata", None) or getattr(getattr(r, "node", None), "metadata", {}) or {}
                pid = md.get("product_id")
                try:
                    pid = int(pid)
                except Exception:
                    pid = None
                if not pid:
                    continue

                score = getattr(r, "score", None)
                if score is None and hasattr(r, "get_score"):
                    try:
                        score = float(r.get_score() or 0.0)
                    except Exception:
                        score = 0.0
                else:
                    try:
                        score = float(score or 0.0)
                    except Exception:
                        score = 0.0

                text = getattr(r, "text", None)
                if not text and hasattr(r, "node") and getattr(r, "node"):
                    try:
                        text = r.node.get_content(metadata_mode="none")
                    except Exception:
                        text = ""

                candidates.append({
                    "product_id": pid,
                    "metadata": md,
                    "score": score,
                    "matched_text": text or "",
                })
                product_ids.append(pid)

            ProductT = self.env["product.template"].sudo()
            published_field = "is_published" if "is_published" in ProductT._fields else "website_published"
            published_products = ProductT.search([
                ("id", "in", list(set(product_ids))),
                (published_field, "=", True),
            ])
            published_map = {p.id: p for p in published_products}

            warehouse_id = 386
            wh = self.env["stock.warehouse"].sudo().browse(warehouse_id)
            if not wh.exists():
                raise UserError(_("No se encontró la bodega con ID %s") % warehouse_id)

            tmpl_ids = list(published_map.keys())
            variants = self.env["product.product"].search([("product_tmpl_id", "in", tmpl_ids)])

            available_by_tmpl = {}
            if variants:
                quants = self.env["stock.quant"].sudo().read_group(
                    domain=[
                        ("product_id", "in", variants.ids),
                        ("location_id", "child_of", wh.view_location_id.id),
                    ],
                    fields=["product_id", "quantity", "reserved_quantity"],
                    groupby=["product_id"],
                    lazy=False,
                )
                avail_by_variant = {
                    q["product_id"][0]: (q.get("quantity", 0.0) - q.get("reserved_quantity", 0.0))
                    for q in quants
                }
                from collections import defaultdict
                acc = defaultdict(float)
                for v in variants:
                    acc[v.product_tmpl_id.id] += avail_by_variant.get(v.id, 0.0)
                available_by_tmpl = dict(acc)

            search_results, rank = [], 0
            for item in candidates:
                product = published_map.get(item["product_id"])
                if not product or not product.exists():
                    continue

                available_qty = float(available_by_tmpl.get(product.id, 0.0))
                if available_qty < 1.0:
                    continue

                rank += 1
                search_results.append({
                    "rank": rank,
                    "product_id": product.id,
                    "product": product,
                    "product_name": item["metadata"].get("product_name") or product.display_name or product.name,
                    "default_code": product.default_code or "",
                    "list_price": product.list_price,
                    "currency_id": product.currency_id,
                    "category_name": product.categ_id.complete_name if product.categ_id else "",
                    "score": item["score"],
                    "matched_text": item["matched_text"],
                    "uom_po_id": product.uom_po_id.name if product.uom_po_id else "",
                    "warehouse_id": wh.id,
                    "warehouse_name": wh.name,
                    "available_qty": available_qty,
                    # "id": product.id,
                    # "name": item["metadata"].get("product_name") or product.display_name or product.name,
                    # "price": p.list_price * p.uom_po_id.factor_inv if p.sale_uom_ecommerce else p.list_price,
                    "price": (
                        (product.list_price * product.uom_po_id.factor_inv if product.sale_uom_ecommerce else product.list_price)
                        * (1 + (sum(t.amount for t in product.taxes_id) / 100))
                        if product.taxes_id else
                        (product.list_price * product.uom_po_id.factor_inv if product.sale_uom_ecommerce else product.list_price)
                    )
                })
                if len(search_results) >= top_k:
                    break
            return search_results

        except UserError:
            raise
        except Exception as e:
            _logger.exception("Error en search_products")
            raise UserError(_("Error en la búsqueda: %s") % str(e))


    @api.model
    def query_with_answer(self, query):
        """
        Hace consulta y retorna respuesta generada por LLM
        
        Args:
            query (str): Pregunta en lenguaje natural
            
        Returns:
            str: Respuesta generada
        """
        if not self._validate_dependencies():
            raise UserError(_("Dependencias de LlamaIndex/Elasticsearch no están instaladas"))
        
        if not query or not query.strip():
            return ""
        
        try:
            # Valida configuración de OpenAI
            self._get_openai_config()
            
            # Crea vector store
            vector_store = self._create_vector_store()
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            
            # Carga índice existente
            index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)
            
            # Crea query engine
            query_engine = index.as_query_engine()
            
            # Hace la pregunta
            response = query_engine.query(query.strip())
            
            _logger.info("Consulta con respuesta: '%s'", query)
            return str(response)
            
        except Exception as e:
            _logger.error("Error en la consulta: %s", str(e))
            raise UserError(_("Error en la consulta: %s") % str(e))

    @api.model
    def _encode_image_to_base64(self, image_data):
        """
        Convierte datos de imagen a base64
        
        Args:
            image_data: Datos de la imagen (bytes o archivo)
            
        Returns:
            str: Imagen codificada en base64
        """
        try:
            if isinstance(image_data, bytes):
                return base64.b64encode(image_data).decode('utf-8')
            elif hasattr(image_data, 'read'):
                # Si es un archivo
                return base64.b64encode(image_data.read()).decode('utf-8')
            else:
                raise ValueError("Formato de imagen no soportado")
        except Exception as e:
            _logger.error("Error al codificar imagen: %s", str(e))
            raise UserError(_("Error al procesar imagen: %s") % str(e))

    @api.model
    def _validate_image_format(self, image_data):
        """
        Valida formato de imagen
        
        Args:
            image_data: Datos de la imagen
            
        Returns:
            bool: True si es válido
        """
        try:
            if isinstance(image_data, bytes):
                image = Image.open(io.BytesIO(image_data))
            else:
                image = Image.open(image_data)
            
            # Valida formato
            if image.format not in ['JPEG', 'PNG', 'JPG', 'WEBP']:
                return False
            
            # Valida tamaño (max 20MB)
            if hasattr(image_data, '__len__') and len(image_data) > 20 * 1024 * 1024:
                return False
                
            return True
        except Exception as e:
            _logger.error("Error al validar imagen: %s", str(e))
            return False

    @api.model
    def analyze_prescription_image(self, image_data, image_format='auto'):
        """
        Analiza una imagen de receta médica usando GPT-4 Vision
        
        Args:
            image_data: Datos de la imagen (bytes o base64)
            image_format: Formato de la imagen ('auto', 'jpeg', 'png', etc.)
            
        Returns:
            dict: Información extraída de la receta
        """
        if not self._validate_dependencies():
            raise UserError(_("Dependencias de OpenAI no están instaladas"))
        
        try:
            # Valida configuración de OpenAI
            openai_config = self._get_openai_config()
            
            # Valida imagen
            if not self._validate_image_format(image_data):
                raise UserError(_("Formato de imagen no válido. Use JPEG, PNG o WEBP"))
            
            # Codifica imagen a base64
            base64_image = self._encode_image_to_base64(image_data)
            
            # Detecta formato si es auto
            if image_format == 'auto':
                try:
                    if isinstance(image_data, bytes):
                        image = Image.open(io.BytesIO(image_data))
                    else:
                        image = Image.open(image_data)
                    image_format = image.format.lower()
                except:
                    image_format = 'jpeg'
            
            # Prepara prompt para análisis de receta médica
            system_prompt = """Eres un experto farmacéutico analizando recetas médicas e imagens de medicamentos. Tu ÚNICA tarea es identificar y extraer los NOMBRES DE MEDICAMENTOS con la máxima precisión.

INSTRUCCIONES CRÍTICAS:
1. ENFÓCATE EXCLUSIVAMENTE en extraer nombres de medicamentos
2. Identifica tanto nombres comerciales como principios activos
3. Para cada medicamento, extrae: nombre comercial, principio activo, dosificación y forma farmacéutica
4. Si hay dudas entre nombres, incluye el más probable
5. NO extraigas información de paciente, médico o diagnóstico

ESTRUCTURA DE RESPUESTA EN JSON (SOLO MEDICAMENTOS):
{
    "medicamentos": [
        {
            "nombre": "Nombre comercial exacto del medicamento",
            "principio_activo": "Principio activo si es diferente del nombre",
            "dosificacion": "mg/ml/etc si visible",
            "forma_farmaceutica": "tabletas/jarabe/crema/etc si visible",
            "confianza_nombre": 0.95
        }
    ],
    "total_medicamentos": 1,
    "analisis_exitoso": true
}

REGLAS DE EXTRACCIÓN:
- PRIORIDAD 1: Nombre comercial del medicamento
- PRIORIDAD 2: Principio activo (si es diferente del nombre comercial)
- Si NO puedes leer un medicamento claramente, marca nombre como "medicamento_no_legible_X"
- Si texto está borroso pero reconoces patrones de medicamento, haz tu mejor estimación
- Marca confianza_nombre de 0.0 a 1.0 según qué tan seguro estés del nombre
- NO incluyas información de paciente, médico, fecha o diagnóstico

EJEMPLOS DE MEDICAMENTOS A BUSCAR:
- Paracetamol, Ibuprofeno, Amoxicilina
- Losartán, Metformina, Omeprazol  
- Cualquier nombre que termine en sufijos como -ol, -ina, -zol, etc.
- Marcas comerciales conocidas"""

            # Hace llamada a OpenAI Vision
            client = openai.OpenAI(api_key=openai_config['api_key'])
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analiza esta receta médica y extrae ÚNICAMENTE los nombres de medicamentos con sus principios activos. Ignora información de paciente, médico o diagnóstico:"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image_format};base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.1
            )
            
            # Procesa respuesta
            response_text = response.choices[0].message.content

            _logger.warning("Respuesta de GPT-4 Vision: %s", response_text)
            
            # Limpia marcaciones markdown del JSON si existen
            cleaned_text = response_text.strip()
            if cleaned_text.startswith('```json'):
                # Elimina bloques de código markdown
                cleaned_text = cleaned_text.replace('```json', '').replace('```', '').strip()
            elif cleaned_text.startswith('```'):
                # Si solo tiene ``` sin especificar json
                cleaned_text = cleaned_text.replace('```', '').strip()
            
            # Intenta parsear JSON
            try:
                import json
                prescription_data = json.loads(cleaned_text)
                
                # Valida que al menos tengamos medicamentos
                if not prescription_data.get('medicamentos'):
                    prescription_data['medicamentos'] = []
                
                # Asegura que cada medicamento tenga al menos un nombre
                for i, med in enumerate(prescription_data['medicamentos']):
                    if not med.get('nombre') or med['nombre'] in ['', 'no_legible']:
                        med['nombre'] = f"Medicamento_{i+1}"
                    if not med.get('confianza_nombre'):
                        med['confianza_nombre'] = 0.5
                        
            except json.JSONDecodeError as e:
                # Si no es JSON válido, intenta extraer medicamentos del texto
                _logger.warning("Respuesta no es JSON válido: %s. Texto limpio: %s", str(e), cleaned_text[:200])
                prescription_data = {
                    "medicamentos": [],
                    "raw_analysis": response_text,
                    "analisis_exitoso": False
                }
                
                # Busca patrones de medicamentos en el texto
                import re
                lines = response_text.split('\n')
                med_count = 1
                for line in lines:
                    # Busca líneas que podrían contener nombres de medicamentos
                    if any(keyword in line.lower() for keyword in ['mg', 'ml', 'tableta', 'capsula', 'jarabe', 'cada']):
                        prescription_data['medicamentos'].append({
                            'nombre': f"Medicamento_extraido_{med_count}",
                            'raw_text': line.strip(),
                            'confianza_nombre': 0.3
                        })
                        med_count += 1
            
            _logger.info("Receta médica analizada exitosamente")
            return prescription_data
            
        except Exception as e:
            _logger.error("Error al analizar receta médica: %s", str(e))
            raise UserError(_("Error al analizar receta médica: %s") % str(e))

    @api.model
    def search_products_from_prescription(self, prescription_data, top_k=10):
        """
        Busca productos basándose en la información extraída de una receta médica
        
        Args:
            prescription_data: Datos extraídos de la receta médica
            top_k: Número máximo de resultados por medicamento
            
        Returns:
            dict: Resultados de búsqueda organizados por medicamento
        """
        if not prescription_data or not prescription_data.get('medicamentos'):
            return {'error': _("No se encontraron medicamentos en la receta")}
        
        search_results = {
            'medicamentos_encontrados': [],
            'medicamentos_no_encontrados': [],
            'total_medicamentos': len(prescription_data['medicamentos']),
            'resumen': {}
        }
        
        for medicamento in prescription_data['medicamentos']:
            try:
                # Estrategia de búsqueda priorizando nombre comercial
                confianza = medicamento.get('confianza_nombre', 0.5)
                nombre = medicamento.get('nombre', '')
                principio_activo = medicamento.get('principio_activo', '')
                
                # PASO 1: Buscar por nombre comercial primero
                productos_encontrados = []
                query_usada = ""
                
                if nombre and nombre not in ['no_legible', 'no_visible'] and not nombre.startswith('medicamento_no_legible'):
                    query_usada = nombre.strip()
                    _logger.info(f"Búsqueda 1 - Nombre comercial: '{query_usada}' (confianza: {confianza:.2f})")
                    productos_encontrados = self.search_products(query_usada, top_k=top_k)
                
                # PASO 2: Si no encontramos resultados suficientes, buscar por principio activo
                if (not productos_encontrados or len(productos_encontrados) < 3) and principio_activo:
                    if principio_activo not in ['no_legible', 'no_visible'] and principio_activo != nombre:
                        query_principio = principio_activo.strip()
                        _logger.info(f"Búsqueda 2 - Principio activo: '{query_principio}'")
                        productos_principio = self.search_products(query_principio, top_k=top_k)
                        
                        # Combinar resultados evitando duplicados
                        productos_existentes_ids = {p['product_id'] for p in productos_encontrados}
                        for producto in productos_principio:
                            if producto['product_id'] not in productos_existentes_ids:
                                productos_encontrados.append(producto)
                        
                        if query_usada:
                            query_usada += f" | {query_principio}"
                        else:
                            query_usada = query_principio
                
                # PASO 3: Si aún no hay resultados, usar texto crudo si existe
                if not productos_encontrados and medicamento.get('raw_text'):
                    raw_text = medicamento['raw_text'].strip()
                    # Limpiar el texto crudo básicamente
                    raw_clean = ' '.join(raw_text.split()[:3])  # Solo primeras 3 palabras
                    _logger.info(f"Búsqueda 3 - Texto crudo: '{raw_clean}'")
                    productos_encontrados = self.search_products(raw_clean, top_k=top_k)
                    query_usada = raw_clean
                
                # Registrar resultados
                if productos_encontrados:
                    search_results['medicamentos_encontrados'].append({
                        'medicamento_original': medicamento,
                        'query_utilizada': query_usada,
                        'productos': productos_encontrados,
                        'total_productos': len(productos_encontrados),
                        'metodo_busqueda': 'nombre_comercial' if nombre in query_usada else 'principio_activo'
                    })
                else:
                    search_results['medicamentos_no_encontrados'].append({
                        'medicamento_original': medicamento,
                        'query_utilizada': query_usada or 'sin_terminos_validos',
                        'razon': 'No se encontraron productos coincidentes'
                    })
                    
            except Exception as e:
                _logger.error("Error al buscar medicamento %s: %s", medicamento, str(e))
                search_results['medicamentos_no_encontrados'].append({
                    'medicamento_original': medicamento,
                    'razon': f'Error en búsqueda: {str(e)}'
                })
        
        # Genera resumen
        search_results['resumen'] = {
            'encontrados': len(search_results['medicamentos_encontrados']),
            'no_encontrados': len(search_results['medicamentos_no_encontrados']),
            'tasa_exito': len(search_results['medicamentos_encontrados']) / max(1, search_results['total_medicamentos'])
        }
        
        return search_results

    @api.model
    def process_prescription_image_complete(self, image_data, image_format='auto', top_k=10):
        """
        Proceso completo: analiza imagen de receta y busca productos
        
        Args:
            image_data: Datos de la imagen
            image_format: Formato de la imagen
            top_k: Número máximo de productos por medicamento
            
        Returns:
            dict: Análisis completo y resultados de búsqueda
        """
        try:
            # Analiza la receta médica
            _logger.info("Iniciando análisis de receta médica...")
            prescription_analysis = self.analyze_prescription_image(image_data, image_format)
            
            # Busca productos
            _logger.info("Buscando productos para medicamentos encontrados...")
            search_results = self.search_products_from_prescription(prescription_analysis, top_k)
            
            # Combina resultados
            complete_result = {
                'receta_analizada': prescription_analysis,
                'busqueda_productos': search_results,
                'timestamp': time.time(),
                'exito': True
            }
            
            _logger.info("Proceso completo de receta médica finalizado exitosamente")
            return complete_result
            
        except Exception as e:
            _logger.error("Error en proceso completo de receta: %s", str(e))
            return {
                'error': str(e),
                'exito': False,
                'timestamp': time.time()
            }

    @api.model
    def check_index_status(self):
        """
        Verifica estado del índice de Elasticsearch
        
        Returns:
            dict: Estado del índice
        """
        if not self._validate_dependencies():
            return {
                'exists': False,
                'error': _("Dependencias no instaladas")
            }
        
        try:
            vector_store = self._create_vector_store()
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            
            # Intenta cargar el índice
            index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)
            
            # Prueba búsqueda simple
            retriever = index.as_retriever(similarity_top_k=1)
            results = retriever.retrieve("test")
            
            # Obtiene nombre del índice de Elasticsearch
            index_name = self._get_elasticsearch_config()['index_name']
            
            return {
                'exists': True,
                'has_data': len(results) > 0,
                'sample_results': len(results),
                'index_name': index_name,
                'vector_store_type': 'elasticsearch',
            }
            
        except Exception as e:
            return {
                'exists': False,
                'error': str(e),
                'vector_store_type': 'elasticsearch',
            }
