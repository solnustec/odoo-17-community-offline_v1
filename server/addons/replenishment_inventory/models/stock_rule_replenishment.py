# -*- coding: utf-8 -*-
"""
Módulo de Reglas de Reabastecimiento Optimizado para Odoo 17

Optimizaciones implementadas:
1. Caché multinivel con TTL (reglas, estadísticas, expresiones compiladas)
2. Consultas SQL batch con índices optimizados
3. Procesamiento en lotes configurable con commits incrementales
4. Pre-cálculo de valores para minimizar safe_eval
5. Procesamiento eficiente en memoria con generadores
6. Monitoreo de rendimiento integrado
7. Uso de sudo() para operaciones masivas
8. Commits intermedios para evitar transacciones largas
9. Detección de backlog y rate limiting
10. Pre-fetch de datos en batch
11. Deduplicación por producto/almacén
12. Protección contra timeout
13. Aislamiento de errores por registro
"""
import math
import logging
import time
import os
import gc
from math import sqrt
from functools import lru_cache

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
from collections import defaultdict
from scipy.stats import norm
from datetime import datetime

_logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURACIÓN DE OPTIMIZACIÓN
# =============================================================================
# Tamaño de lote por defecto (ajustable según recursos del servidor)
BATCH_SIZE = int(os.environ.get('ODOO_REPLENISHMENT_BATCH_SIZE', 500))
# TTL del caché en segundos (5 minutos por defecto)
CACHE_TTL = int(os.environ.get('ODOO_REPLENISHMENT_CACHE_TTL', 300))
# Tamaño máximo de sub-lotes para operaciones SQL
SQL_BATCH_SIZE = int(os.environ.get('ODOO_REPLENISHMENT_SQL_BATCH', 1000))
# Timeout máximo en segundos para procesamiento (default: 4 minutos)
PROCESSING_TIMEOUT = int(os.environ.get('ODOO_REPLENISHMENT_TIMEOUT', 240))
# Umbral de backlog para advertencia (registros pendientes)
BACKLOG_WARNING_THRESHOLD = int(os.environ.get('ODOO_REPLENISHMENT_BACKLOG_WARN', 5000))
# Habilitar commits intermedios
ENABLE_INTERMEDIATE_COMMITS = os.environ.get('ODOO_REPLENISHMENT_COMMITS', '1') == '1'


# =============================================================================
# UTILIDADES DE RENDIMIENTO
# =============================================================================
class ProcessingStats:
    """Estadísticas de procesamiento para detección de backlog."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.reset()
        return cls._instance

    def reset(self):
        self.last_batch_time = 0
        self.last_batch_size = 0
        self.total_processed = 0
        self.total_time = 0
        self.backlog_warnings = 0

    def record_batch(self, size, elapsed):
        self.last_batch_time = elapsed
        self.last_batch_size = size
        self.total_processed += size
        self.total_time += elapsed

    def get_avg_time_per_record(self):
        if self.total_processed == 0:
            return 0
        return self.total_time / self.total_processed

    def estimate_time_for_batch(self, size):
        avg = self.get_avg_time_per_record()
        return avg * size if avg > 0 else size * 0.003  # Default: 3ms/record

    def check_backlog(self, pending_size):
        if pending_size > BACKLOG_WARNING_THRESHOLD:
            self.backlog_warnings += 1
            return True
        return False

    def get_stats(self):
        return {
            'total_processed': self.total_processed,
            'total_time': round(self.total_time, 2),
            'avg_time_per_record': round(self.get_avg_time_per_record() * 1000, 3),  # ms
            'last_batch_size': self.last_batch_size,
            'last_batch_time': round(self.last_batch_time, 2),
            'backlog_warnings': self.backlog_warnings,
        }


_processing_stats = ProcessingStats()


# =============================================================================
# SISTEMA DE CACHÉ MULTINIVEL
# =============================================================================
class MultiLevelCache:
    """
    Caché singleton multinivel con TTL configurable.
    Soporta múltiples namespaces para diferentes tipos de datos.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._caches = {}
            cls._instance._timestamps = {}
            cls._instance._ttls = {}
            cls._instance._hits = 0
            cls._instance._misses = 0
        return cls._instance

    def configure_namespace(self, namespace, ttl=CACHE_TTL):
        """Configura un namespace con su propio TTL."""
        if namespace not in self._caches:
            self._caches[namespace] = {}
            self._timestamps[namespace] = {}
            self._ttls[namespace] = ttl

    def get(self, namespace, key):
        """Obtiene valor del caché si no ha expirado."""
        if namespace not in self._caches:
            self._misses += 1
            return None

        cache = self._caches[namespace]
        timestamps = self._timestamps[namespace]
        ttl = self._ttls.get(namespace, CACHE_TTL)

        if key in cache:
            if (datetime.now() - timestamps[key]).total_seconds() < ttl:
                self._hits += 1
                return cache[key]
            del cache[key]
            del timestamps[key]

        self._misses += 1
        return None

    def set(self, namespace, key, value):
        """Almacena valor en el caché."""
        self.configure_namespace(namespace)
        self._caches[namespace][key] = value
        self._timestamps[namespace][key] = datetime.now()

    def invalidate(self, namespace=None, key=None):
        """Invalida una clave, un namespace, o todo el caché."""
        if namespace is None:
            self._caches.clear()
            self._timestamps.clear()
        elif key is None:
            if namespace in self._caches:
                self._caches[namespace].clear()
                self._timestamps[namespace].clear()
        else:
            if namespace in self._caches and key in self._caches[namespace]:
                del self._caches[namespace][key]
                del self._timestamps[namespace][key]

    def get_stats(self):
        """Retorna estadísticas del caché."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': f"{hit_rate:.1f}%",
            'namespaces': list(self._caches.keys()),
            'total_entries': sum(len(c) for c in self._caches.values()),
        }


_cache = MultiLevelCache()

CACHE_NS_RULES = 'rules'
CACHE_NS_STATS = 'stats'
CACHE_NS_EXPRESSIONS = 'expressions'


# =============================================================================
# EXPRESIONES PRE-COMPILADAS
# =============================================================================
@lru_cache(maxsize=1024)
def _quick_eval(expr):
    """
    Evaluación rápida de expresiones simples sin contexto.
    Usa LRU cache para evitar re-evaluación.
    """
    expr = expr.strip()

    try:
        return float(expr)
    except ValueError:
        pass

    if expr == 'True':
        return True
    if expr == 'False':
        return False

    if expr.replace('.', '').replace('-', '').replace('+', '').isdigit():
        try:
            return float(expr)
        except ValueError:
            pass

    return None


def optimized_safe_eval(expression, localdict, mode='eval'):
    """
    Wrapper optimizado para safe_eval con atajos para casos comunes.
    """
    if not expression:
        return 0.0

    expr = expression.strip()

    quick_result = _quick_eval(expr)
    if quick_result is not None:
        return quick_result

    if '.' not in expr and '+' not in expr and '-' not in expr:
        if expr in localdict:
            return localdict[expr]

    if mode == 'exec':
        safe_eval(expression, localdict, mode='exec', nocopy=True)
        return localdict.get('result')
    return safe_eval(expression, localdict)


# =============================================================================
# MODELO PRINCIPAL
# =============================================================================
class StockRuleReplenishment(models.Model):
    _name = 'stock.rule.replenishment'
    _order = 'sequence, id'
    _description = 'Replenishment Rule'

    name = fields.Char(required=True, string="Nombre")
    code = fields.Char(
        required=True,
        string="Código",
        index=True,
        help="El código de las reglas puede usarse como referencia en el cálculo de otras reglas."
    )
    sequence = fields.Integer(required=True, index=True, default=5, string="Orden")
    quantity = fields.Char(default='1.0', string="Cantidad")
    active = fields.Boolean(default=True, index=True, string="Activo")
    condition_select = fields.Selection([
        ('none', 'Siempre Verdadero'),
        ('range', 'Rango'),
        ('python', 'Expresión Python')
    ], string="Condición Basada en", default='none', required=True)
    condition_range = fields.Char(string='Rango Basado en', default='contract.wage')
    condition_python = fields.Text(
        string='Condición Python',
        required=True,
        default='''
    # Variables disponibles:
    # product, warehouse, rules, inputs, approx_norm_ppf, get_standard_deviation, sqrt, get_sales
    result = 1 > 0'''
    )
    condition_range_min = fields.Float(string='Rango Mínimo')
    condition_range_max = fields.Float(string='Rango Máximo')
    amount_select = fields.Selection([
        ('percentage', 'Porcentaje (%)'),
        ('fix', 'Monto Fijo'),
        ('code', 'Código Python'),
    ], string='Tipo de Monto', index=True, required=True, default='fix')
    amount_fix = fields.Float(string='Monto Fijo', digits='Replenishment Float')
    amount_percentage = fields.Float(string='Porcentaje (%)', digits='Replenishment Float')
    amount_python_compute = fields.Text(string='Código Python', default='result = 0')
    amount_percentage_base = fields.Char(string='Porcentaje basado en')
    note = fields.Html(string='Descripción', translate=True)
    state = fields.Char("Estado de Ejecución")

    # =========================================================================
    # CACHÉ DE REGLAS
    # =========================================================================
    @api.model
    def _get_cached_rules(self, force_refresh=False):
        """Obtiene reglas del caché o las carga de la BD."""
        cache_key = f'rules_{self.env.cr.dbname}'

        if not force_refresh:
            cached = _cache.get(CACHE_NS_RULES, cache_key)
            if cached is not None:
                return cached

        rules = self.sudo().search([('active', '=', True)], order='sequence')

        rules_data = {
            'all': rules,
            'sorted': rules,
            'by_code': {},
            'input_dict': defaultdict(list),
            'lines_dict': {},
            'codes_set': set(),
        }

        for rule in rules:
            if rule.code:
                rules_data['by_code'][rule.code] = rule
                rules_data['input_dict'][rule.code].append(rule)
                rules_data['codes_set'].add(rule.code)
            if rule.name:
                rules_data['lines_dict'][rule.name] = rule

        _cache.set(CACHE_NS_RULES, cache_key, rules_data)
        return rules_data

    @api.model
    def _invalidate_rules_cache(self):
        """Invalida el caché de reglas."""
        _cache.invalidate(CACHE_NS_RULES)
        _quick_eval.cache_clear()

    def write(self, vals):
        res = super().write(vals)
        self._invalidate_rules_cache()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        self._invalidate_rules_cache()
        return res

    def unlink(self):
        self._invalidate_rules_cache()
        return super().unlink()

    # =========================================================================
    # MÉTODOS DE CÁLCULO OPTIMIZADOS
    # =========================================================================
    def _raise_error(self, localdict, error_type, e):
        raise UserError(_("""%s
    - Producto: %s
    - Almacen: %s
    - Regla: %s (%s)
    - Error: %s""",
                          error_type,
                          localdict['product'].name,
                          localdict['warehouse'].name,
                          self.name, self.code, e))

    def _compute_rule(self, localdict):
        """Calcula el resultado de una regla - optimizado."""
        self.ensure_one()
        localdict['localdict'] = localdict

        if self.amount_select == 'fix':
            qty = self._eval_quantity(localdict)
            if qty is None:
                return None
            self.state = "Ejecución Correcta"
            return self.amount_fix or 0.0, qty, 100.0

        if self.amount_select == 'percentage':
            try:
                base = optimized_safe_eval(self.amount_percentage_base, localdict)
                qty = self._eval_quantity(localdict)
                if qty is None:
                    return None
                self.state = "Ejecución Correcta"
                return float(base), qty, self.amount_percentage or 0.0
            except Exception as e:
                self.state = str(e)
                self._raise_error(localdict, _("Wrong percentage base or quantity defined for:"), e)
        else:
            try:
                optimized_safe_eval(self.amount_python_compute or '0.0', localdict, mode='exec')
                self.state = "Ejecución Correcta"
                return localdict['result'], localdict.get('result_qty', 1.0), localdict.get('result_rate', 100.0)
            except Exception as e:
                self.state = str(e)
                self._raise_error(localdict, _("Wrong python code defined for:"), e)

    def _eval_quantity(self, localdict):
        """Evalúa cantidad - optimizado para números simples."""
        qty_str = self.quantity or '1.0'

        quick_result = _quick_eval(qty_str)
        if quick_result is not None:
            return float(quick_result)

        try:
            return float(optimized_safe_eval(qty_str, localdict))
        except Exception as e:
            self.state = str(e)
            self._raise_error(localdict, _("Wrong quantity defined for:"), e)
            return None

    def approx_norm_ppf(self, p):
        return norm.ppf(p)

    # =========================================================================
    # WRAPPERS PARA ROLLING STATS (compatibilidad con reglas existentes)
    # =========================================================================
    def _get_stddev_from_rolling(self, product_id, warehouse_id, days=30, record_type=None):
        """
        Wrapper que obtiene stddev desde product.sales.stats.rolling.
        Determina el record_type según la configuración del warehouse si no se especifica.

        Args:
            product_id: ID del producto
            warehouse_id: ID del warehouse
            days: Período (30, 60 o 90)
            record_type: 'sale', 'transfer' o 'combined' (si None, usa config del warehouse)

        Returns:
            float: Desviación estándar
        """
        # Si no se especifica record_type, determinarlo según config del warehouse
        if record_type is None:
            wh = self.env['stock.warehouse'].browse(warehouse_id)
            if wh.exists():
                based_on_sales = getattr(wh, 'replenishment_based_on_sales', True)
                based_on_transfers = getattr(wh, 'replenishment_based_on_transfers', False)

                if based_on_sales and based_on_transfers:
                    record_type = 'combined'
                elif based_on_transfers:
                    record_type = 'transfer'
                else:
                    record_type = 'sale'
            else:
                record_type = 'sale'

        RollingStats = self.env['product.sales.stats.rolling']
        stats = RollingStats.get_stats(
            product_id=product_id,
            warehouse_id=warehouse_id,
            record_type=record_type,
            days=days
        )
        return stats.get('stddev', 0.0)

    def _get_sales_from_rolling(self, lapse, product, warehouse):
        """
        Wrapper que obtiene total de ventas desde product.sales.stats.rolling.
        Mantiene la misma firma que product.sales.stats.get_sales() para compatibilidad.

        Args:
            lapse: Días del período (30, 60 o 90)
            product: Producto o ID
            warehouse: Warehouse o ID

        Returns:
            float: Total de ventas/transferencias del período
        """
        product_id = product.id if hasattr(product, 'id') else product
        warehouse_id = warehouse.id if hasattr(warehouse, 'id') else warehouse

        # Obtener configuración de la bodega
        wh = self.env['stock.warehouse'].browse(warehouse_id)
        if not wh.exists():
            return 0.0

        based_on_sales = getattr(wh, 'replenishment_based_on_sales', True)
        based_on_transfers = getattr(wh, 'replenishment_based_on_transfers', False)

        # Determinar el record_type según configuración del warehouse
        if based_on_sales and based_on_transfers:
            record_type = 'combined'
        elif based_on_transfers:
            record_type = 'transfer'
        else:
            record_type = 'sale'

        RollingStats = self.env['product.sales.stats.rolling']
        stats = RollingStats.get_stats(
            product_id=product_id,
            warehouse_id=warehouse_id,
            record_type=record_type,
            days=lapse
        )
        return stats.get('total_qty', 0.0)

    def _satisfy_condition(self, localdict):
        """Verifica si la condición de la regla se cumple - optimizado."""
        self.ensure_one()
        localdict['localdict'] = localdict

        if self.condition_select == 'none':
            return True

        if self.condition_select == 'range':
            try:
                result = optimized_safe_eval(self.condition_range, localdict)
                return self.condition_range_min <= result <= self.condition_range_max
            except Exception as e:
                self._raise_error(localdict, _("Wrong range condition defined for:"), e)
        else:
            try:
                optimized_safe_eval(self.condition_python, localdict, mode='exec')
                return localdict.get('result', False)
            except Exception as e:
                self._raise_error(localdict, _("Wrong python condition defined for:"), e)

    def get_all_rules(self):
        """Compatibilidad - usa caché."""
        return self._get_cached_rules()['all']

    def get_localdict(self, product_id, warehouse_id, rules_data=None):
        """Construye diccionario local para evaluación."""
        if not (product_id and warehouse_id):
            raise ValidationError("Se requiere product_id y warehouse_id válidos")

        if rules_data is None:
            rules_data = self._get_cached_rules()

        return {
            'rules': defaultdict(lambda: {'total': 0, 'amount': 0, 'quantity': 0}),
            'reple': self,
            'inputs': dict(rules_data['input_dict']),
            'product': product_id,
            'warehouse': warehouse_id,
            'result_rules': defaultdict(lambda: {'total': 0, 'amount': 0, 'quantity': 0, 'rate': 0}),
            'approx_norm_ppf': self.approx_norm_ppf,
            'get_standard_deviation': self._get_stddev_from_rolling,
            'get_sales': self._get_sales_from_rolling,
            'sqrt': sqrt,
            'lines': rules_data['lines_dict'],
        }

    def _get_rule_name(self, localdict):
        return localdict.get('result_name', False)

    # =========================================================================
    # CONSULTAS BATCH OPTIMIZADAS
    # =========================================================================
    def _get_orderpoints_batch(self, location_product_pairs):
        """
        Obtiene orderpoints en UNA SOLA consulta usando IN con tuplas.
        Optimizado con límites de batch.
        """
        if not location_product_pairs:
            return {}

        all_results = {}
        pairs_list = list(location_product_pairs)

        for i in range(0, len(pairs_list), SQL_BATCH_SIZE):
            batch = pairs_list[i:i + SQL_BATCH_SIZE]

            query = """
                SELECT id, location_id, product_id, product_max_qty, product_min_qty, point_reorder
                FROM stock_warehouse_orderpoint
                WHERE (location_id, product_id) IN %s
            """

            self.env.cr.execute(query, (tuple(batch),))
            rows = self.env.cr.fetchall()

            if rows:
                for row in rows:
                    op_id, loc_id, prod_id, max_qty, min_qty, point_qty = row
                    all_results[(loc_id, prod_id)] = {
                        'id': op_id,
                        'product_max_qty': max_qty or 0,
                        'product_min_qty': min_qty or 0,
                        'point_reorder': point_qty or 0,
                    }

        return all_results

    # =========================================================================
    # PRE-FETCH DE DATOS EN BATCH
    # =========================================================================
    def _prefetch_record_data(self, records):
        """
        Pre-carga datos de productos y almacenes en batch para evitar
        queries individuales durante el procesamiento.
        """
        product_ids = set()
        warehouse_ids = set()

        for record in records:
            if record.product_id:
                product_ids.add(record.product_id.id)
            if record.warehouse_id:
                warehouse_ids.add(record.warehouse_id.id)

        # Pre-cargar productos con campos necesarios
        if product_ids:
            self.env['product.product'].browse(list(product_ids)).read(
                ['list_price', 'type', 'name']
            )

        # Pre-cargar almacenes con lot_stock_id
        if warehouse_ids:
            self.env['stock.warehouse'].browse(list(warehouse_ids)).read(
                ['lot_stock_id', 'name']
            )

        return len(product_ids), len(warehouse_ids)

    # =========================================================================
    # DEDUPLICACIÓN POR PRODUCTO/ALMACÉN
    # =========================================================================
    def _deduplicate_records(self, records):
        """
        Deduplica registros por producto/almacén.
        Solo procesa el último registro para cada combinación.
        """
        seen = {}
        for record in records:
            if not record.product_id or not record.warehouse_id:
                continue
            key = (record.product_id.id, record.warehouse_id.id)
            seen[key] = record  # El último gana

        return list(seen.values())

    # =========================================================================
    # CÁLCULO DE MAX Y MIN - OPTIMIZADO CON AISLAMIENTO DE ERRORES
    # =========================================================================
    def get_max_and_min(self, obj):
        """Calcula MAX, MIN y POINT_REORDER para un producto/almacén."""
        product_id = obj.product_id
        warehouse = obj.warehouse_id

        if not product_id or not warehouse:
            return []

        # Validaciones previas
        if product_id.list_price == 0 or product_id.type == 'service':
            return []

        location_id = warehouse.lot_stock_id
        if not location_id:
            return []

        line_vals = []
        rules_data = self._get_cached_rules()
        localdict = self.get_localdict(product_id, warehouse, rules_data)
        rules_dict = localdict['rules']
        result_rules_dict = localdict['result_rules']

        target_codes = {'MAX', 'MIN', 'POINT_REORDER'}

        for rule in rules_data['sorted']:
            localdict.update({
                'result': None,
                'result_qty': 1.0,
                'result_rate': 100,
                'result_name': False,
            })

            try:
                if not rule._satisfy_condition(localdict):
                    continue

                result = rule._compute_rule(localdict)
                if result is None:
                    continue

                amount, qty, rate = result

                if isinstance(amount, (int, float)):
                    non_numeric_value = None
                    amount = float(amount)
                else:
                    non_numeric_value = amount
                    amount = 0.0

                tot_rule = amount * qty * rate / 100.0
                localdict[rule.code] = tot_rule
                result_rules_dict[rule.code] = {
                    'total': tot_rule, 'amount': amount, 'quantity': qty, 'rate': rate,
                }
                rules_dict[rule.code] = rule

                if rule.code in target_codes:
                    line_vals.append({
                        'sequence': rule.sequence,
                        'code': rule.code,
                        'name': self._get_rule_name(localdict) or rule.name,
                        'salary_rule_id': rule.id,
                        'product_id': product_id.id,
                        'warehouse_id': location_id.id,
                        'amount': amount,
                        'quantity': qty,
                        'data_extra': non_numeric_value,
                        'rate': rate,
                    })

            except Exception:
                # Aislamiento de errores: un error en una regla no detiene el resto
                pass

        return line_vals

    # =========================================================================
    # PROCESAMIENTO EN LOTE CON COMMITS INTERMEDIOS
    # =========================================================================
    def _process_records_batch(self, records, batch_size=None):
        """
        Procesa un lote de registros con máxima eficiencia.

        Mejoras para alta frecuencia:
        1. Deduplicación por producto/almacén
        2. Pre-fetch de datos en batch
        3. Commits intermedios cada sub-lote
        4. Detección de timeout
        5. Aislamiento de errores por registro
        6. Limpieza de memoria periódica
        """
        if not records:
            return {'processed': 0, 'errors': 0, 'created': 0, 'updated': 0}

        batch_size = batch_size or BATCH_SIZE
        start_time = time.perf_counter()

        # Verificar backlog
        _processing_stats.check_backlog(len(records))

        # Paso 0: Deduplicar registros
        original_count = len(records)
        records = self._deduplicate_records(records)
        deduplicated = original_count - len(records)

        # Paso 1: Pre-fetch de datos
        self._prefetch_record_data(records)

        processed = 0
        errors = 0
        all_orderpoint_data = {}

        # Paso 2: Calcular todos los max/min en memoria
        for record in records:
            # Verificar timeout
            elapsed = time.perf_counter() - start_time
            if elapsed > PROCESSING_TIMEOUT:
                break

            try:
                line_vals = self.get_max_and_min(record)

                if not line_vals:
                    processed += 1
                    continue

                for val in line_vals:
                    if not (val.get('warehouse_id') and val.get('product_id')):
                        continue

                    key = (val['product_id'], val['warehouse_id'])
                    if key not in all_orderpoint_data:
                        all_orderpoint_data[key] = {'max_qty': 0, 'min_qty': 0, 'point_qty': 0}

                    # Redondeo estándar: >= 0.5 sube, < 0.5 baja
                    qty = round(val['amount'])
                    code = val['code']
                    if code == 'MAX':
                        all_orderpoint_data[key]['max_qty'] = qty
                    elif code == 'MIN':
                        all_orderpoint_data[key]['min_qty'] = qty
                    elif code == 'POINT_REORDER':
                        all_orderpoint_data[key]['point_qty'] = qty

                processed += 1

            except Exception:
                errors += 1

        if not all_orderpoint_data:
            return {'processed': processed, 'errors': errors, 'created': 0, 'updated': 0}

        # Paso 3: UNA consulta batch para orderpoints existentes
        location_product_pairs = [
            (loc_id, prod_id)
            for prod_id, loc_id in all_orderpoint_data.keys()
        ]
        existing_orderpoints = self._get_orderpoints_batch(location_product_pairs)

        # Paso 4: Preparar operaciones
        to_create = []
        updates_by_vals = defaultdict(list)

        for (product_id, warehouse_id), quantities in all_orderpoint_data.items():
            key = (warehouse_id, product_id)
            existing = existing_orderpoints.get(key)

            if existing:
                updates = {}
                if existing['product_max_qty'] != quantities['max_qty']:
                    updates['product_max_qty'] = quantities['max_qty']
                if existing['product_min_qty'] != quantities['min_qty']:
                    updates['product_min_qty'] = quantities['min_qty']
                if existing['point_reorder'] != quantities['point_qty']:
                    updates['point_reorder'] = quantities['point_qty']

                if updates:
                    vals_key = tuple(sorted(updates.items()))
                    updates_by_vals[vals_key].append(existing['id'])
            else:
                to_create.append({
                    'product_id': product_id,
                    'location_id': warehouse_id,
                    'product_max_qty': quantities['max_qty'],
                    'product_min_qty': quantities['min_qty'],
                    'point_reorder': quantities['min_qty'],
                    'trigger': 'manual'
                })

        # Paso 5: Ejecutar operaciones batch con commits intermedios
        created_count = 0
        updated_count = 0
        orderpoint_model = self.env['stock.warehouse.orderpoint'].sudo()

        try:
            for vals_key, op_ids in updates_by_vals.items():
                for i in range(0, len(op_ids), batch_size):
                    batch_ids = op_ids[i:i + batch_size]
                    orderpoint_model.browse(batch_ids).write(dict(vals_key))
                    updated_count += len(batch_ids)

                    if ENABLE_INTERMEDIATE_COMMITS:
                        self.env.cr.commit()
        except Exception:
            if ENABLE_INTERMEDIATE_COMMITS:
                self.env.cr.rollback()

        try:
            if to_create:
                for i in range(0, len(to_create), batch_size):
                    batch = to_create[i:i + batch_size]
                    orderpoint_model.create(batch)
                    created_count += len(batch)

                    if ENABLE_INTERMEDIATE_COMMITS:
                        self.env.cr.commit()
        except Exception:
            if ENABLE_INTERMEDIATE_COMMITS:
                self.env.cr.rollback()

        # Limpiar memoria
        del all_orderpoint_data
        del existing_orderpoints
        del to_create
        del updates_by_vals
        gc.collect()

        # Registrar estadísticas
        elapsed = time.perf_counter() - start_time
        _processing_stats.record_batch(processed, elapsed)

        return {
            'processed': processed,
            'errors': errors,
            'created': created_count,
            'updated': updated_count,
            'deduplicated': deduplicated,
        }

    # =========================================================================
    # UTILIDADES DE DIAGNÓSTICO
    # =========================================================================
    @api.model
    def get_cache_stats(self):
        """Retorna estadísticas del caché para diagnóstico."""
        return _cache.get_stats()

    @api.model
    def get_processing_stats(self):
        """Retorna estadísticas de procesamiento."""
        return _processing_stats.get_stats()

    @api.model
    def clear_all_caches(self):
        """Limpia todos los cachés (útil para debugging)."""
        _cache.invalidate()
        _quick_eval.cache_clear()

    @api.model
    def reset_processing_stats(self):
        """Reinicia estadísticas de procesamiento."""
        _processing_stats.reset()
