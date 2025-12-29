import json
from odoo.http import request
import logging
import re
import unicodedata
from difflib import SequenceMatcher

from .invoice_flow import InvoiceFlow
from .product_asesor import ProductAsesorFlow
from .saveOdoo import SaveOdoo
from ..templates.meta_api import MetaAPi
from ..utils.user_session import UserSession
from odoo import fields
from decimal import Decimal, ROUND_HALF_UP

_logger = logging.getLogger(__name__)


class FuzzyProductSearch:
    """Clase para búsqueda de productos tolerante a errores tipográficos."""

    # Stopwords en español - palabras comunes que no aportan a la búsqueda de productos
    SPANISH_STOPWORDS = {
        # Verbos comunes de solicitud
        'quiero', 'quiere', 'queremos', 'quisiera', 'quisieras',
        'necesito', 'necesita', 'necesitamos', 'necesitan',
        'dame', 'deme', 'deme', 'denos', 'da', 'den',
        'busco', 'busca', 'buscamos', 'buscan',
        'tengo', 'tiene', 'tenemos', 'tienen',
        'hay', 'tienen', 'venden', 'vende',
        'pido', 'pide', 'pedimos', 'piden',
        'ocupo', 'ocupa', 'ocupamos',
        'requiero', 'requiere', 'requerimos',
        'deseo', 'desea', 'deseamos',
        'compro', 'compra', 'compramos',
        'llevo', 'lleva', 'llevamos',
        # Artículos
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
        # Preposiciones
        'de', 'del', 'a', 'al', 'en', 'con', 'sin', 'por', 'para',
        'sobre', 'bajo', 'entre', 'hacia', 'hasta', 'desde',
        # Pronombres
        'me', 'te', 'se', 'nos', 'les', 'lo', 'le',
        'yo', 'tu', 'el', 'ella', 'usted', 'nosotros', 'ustedes', 'ellos',
        'mi', 'mis', 'su', 'sus', 'nuestro', 'nuestra',
        # Conjunciones
        'y', 'o', 'e', 'u', 'ni', 'pero', 'sino', 'que', 'como',
        # Adverbios comunes
        'mas', 'muy', 'mucho', 'poco', 'bien', 'mal', 'si', 'no',
        'ya', 'aun', 'todavia', 'tambien', 'solo', 'siempre', 'nunca',
        'aqui', 'ahi', 'alli', 'donde', 'cuando', 'ahora', 'hoy',
        # Expresiones de cortesía
        'por', 'favor', 'porfavor', 'porfa', 'gracias', 'please',
        # Palabras interrogativas
        'que', 'cual', 'cuales', 'quien', 'quienes', 'cuanto', 'cuantos',
        'cuanta', 'cuantas', 'como', 'donde', 'cuando', 'porque',
        # Otros comunes
        'este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas',
        'algo', 'nada', 'todo', 'todos', 'alguno', 'alguna', 'algunos',
        'cada', 'otro', 'otra', 'otros', 'otras', 'mismo', 'misma',
        'ser', 'estar', 'tener', 'haber', 'poder', 'deber',
        'es', 'son', 'era', 'fue', 'sido', 'siendo',
        'esta', 'estan', 'estaba', 'estuvo',
        'puedo', 'puede', 'pueden', 'podria',
        'debo', 'debe', 'deben',
        'hola', 'buenas', 'buenos', 'dias', 'tardes', 'noches',
    }

    # Mapeo de caracteres fonéticamente similares en español
    PHONETIC_MAP = {
        'v': 'b', 'z': 's', 'c': 's', 'qu': 'k', 'q': 'k',
        'x': 's', 'h': '', 'll': 'y', 'ñ': 'n', 'ge': 'je',
        'gi': 'ji', 'gue': 'ge', 'gui': 'gi', 'ce': 'se',
        'ci': 'si', 'rr': 'r', 'ph': 'f', 'w': 'u',
    }

    # Letras que se confunden comúnmente al escribir
    COMMON_TYPOS = {
        'a': ['s', 'q', 'z'],
        'b': ['v', 'n', 'g'],
        'c': ['x', 'v', 's'],
        'd': ['s', 'f', 'e'],
        'e': ['r', 'w', '3'],
        'f': ['g', 'd', 'r'],
        'g': ['h', 'f', 't'],
        'i': ['o', 'u', '1'],
        'l': ['k', '1', 'i'],
        'm': ['n', ','],
        'n': ['m', 'b'],
        'o': ['p', 'i', '0'],
        'p': ['o', 'l'],
        'r': ['t', 'e'],
        's': ['a', 'd', 'z'],
        't': ['r', 'y', 'g'],
        'u': ['y', 'i'],
        'v': ['b', 'c'],
        'y': ['u', 't'],
        'z': ['s', 'x', 'a'],
    }

    @classmethod
    def normalize_text(cls, text):
        """Normaliza texto: quita tildes, minúsculas, solo alfanumérico."""
        if not text:
            return ""
        # Convertir a minúsculas
        text = text.lower()
        # Quitar tildes
        text = ''.join(c for c in unicodedata.normalize('NFD', text)
                       if unicodedata.category(c) != 'Mn')
        # Solo letras y números
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return text.strip()

    @classmethod
    def extract_keywords(cls, text, min_length=2):
        """
        Extrae palabras clave de un texto eliminando stopwords y números solos.

        Args:
            text: Texto de entrada del usuario (ej: "quiero vitamina", "me da 1 vitamina")
            min_length: Longitud mínima de palabras a considerar

        Returns:
            Lista de palabras clave relevantes para búsqueda de productos
        """
        if not text:
            return []

        # Normalizar texto
        normalized = cls.normalize_text(text)

        # Dividir en palabras
        words = normalized.split()

        # Filtrar stopwords, números solos y palabras muy cortas
        keywords = []
        for word in words:
            # Ignorar si es solo números (cantidades como "1", "2", etc.)
            if word.isdigit():
                continue
            # Ignorar palabras muy cortas
            if len(word) < min_length:
                continue
            # Ignorar stopwords
            if word in cls.SPANISH_STOPWORDS:
                continue
            # Agregar como palabra clave
            keywords.append(word)

        return keywords

    @classmethod
    def get_search_terms_from_natural_language(cls, user_input):
        """
        Procesa entrada en lenguaje natural y retorna términos de búsqueda optimizados.

        Args:
            user_input: Texto del usuario (ej: "me da 1 vitamina por favor")

        Returns:
            Lista de términos de búsqueda ordenados por relevancia
        """
        keywords = cls.extract_keywords(user_input)

        if not keywords:
            # Si no quedan palabras después de filtrar, intentar con el texto original normalizado
            normalized = cls.normalize_text(user_input)
            # Quitar solo números y palabras de una letra
            words = [w for w in normalized.split() if len(w) > 1 and not w.isdigit()]
            return words if words else [normalized] if normalized else []

        return keywords

    @classmethod
    def get_phonetic_key(cls, word):
        """Genera una clave fonética simplificada para español."""
        if not word:
            return ""
        word = cls.normalize_text(word)

        # Aplicar reemplazos fonéticos (ordenados por longitud descendente)
        for original, replacement in sorted(cls.PHONETIC_MAP.items(),
                                            key=lambda x: len(x[0]), reverse=True):
            word = word.replace(original, replacement)

        # Eliminar vocales duplicadas consecutivas
        word = re.sub(r'([aeiou])\1+', r'\1', word)
        # Eliminar consonantes duplicadas consecutivas
        word = re.sub(r'([bcdfghjklmnpqrstvwxyz])\1+', r'\1', word)

        return word

    @classmethod
    def get_trigrams(cls, text):
        """Genera trigramas (grupos de 3 caracteres) de un texto."""
        text = cls.normalize_text(text)
        if len(text) < 3:
            return {text} if text else set()

        trigrams = set()
        # Agregar marcadores de inicio y fin
        padded = f"  {text}  "
        for i in range(len(padded) - 2):
            trigrams.add(padded[i:i + 3])
        return trigrams

    @classmethod
    def trigram_similarity(cls, text1, text2):
        """Calcula similitud basada en trigramas (coeficiente de Jaccard)."""
        tg1 = cls.get_trigrams(text1)
        tg2 = cls.get_trigrams(text2)

        if not tg1 or not tg2:
            return 0.0

        intersection = len(tg1 & tg2)
        union = len(tg1 | tg2)

        return intersection / union if union > 0 else 0.0

    @classmethod
    def levenshtein_similarity(cls, s1, s2):
        """Calcula similitud usando SequenceMatcher (similar a Levenshtein)."""
        s1 = cls.normalize_text(s1)
        s2 = cls.normalize_text(s2)

        if not s1 or not s2:
            return 0.0

        return SequenceMatcher(None, s1, s2).ratio()

    @classmethod
    def phonetic_match(cls, word1, word2):
        """Verifica si dos palabras suenan similar."""
        key1 = cls.get_phonetic_key(word1)
        key2 = cls.get_phonetic_key(word2)

        if not key1 or not key2:
            return 0.0

        # Si las claves fonéticas son iguales, alta coincidencia
        if key1 == key2:
            return 1.0

        # Comparar claves fonéticas con Levenshtein
        return SequenceMatcher(None, key1, key2).ratio()

    @classmethod
    def word_starts_with_fuzzy(cls, word, prefix, threshold=0.7):
        """Verifica si una palabra comienza con un prefijo (con tolerancia)."""
        word = cls.normalize_text(word)
        prefix = cls.normalize_text(prefix)

        if not word or not prefix:
            return False

        # Coincidencia exacta de prefijo
        if word.startswith(prefix):
            return True

        # Comparar solo la parte inicial de la palabra
        word_prefix = word[:len(prefix) + 1] if len(word) > len(prefix) else word
        return SequenceMatcher(None, word_prefix, prefix).ratio() >= threshold

    @classmethod
    def calculate_match_score(cls, search_term, product_name, category_name="", parent_category=""):
        """
        Calcula un puntaje de coincidencia combinando múltiples algoritmos.
        Retorna un valor entre 0 y 100.
        """
        search_normalized = cls.normalize_text(search_term)
        name_normalized = cls.normalize_text(product_name)

        if not search_normalized or not name_normalized:
            return 0

        scores = []

        # 1. Coincidencia exacta de subcadena (máxima prioridad)
        if search_normalized in name_normalized:
            return 100

        # 2. Coincidencia por palabras individuales
        search_words = search_normalized.split()
        name_words = name_normalized.split()

        word_matches = 0
        for sw in search_words:
            best_word_score = 0
            for nw in name_words:
                # Levenshtein
                lev_score = cls.levenshtein_similarity(sw, nw)
                # Trigramas
                tri_score = cls.trigram_similarity(sw, nw)
                # Fonético
                phon_score = cls.phonetic_match(sw, nw)
                # Prefijo fuzzy
                prefix_bonus = 0.2 if cls.word_starts_with_fuzzy(nw, sw) else 0

                # Combinar scores (ponderado)
                combined = (lev_score * 0.4 + tri_score * 0.3 + phon_score * 0.3) + prefix_bonus
                best_word_score = max(best_word_score, min(combined, 1.0))

            if best_word_score >= 0.6:  # Umbral para considerar match
                word_matches += best_word_score

        # Score basado en coincidencia de palabras
        if search_words:
            word_score = (word_matches / len(search_words)) * 80
            scores.append(word_score)

        # 3. Similitud general del texto completo
        overall_lev = cls.levenshtein_similarity(search_term, product_name) * 70
        overall_tri = cls.trigram_similarity(search_term, product_name) * 70
        scores.append((overall_lev + overall_tri) / 2)

        # 4. Bonus por coincidencia en categoría
        if category_name:
            cat_normalized = cls.normalize_text(category_name)
            if search_normalized in cat_normalized:
                scores.append(60)
            elif cls.levenshtein_similarity(search_term, category_name) > 0.7:
                scores.append(50)

        if parent_category:
            parent_normalized = cls.normalize_text(parent_category)
            if search_normalized in parent_normalized:
                scores.append(55)

        # Retornar el mejor score
        return max(scores) if scores else 0

    @classmethod
    def search_products_fuzzy(cls, search_term, products, threshold=45):
        """
        Busca productos con tolerancia a errores tipográficos.

        Args:
            search_term: Término de búsqueda del usuario
            products: Lista de productos (recordset o lista de dicts)
            threshold: Puntaje mínimo para considerar coincidencia (0-100)

        Returns:
            Lista de productos ordenados por relevancia
        """
        if not search_term or not products:
            return []

        results = []

        for product in products:
            # Obtener datos del producto
            if hasattr(product, 'name'):
                # Es un recordset de Odoo
                name = product.name or ""
                category = product.categ_id.name if product.categ_id else ""
                parent_cat = product.categ_id.parent_id.name if product.categ_id and product.categ_id.parent_id else ""
                product_data = product
            else:
                # Es un diccionario
                name = product.get('name', '')
                category = product.get('category', '')
                parent_cat = product.get('parent_category', '')
                product_data = product

            # Calcular score
            score = cls.calculate_match_score(search_term, name, category, parent_cat)

            if score >= threshold:
                results.append({
                    'product': product_data,
                    'score': score,
                    'name': name
                })

        # Ordenar por score descendente
        results.sort(key=lambda x: x['score'], reverse=True)

        return results


class BuyProductFlow:

    @classmethod
    def _get_default_warehouse_id(cls):
        """Obtiene el warehouse por defecto desde configuración."""
        config_param = request.env['ir.config_parameter'].sudo()
        warehouse_id = config_param.get_param('chatbot.default_warehouse_id')#386

        if warehouse_id:
            try:
                return int(warehouse_id)
            except (ValueError, TypeError):
                pass

        # Fallback: primer warehouse de la compañía actual
        company = request.env.company
        warehouse = request.env['stock.warehouse'].sudo().search([
            ('company_id', '=', company.id)
        ], limit=1)

        if warehouse:
            return warehouse.id

        # Último fallback: cualquier warehouse activo
        warehouse = request.env['stock.warehouse'].sudo().search([], limit=1)
        return warehouse.id if warehouse else False

    @classmethod
    def start_flow(cls, number, mensaje_texto=None):
        user_session = UserSession(request.env)
        session = user_session.get_session(number)

        orden_data = {}
        if session.orden:
            try:
                orden_data = json.loads(session.orden)
            except Exception:
                orden_data = {}

        user_session.update_session(number, state="promociones", orden=json.dumps(orden_data))
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('search')
        MetaAPi.enviar_mensaje_texto(number, mensaje)
        user_session.update_session(number, state="buscar_producto")
        return {"status": "sent", "action": "buscar_producto"}

    @classmethod
    def parse_search_input(cls, search_term):
        """Normaliza y divide el término de búsqueda en tokens."""
        if not search_term:
            return []

        def normalize_text(text):
            text = ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                           if unicodedata.category(c) != 'Mn')
            text = re.sub(r'[^a-z0-9\s]', '', text)
            return [t.strip() for t in text.split() if t.strip()]

        return normalize_text(search_term)

    @classmethod
    def build_search_domain(cls, terms):
        """Construye el dominio de búsqueda dinámico basado en los términos."""
        domain = []
        for term in terms:
            subdom = [
                '|', '|',
                ('categ_id.parent_id.name', 'ilike', term),
                ('categ_id.name', 'ilike', term),
                ('name', 'ilike', term),
            ]
            if domain:
                domain = ['&'] + domain + subdom
            else:
                domain = subdom

        domain += [('is_published', '=', True)]
        return domain

    @classmethod
    def filter_products_server_side(cls, products, warehouse_id, search_term):
        if not products:
            return []

        normalized_search = cls.parse_search_input(search_term)
        search_term_normalized = ' '.join(normalized_search)

        warehouse = request.env['stock.warehouse'].sudo().browse(warehouse_id)
        location_id = warehouse.lot_stock_id.id
        resultado = []

        for p in products:
            # Verificar variante
            variant = request.env['product.product'].sudo().search(
                [('product_tmpl_id', '=', p.id)], limit=1)
            if not variant:
                _logger.warning(f"No variant found for product template: {p.name} (id: {p.id})")
                continue

            # Buscar quants con cantidades a mano y reservadas
            quants = request.env['stock.quant'].sudo().read_group(
                [
                    ('product_id', '=', variant.id),
                    ('location_id', 'child_of', location_id),
                ],
                ['inventory_quantity_auto_apply:sum', 'reserved_quantity:sum'],
                []
            )

            qty_on_hand = quants and quants[0].get('inventory_quantity_auto_apply') or 0.0
            qty_reserved = quants and quants[0].get('reserved_quantity') or 0.0
            available_qty = qty_on_hand - qty_reserved

            if available_qty <= 0:
                continue

            relevance = 100 if search_term_normalized in cls.parse_search_input(p.name) else 50

            resultado.append({
                "id": p.id,
                "name": p.name,
                "price": (
                    (p.list_price * p.uom_po_id.factor_inv if p.sale_uom_ecommerce else p.list_price)
                    * (1 + (sum(t.amount for t in p.taxes_id) / 100))
                    if p.taxes_id else
                    (p.list_price * p.uom_po_id.factor_inv if p.sale_uom_ecommerce else p.list_price)
                ),
                "stock": available_qty,
                "uom_po_id": p.uom_po_id.name if p.uom_po_id else " ",
                "category": p.categ_id.name or "Sin categoría",
                "parent_category": (p.categ_id.parent_id.name
                                    if p.categ_id.parent_id
                                    else "Sin categoría padre"),
                "relevance": relevance
            })

        return sorted(resultado, key=lambda x: x['relevance'], reverse=True)[:5]

    @classmethod
    def get_product_quantity(cls, search_term, warehouse_id):
        """
        Método principal para buscar productos con stock usando búsqueda fuzzy.
        Ahora soporta lenguaje natural extrayendo palabras clave.

        Ejemplos de entrada soportados:
        - "vitamina" -> busca "vitamina"
        - "quiero vitamina" -> extrae y busca "vitamina"
        - "me da 1 vitamina por favor" -> extrae y busca "vitamina"
        """
        try:
            # 0. Extraer palabras clave del lenguaje natural
            keywords = FuzzyProductSearch.get_search_terms_from_natural_language(search_term)

            if not keywords:
                # Fallback al término original si no se extraen palabras clave
                terms = cls.parse_search_input(search_term)
                if not terms:
                    return []
                keywords = terms

            # 1. Intentar búsqueda con cada palabra clave individualmente
            all_results = []
            searched_product_ids = set()

            for keyword in keywords:
                terms = cls.parse_search_input(keyword)
                if not terms:
                    continue

                # Búsqueda exacta con ilike
                domain = cls.build_search_domain(terms)
                products = request.env['product.template'].sudo().search(domain, limit=30)

                result = cls.filter_products_server_side(products, warehouse_id, keyword)

                # Agregar resultados únicos
                for r in result:
                    if r['id'] not in searched_product_ids:
                        searched_product_ids.add(r['id'])
                        all_results.append(r)

            # 2. Si hay resultados con búsqueda exacta, retornarlos
            if all_results:
                # Ordenar por relevancia y retornar top 5
                all_results.sort(key=lambda x: x['relevance'], reverse=True)
                return all_results[:5]


            # Intentar fuzzy con cada keyword
            for keyword in keywords:
                result = cls.get_product_quantity_fuzzy(keyword, warehouse_id)
                if result:
                    return result

            # 4. Último intento: fuzzy con el término original completo
            if len(keywords) > 1:
                search_combined = ' '.join(keywords)
                result = cls.get_product_quantity_fuzzy(search_combined, warehouse_id)
                if result:
                    return result

            return []

        except Exception as e:
            _logger.error(f"Error en get_product_quantity: {str(e)}")
            return []

    @classmethod
    def get_product_quantity_fuzzy(cls, search_term, warehouse_id):
        """Búsqueda de productos con tolerancia a errores tipográficos."""
        try:
            normalized = FuzzyProductSearch.normalize_text(search_term)

            if not normalized:
                return []


            # Dominio base: productos publicados (igual que build_search_domain)
            base_domain = [('is_published', '=', True)]

            # Estrategia 1: Buscar por nombre, categoría o categoría padre con coincidencia parcial
            candidates = request.env['product.template'].sudo().search(
                base_domain + [
                    '|', '|',
                    ('name', 'ilike', normalized),
                    ('categ_id.name', 'ilike', normalized),
                    ('categ_id.parent_id.name', 'ilike', normalized),
                ], limit=50
            )

            # Estrategia 2: Si no hay resultados, buscar por primeras letras en nombre y categorías
            if not candidates and len(normalized) >= 2:
                first_chars = normalized[:3] if len(normalized) >= 3 else normalized[:2]
                candidates = request.env['product.template'].sudo().search(
                    base_domain + [
                        '|', '|',
                        ('name', 'ilike', f'{first_chars}%'),
                        ('categ_id.name', 'ilike', f'{first_chars}%'),
                        ('categ_id.parent_id.name', 'ilike', f'{first_chars}%'),
                    ], limit=100
                )

            # Estrategia 3: Buscar por cada palabra del término
            if not candidates:
                words = normalized.split()
                for word in words:
                    if len(word) >= 2:
                        word_candidates = request.env['product.template'].sudo().search(
                            base_domain + [
                                '|', '|',
                                ('name', 'ilike', word),
                                ('categ_id.name', 'ilike', word),
                                ('categ_id.parent_id.name', 'ilike', word),
                            ], limit=50
                        )
                        candidates = candidates | word_candidates if candidates else word_candidates

            # Estrategia 4: Buscar por trigramas del nombre
            if not candidates and len(normalized) >= 3:
                trigrams = list(FuzzyProductSearch.get_trigrams(normalized))
                clean_trigrams = [tg.strip() for tg in trigrams if len(tg.strip()) >= 2][:8]
                for tg in clean_trigrams:
                    tg_candidates = request.env['product.template'].sudo().search(
                        base_domain + [('name', 'ilike', f'%{tg}%')], limit=30
                    )
                    candidates = candidates | tg_candidates if candidates else tg_candidates

            # Estrategia 5: Fallback - todos los productos publicados para fuzzy matching
            if not candidates:
                candidates = request.env['product.template'].sudo().search(
                    base_domain, limit=300
                )

            if not candidates:
                _logger.warning(f"No se encontraron candidatos para búsqueda fuzzy: '{search_term}'")
                return []


            # Aplicar búsqueda fuzzy con umbral tolerante
            fuzzy_results = FuzzyProductSearch.search_products_fuzzy(
                search_term, candidates, threshold=35
            )

            if not fuzzy_results:
                _logger.info(f"Fuzzy matching no encontró resultados sobre umbral para: '{search_term}'")
                return []


            # Filtrar por stock disponible en el almacén configurado
            warehouse = request.env['stock.warehouse'].sudo().browse(warehouse_id)
            if not warehouse.exists():
                _logger.error(f"Warehouse {warehouse_id} no existe")
                return []

            location_id = warehouse.lot_stock_id.id
            resultado = []

            for item in fuzzy_results[:20]:
                p = item['product']
                fuzzy_score = item['score']

                # Verificar variante
                variant = request.env['product.product'].sudo().search(
                    [('product_tmpl_id', '=', p.id)], limit=1
                )
                if not variant:
                    continue

                # Verificar stock en el almacén configurado
                quants = request.env['stock.quant'].sudo().read_group(
                    [
                        ('product_id', '=', variant.id),
                        ('location_id', 'child_of', location_id),
                    ],
                    ['inventory_quantity_auto_apply:sum', 'reserved_quantity:sum'],
                    []
                )

                qty_on_hand = quants and quants[0].get('inventory_quantity_auto_apply') or 0.0
                qty_reserved = quants and quants[0].get('reserved_quantity') or 0.0
                available_qty = qty_on_hand - qty_reserved

                if available_qty <= 0:
                    continue

                resultado.append({
                    "id": p.id,
                    "name": p.name,
                    "price": (
                        (p.list_price * p.uom_po_id.factor_inv if p.sale_uom_ecommerce else p.list_price)
                        * (1 + (sum(t.amount for t in p.taxes_id) / 100))
                        if p.taxes_id else
                        (p.list_price * p.uom_po_id.factor_inv if p.sale_uom_ecommerce else p.list_price)
                    ),
                    "stock": available_qty,
                    "uom_po_id": p.uom_po_id.name if p.uom_po_id else " ",
                    "category": p.categ_id.name or "Sin categoría",
                    "parent_category": (p.categ_id.parent_id.name
                                        if p.categ_id.parent_id
                                        else "Sin categoría padre"),
                    "relevance": fuzzy_score,
                    "fuzzy_match": True
                })

            return sorted(resultado, key=lambda x: x['relevance'], reverse=True)[:5]

        except Exception as e:
            _logger.error(f"Error en get_product_quantity_fuzzy: {str(e)}")
            return []

    @staticmethod
    def _row(prod):
        return {
            "id": prod.get("id") or prod.get("product_id"),
            "name": prod.get("name") or prod.get("product_name") or prod.get("display_name") or "Producto",
            "uom": prod.get("uom_po_id") or prod.get("uom_name") or "",
            "price": float(prod.get("price", prod.get("list_price", 0.0)) or 0.0),
            "qty": float(prod.get("available_qty", 0) or 0),
            "wh": prod.get("warehouse_name") or "",
            "code": prod.get("default_code") or "",
            "score": float(prod.get("score", 0) or 0),
        }

    @classmethod
    def process_product_search(cls, number, product_name):
        query = (product_name or "").strip()
        products = []
        if query:
            try:
                service = request.env['product.ai.search.service'].sudo()
                ai_results = service.search_products(query, top_k=5)
                if ai_results:
                    products = ai_results
            except Exception as e:
                _logger.warning("AI search failed; falling back. Reason: %s", e)

        if not products:
            warehouse_id = cls._get_default_warehouse_id()
            products = cls.get_product_quantity(query, warehouse_id)

        user_session = UserSession(request.env)
        if not products:
            user_session.update_session(number, state="manejar_decision_producto")
            ProductAsesorFlow.product_found(number)
            return {"status": "sent", "action": "buscar_producto"}

        safe_products = [cls._row(p) for p in products]

        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('searched_product') or ""
        for idx, r in enumerate(safe_products, start=1):
            mensaje += f"{idx}. {r['name']} ({r['uom']}) - Precio: {r['price']:.2f}\n"

        opcion_buscar_otro = len(safe_products) + 1
        opcion_salir = len(safe_products) + 2
        mensaje += f"{opcion_buscar_otro}. BUSCAR OTRO PRODUCTO\n"
        mensaje += f"{opcion_salir}. SALIR\n"
        mensaje += f"\nPor favor, ingresa el número de tu elección (1 a {opcion_salir})"

        session = user_session.get_session(number)
        try:
            orden_data = json.loads(session.orden or "{}")
        except Exception:
            orden_data = {}

        orden_data["temp_product_list"] = {"productos": safe_products}
        session.sudo().write({'orden': json.dumps(orden_data)})

        user_session.update_session(number, state="seleccionar_producto")
        MetaAPi.enviar_mensaje_texto(number, mensaje)
        return {"status": "sent", "action": "seleccionar_producto"}

    @classmethod
    def process_product_selection(cls, number, selection_text):
        user_session = UserSession(request.env)
        try:
            option = int(selection_text)
        except Exception:
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('invalid_number')
            MetaAPi.enviar_mensaje_texto(number, mensaje)
            user_session.update_session(number, state="seleccionar_producto")
            return

        user_session = UserSession(request.env)
        session = user_session.get_session(number)

        orden_data = {}
        if session.orden:
            try:
                orden_data = json.loads(session.orden)
            except:
                orden_data = {}

        try:
            option = int(selection_text)
        except:
            MetaAPi.enviar_mensaje_texto(number, "Por favor, ingresa un número válido.")
            user_session.update_session(number, state="seleccionar_producto")
        temp_products = orden_data.get("temp_product_list", {})
        products = temp_products.get("productos", [])
        num_products = len(products)

        opcion_buscar_otro = num_products + 1
        opcion_salir = num_products + 2

        if option == opcion_buscar_otro:
            BuyProductFlow.start_flow(number)
            return {"status": "sent", "action": "promociones"}
        elif option == opcion_salir:
            MetaAPi.enviar_mensaje_con_botones_salida(number)
            return {"status": "sent", "action": "salir"}

        index = option - 1
        if not products or index < 0 or index >= num_products:
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('invalid_product')
            MetaAPi.enviar_mensaje_texto(number, mensaje)
            return {"status": "error", "action": "seleccionar_producto"}

        temp_products = orden_data.get("temp_product_list", {})
        products = temp_products.get("productos", [])
        index = option - 1
        if index < 0 or index >= len(products):
            MetaAPi.enviar_mensaje_texto(number, "Número de producto inválido. Por favor, intenta nuevamente.")
            return {"status": "error", "action": "seleccionar_producto"}

        pid = products[index]['id']
        p_tmpl = request.env["product.template"].sudo().browse(pid)
        product = request.env['product.product'].sudo().search(
            [('product_tmpl_id', '=', p_tmpl.id)], limit=1)

        sale_order = None
        if orden_data.get("sale_order_id"):
            sale_order = request.env['sale.order'].sudo().browse(orden_data["sale_order_id"])
        if not sale_order:
            partner = request.env['res.partner'].sudo().search([
                ('vat', '=', '1101152001121'),
                ('name', '=', 'Chatbot Prueba')
            ], limit=1)

            if not partner:
                partner = request.env['res.partner'].sudo().create({
                    'name': 'Chatbot Prueba',
                    'vat': '1101152001121',
                    'email': '',
                    'street': '',
                    'phone': '0939098358',
                    'mobile': '0939098358',
                })

            vals = {
                'partner_id': partner.id,
                'state': 'draft',
                'website_id': 1,
                'is_order_chatbot': True,
                'x_numero_chatbot': number,
                'x_modo_compra': 'compra_auto',
                'x_channel': 'canal digital',
                'digital_media': 'chatbot'

            }
            sale_order = request.env['sale.order'].sudo().create(vals)
            orden_data["sale_order_id"] = sale_order.id

        existing = sale_order.order_line.filtered(
            lambda l: l.product_id.id == product.id and float(l.discount or 0) < 100.0)
        if existing:
            selected_line = existing[0]
        else:
            new_line_vals = {
                'product_id': product.id,
                'product_uom_qty': 0,
                'price_unit': product.lst_price,
                'product_uom': product.uom_id.id,
            }
            sale_order.write({'order_line': [(0, 0, new_line_vals)]})
            selected_line = sale_order.order_line.filtered(
                lambda l: l.product_id.id == product.id and l.product_uom_qty == 0
            )[:1]

        orden_data["selected_line_id"] = selected_line.id
        orden_data["selected_product"] = {
            'id': product.id,
            'name': product.name,
            'price': product.lst_price,
        }
        orden_data.pop("temp_product_list", None)
        session.sudo().write({'orden': json.dumps(orden_data)})
        mensaje = f"Has seleccionado: {product.name}. Por favor, ingresa la cantidad que deseas:"
        SaveOdoo.save_product_to_odoo(number, product.name)
        MetaAPi.enviar_mensaje_texto(number, mensaje)
        user_session.update_session(number, state="ingresar_cantidad")

        return {
            "status": "sent",
            "action": "ingresar_cantidad",
            "selected_product": orden_data["selected_product"],
        }

    @classmethod
    def process_quantity_input(cls, number, quantity_text):
        user_session = UserSession(request.env)
        session = user_session.get_session(number)
        data = json.loads(session.orden or "{}")

        sel = data.get("selected_product")
        if not sel:
            MetaAPi.enviar_mensaje_texto(number,
                                         "Ocurrió un problema al obtener el producto. Por favor, inicia nuevamente.")
            return {"status": "error", "action": "buscar_producto"}

        try:
            qty_new = float(quantity_text)
            if qty_new <= 0:
                raise ValueError()
        except Exception:
            msg = request.env['whatsapp_messages_user'].sudo().get_message('invalid_quantity')
            MetaAPi.enviar_mensaje_texto(number, msg)
            return {"status": "error", "action": "ingresar_cantidad"}

        wh = request.env['stock.warehouse'].sudo().browse(386)
        loc_id = wh.lot_stock_id.id
        quants = request.env['stock.quant'].sudo().read_group([
            ('product_id', '=', sel['id']),
            ('location_id', 'child_of', loc_id)
        ], ['inventory_quantity_auto_apply:sum', 'reserved_quantity:sum'], [])

        qty_on_hand = quants and quants[0].get('inventory_quantity_auto_apply') or 0.0
        qty_reserved = quants and quants[0].get('reserved_quantity') or 0.0
        available_qty = qty_on_hand - qty_reserved

        if qty_new > available_qty:
            MetaAPi.enviar_mensaje_texto(
                number,
                f"Lo sentimos, solo tenemos {int(available_qty)} unidades de {sel['name']}. Ingresa menos."
            )
            return {"status": "error", "action": "ingresar_cantidad"}

        so = request.env['sale.order'].with_context(channel='chatbot').sudo().browse(data.get("sale_order_id"))
        line = request.env['sale.order.line'].sudo().browse(data.get("selected_line_id"))
        if not so or not line:
            MetaAPi.enviar_mensaje_texto(number, "Ocurrió un problema con tu carrito. Por favor, inicia otra vez.")
            return {"status": "error", "action": "buscar_producto"}


        old_qty = line.product_uom_qty or 0.0
        total_qty = old_qty + qty_new
        line.write({'product_uom_qty': total_qty})

        reward_discount = request.env['loyalty.reward'].sudo().search([
            ('is_main_chat_bot', '=', True),
            ('reward_type', 'in', ['discount', 'loyalty_card']),
            ('discount_product_ids', 'in', [sel['id']]),
        ], limit=1)

        reward_free = request.env['loyalty.reward'].sudo().search([
            ('is_main_chat_bot', '=', True),
            ('reward_type', 'in', ['product', 'loyalty_card']),
            ('reward_product_id', '=', sel['id']),
        ], limit=1)

        program = reward_discount.program_id.sudo() if reward_discount else reward_free.program_id.sudo() if reward_free else None
        today = fields.Date.today()

        if program and (
                (program.date_from and today < program.date_from) or (program.date_to and today > program.date_to)):
            program = None

        rule_earned, points_earned = None, 0.0
        if program:
            for rule in program.rule_ids:
                if sel['id'] in rule._get_valid_products().ids:
                    points_earned = total_qty * (rule.reward_point_amount or 0)
                    if (reward_discount and points_earned >= (reward_discount.required_points or 0)) or \
                            (reward_free and points_earned >= (reward_free.required_points or 0)):
                        rule_earned = rule
                        break

        if reward_discount and rule_earned and points_earned >= (reward_discount.required_points or 0):
            line.write({'discount': reward_discount.discount or 0.0})

        free_product, free_qty = None, 0
        if reward_free and rule_earned and points_earned >= (reward_free.required_points or 0):
            blocks = int(points_earned // (reward_free.required_points or 1))
            free_qty = blocks * (reward_free.reward_product_qty or 0)
            free_product = reward_free.reward_product_id
            if free_qty and free_product:
                free_line = request.env['sale.order.line'].sudo().search([
                    ('order_id', '=', so.id),
                    ('product_id', '=', free_product.id),
                    ('discount', '=', 100.0),
                ], limit=1)
                if free_line:
                    free_line.product_uom_qty += free_qty
                else:
                    request.env['sale.order.line'].sudo().create({
                        'order_id': so.id,
                        'product_id': free_product.id,
                        'product_uom_qty': free_qty,
                        'price_unit': 0.0,
                        'discount': 100.0,
                        'name': f"{free_product.name} (gratis)",
                    })

        subtotal = sum(l.price_subtotal for l in so.order_line if (l.discount or 0.0) < 100.0)
        tax_total = sum(l.price_tax for l in so.order_line if (l.discount or 0.0) < 100.0)
        gross_total = sum(l.price_total for l in so.order_line if (l.discount or 0.0) < 100.0)

        discount_total = sum([
            ((l.price_unit * l.product_uom_qty) * (l.discount or 0.0) / 100)
            for l in so.order_line if (l.discount or 0.0) < 100.0
        ])

        tpl_name = line.product_template_id.name
        mensaje = (
            f"Tienes {int(total_qty)} × {tpl_name} en tu carrito.\n"
            f"Descuento: {discount_total:.2f}\n"
        )
        if free_product and free_qty:
            mensaje += f"Además recibes {free_qty} × {free_product.name} gratis.\n"
        mensaje += (
            f"Subtotal: {subtotal:.2f}\n"
            f"Total: ${gross_total:.2f} IVA incl."
        )

        MetaAPi.enviar_mensaje_texto(number, mensaje)
        user_session.update_session(number, state="menu_secundario")
        MetaAPi.enviar_mensaje_con_botones(number)
        InvoiceFlow.update_invoice_field(number, "total", round(float(gross_total), 2))

        return {"status": "ok", "action": "mostrar_promociones"}
