# -*- coding: utf-8 -*-
"""
Procesador de Cola de Reabastecimiento - Arquitectura de 4 Capas

Este módulo implementa el consumidor de la cola que:
1. Consume eventos con DELETE...RETURNING (sin locks)
2. Actualiza daily stats con UPSERT
3. Recalcula rolling stats para los productos afectados
4. Calcula MAX/MIN usando las reglas de reabastecimiento
5. Actualiza/crea orderpoints
6. Maneja errores enviando a dead letter queue
"""

import math
import time
import uuid
import logging
import traceback
from odoo import models, api

_logger = logging.getLogger(__name__)

# Configuración
MAX_RETRIES = 3
BATCH_SIZE_DEFAULT = 1000
TIME_LIMIT_DEFAULT = 55  # segundos


class QueueProcessor(models.AbstractModel):
    """
    Procesador abstracto de la cola de reabastecimiento.

    Este modelo proporciona la lógica de procesamiento que es llamada
    por el cron job. Implementa:
    - Consumo atómico con DELETE...RETURNING
    - Agregación y UPSERT de daily stats
    - Actualización de rolling stats
    - Manejo de errores con dead letter queue
    """
    _name = 'replenishment.queue.processor'
    _description = 'Procesador de Cola de Reabastecimiento'

    @api.model
    def process_queue(self, batch_size=BATCH_SIZE_DEFAULT,
                      time_limit=TIME_LIMIT_DEFAULT):
        """
        Procesa la cola de reabastecimiento.

        Este es el método principal llamado por el cron job.

        Args:
            batch_size: Número máximo de registros por batch
            time_limit: Tiempo máximo de ejecución en segundos

        Returns:
            dict: Estadísticas de procesamiento
        """
        start_time = time.time()
        batch_id = str(uuid.uuid4())[:8]

        stats = {
            'batch_id': batch_id,
            'batches_processed': 0,
            'events_processed': 0,
            'events_failed': 0,
            'daily_stats_updated': 0,
            'rolling_stats_updated': 0,
            'orderpoints_updated': 0,
            'orderpoints_created': 0,
            'time_elapsed': 0,
        }

        _logger.info(
            "Iniciando procesamiento de cola [batch_id=%s, batch_size=%s, time_limit=%ss]",
            batch_id, batch_size, time_limit
        )

        Queue = self.env['product.replenishment.queue']

        while True:
            # Verificar tiempo límite
            elapsed = time.time() - start_time
            if elapsed >= time_limit:
                _logger.info(
                    "Tiempo límite alcanzado (%ss), deteniendo procesamiento",
                    time_limit
                )
                break

            # Consumir batch de la cola
            events = Queue.consume_batch(batch_size=batch_size)

            if not events:
                _logger.info("Cola vacía, procesamiento completado")
                break

            stats['batches_processed'] += 1

            # Procesar el batch
            try:
                batch_stats = self._process_batch(events, batch_id)
                stats['events_processed'] += batch_stats['processed']
                stats['events_failed'] += batch_stats['failed']
                stats['daily_stats_updated'] += batch_stats['daily_updated']
                stats['rolling_stats_updated'] += batch_stats['rolling_updated']
                stats['orderpoints_updated'] += batch_stats.get('orderpoints_updated', 0)
                stats['orderpoints_created'] += batch_stats.get('orderpoints_created', 0)

            except Exception as e:
                _logger.error(
                    "Error procesando batch [batch_id=%s]: %s",
                    batch_id, e
                )
                # Enviar todos los eventos del batch a dead letter
                self._send_batch_to_dead_letter(
                    events,
                    error_message=str(e),
                    error_traceback=traceback.format_exc(),
                    error_type='database_error'
                )
                stats['events_failed'] += len(events)

            # Commit después de cada batch para liberar memoria
            self.env.cr.commit()

        stats['time_elapsed'] = time.time() - start_time

        _logger.info(
            "Procesamiento completado [batch_id=%s]: "
            "%s batches, %s eventos, %s orderpoints (%s new), %.2fs",
            batch_id,
            stats['batches_processed'],
            stats['events_processed'],
            stats['orderpoints_updated'],
            stats['orderpoints_created'],
            stats['time_elapsed']
        )

        return stats

    def _process_batch(self, events, batch_id):
        """
        Procesa un batch de eventos.

        Args:
            events: Lista de diccionarios con los eventos
            batch_id: Identificador del batch

        Returns:
            dict: Estadísticas del batch
        """
        stats = {
            'processed': 0,
            'failed': 0,
            'daily_updated': 0,
            'rolling_updated': 0,
        }

        if not events:
            return stats

        DailyStats = self.env['product.sales.stats.daily']
        RollingStats = self.env['product.sales.stats.rolling']
        EventLog = self.env['product.sale.event.log']
        DeadLetter = self.env['product.replenishment.dead.letter']

        # Separar eventos válidos de inválidos
        valid_events = []
        invalid_events = []

        for event in events:
            # Verificar que el producto y warehouse existen
            if not event.get('product_id') or not event.get('warehouse_id'):
                invalid_events.append((event, 'Producto o warehouse inválido'))
                continue

            product = self.env['product.product'].browse(event['product_id']).exists()
            warehouse = self.env['stock.warehouse'].browse(event['warehouse_id']).exists()

            if not product:
                invalid_events.append((event, 'Producto no existe'))
                continue

            if not warehouse:
                invalid_events.append((event, 'Warehouse no existe'))
                continue

            valid_events.append(event)

        # Enviar inválidos a dead letter
        for event, error_msg in invalid_events:
            error_type = 'product_deleted' if 'Producto' in error_msg else 'warehouse_inactive'
            DeadLetter.send_to_dead_letter(
                event,
                error_message=error_msg,
                error_type=error_type
            )
            stats['failed'] += 1

        if not valid_events:
            return stats

        # 1. UPSERT daily stats
        daily_updated = DailyStats.upsert_daily_stats(valid_events)
        stats['daily_updated'] = daily_updated

        # 2. Obtener pares únicos producto/warehouse para actualizar rolling stats
        product_warehouse_pairs = set()
        for event in valid_events:
            product_warehouse_pairs.add((
                event['product_id'],
                event['warehouse_id']
            ))

        # 3. Actualizar rolling stats
        rolling_updated = RollingStats.update_rolling_stats(
            list(product_warehouse_pairs),
            source='queue'
        )
        stats['rolling_updated'] = rolling_updated

        # 4. Calcular MAX/MIN y actualizar orderpoints
        orderpoints_result = self._update_orderpoints_batch(
            list(product_warehouse_pairs)
        )
        stats['orderpoints_updated'] = orderpoints_result.get('updated', 0)
        stats['orderpoints_created'] = orderpoints_result.get('created', 0)

        # 5. Registrar en event log
        try:
            log_events = []
            for event in valid_events:
                log_events.append({
                    'product_id': event['product_id'],
                    'warehouse_id': event['warehouse_id'],
                    'quantity': event.get('quantity', 0),
                    'event_date': event.get('event_date'),
                    'record_type': event.get('record_type', 'sale'),
                    'is_legacy_system': event.get('is_legacy_system', False),
                    'source_model': 'product.warehouse.sale.summary',
                    'source_id': event.get('source_id'),
                    'queue_id': event.get('id'),
                })
            EventLog.log_events(log_events, batch_id=batch_id)
        except Exception as e:
            # El event log es opcional, no fallar si hay error
            _logger.warning("Error registrando eventos en log: %s", e)

        stats['processed'] = len(valid_events)

        return stats

    def _send_batch_to_dead_letter(self, events, error_message, error_traceback=None,
                                   error_type='unknown'):
        """
        Envía un batch completo de eventos a dead letter.
        """
        DeadLetter = self.env['product.replenishment.dead.letter']

        for event in events:
            try:
                DeadLetter.send_to_dead_letter(
                    event,
                    error_message=error_message,
                    error_traceback=error_traceback,
                    error_type=error_type
                )
            except Exception as e:
                _logger.error(
                    "Error enviando evento a dead letter: %s",
                    e
                )

    def _update_orderpoints_batch(self, product_warehouse_pairs):
        """
        Calcula MAX/MIN y actualiza orderpoints para los pares producto/almacén.

        Usa las reglas de stock.rule.replenishment y las rolling_stats
        precalculadas para obtener consultas O(1).

        Args:
            product_warehouse_pairs: Lista de tuplas (product_id, warehouse_id)

        Returns:
            dict: {updated: int, created: int, errors: int}
        """
        if not product_warehouse_pairs:
            return {'updated': 0, 'created': 0, 'errors': 0}

        result = {'updated': 0, 'created': 0, 'errors': 0}

        try:
            ReplenishmentRule = self.env['stock.rule.replenishment']
            Orderpoint = self.env['stock.warehouse.orderpoint']

            # Obtener reglas cacheadas
            rules_data = ReplenishmentRule._get_cached_rules()

            if not rules_data.get('sorted'):
                _logger.warning("No hay reglas de reabastecimiento configuradas")
                return result

            _logger.info(
                "Procesando %s pares con %s reglas cargadas",
                len(product_warehouse_pairs),
                len(rules_data.get('sorted', []))
            )

            # Pre-fetch productos y warehouses
            product_ids = list(set(p[0] for p in product_warehouse_pairs))
            warehouse_ids = list(set(p[1] for p in product_warehouse_pairs))

            products = {p.id: p for p in self.env['product.product'].browse(product_ids).exists()}
            warehouses = {w.id: w for w in self.env['stock.warehouse'].browse(warehouse_ids).exists()}

            # Obtener orderpoints existentes en batch
            location_product_pairs = set()
            for product_id, warehouse_id in product_warehouse_pairs:
                warehouse = warehouses.get(warehouse_id)
                if warehouse and warehouse.lot_stock_id:
                    location_product_pairs.add((warehouse.lot_stock_id.id, product_id))

            existing_orderpoints = ReplenishmentRule._get_orderpoints_batch(location_product_pairs)

            # Procesar cada par
            to_update = {}  # {orderpoint_id: vals}
            to_create = []

            for product_id, warehouse_id in product_warehouse_pairs:
                product = products.get(product_id)
                warehouse = warehouses.get(warehouse_id)

                if not product or not warehouse:
                    continue

                # Saltar productos sin precio o servicios
                if product.list_price == 0 or product.type == 'service':
                    continue

                location_id = warehouse.lot_stock_id
                if not location_id:
                    continue

                try:
                    # Calcular MAX/MIN usando reglas
                    localdict = ReplenishmentRule.get_localdict(product, warehouse, rules_data)
                    rules_dict = localdict['rules']
                    result_rules_dict = localdict['result_rules']

                    target_codes = {'MAX', 'MIN', 'POINT_REORDER'}
                    calculated_values = {}

                    # IMPORTANTE: Procesar TODAS las reglas en orden, no solo las target
                    # Las reglas MAX/MIN/POINT_REORDER dependen de reglas previas
                    for rule in rules_data['sorted']:
                        localdict.update({
                            'result': None,
                            'result_qty': 1.0,
                            'result_rate': 100,
                            'result_name': False,
                        })

                        try:
                            # Usar los métodos del registro de regla directamente
                            if not rule._satisfy_condition(localdict):
                                continue

                            rule_result = rule._compute_rule(localdict)
                            if rule_result is None:
                                continue

                            amount, qty, rate = rule_result

                            # Convertir a float si es numérico
                            if isinstance(amount, (int, float)):
                                amount = float(amount)
                            else:
                                amount = 0.0

                            tot_rule = amount * qty * rate / 100.0

                            # Guardar en rules_dict, result_rules_dict y localdict
                            rules_dict[rule.code]['amount'] = tot_rule
                            rules_dict[rule.code]['total'] = tot_rule
                            result_rules_dict[rule.code] = {
                                'total': tot_rule,
                                'amount': amount,
                                'quantity': qty,
                                'rate': rate,
                            }
                            localdict[rule.code] = tot_rule

                            # Solo guardar en calculated_values si es una regla target
                            if rule.code in target_codes:
                                calculated_values[rule.code] = tot_rule

                        except Exception:
                            continue

                    if not calculated_values:
                        continue

                    # Preparar valores para orderpoint (redondeo hacia arriba para productos)
                    max_qty = math.ceil(calculated_values.get('MAX', 0))
                    min_qty = math.ceil(calculated_values.get('MIN', 0))
                    point_reorder = math.ceil(calculated_values.get('POINT_REORDER', min_qty))

                    # Buscar orderpoint existente
                    key = (location_id.id, product_id)
                    existing = existing_orderpoints.get(key)

                    if existing:
                        # Actualizar si cambió (existing es un dict de _get_orderpoints_batch)
                        op_id = existing['id']
                        old_max = existing['product_max_qty']
                        old_min = existing['product_min_qty']
                        old_point = existing['point_reorder']
                        if (old_max != max_qty or old_min != min_qty or
                                old_point != point_reorder):
                            if op_id not in to_update:
                                to_update[op_id] = {}
                            to_update[op_id].update({
                                'product_max_qty': max_qty,
                                'product_min_qty': min_qty,
                                'point_reorder': point_reorder,
                            })
                    else:
                        # Crear nuevo
                        to_create.append({
                            'product_id': product_id,
                            'warehouse_id': warehouse_id,
                            'location_id': location_id.id,
                            'product_max_qty': max_qty,
                            'product_min_qty': min_qty,
                            'point_reorder': point_reorder,
                        })

                except Exception as e:
                    # Log solo los primeros errores para no llenar el log
                    if result['errors'] < 5:
                        _logger.warning(
                            "Error procesando orderpoint para producto=%s, warehouse=%s: %s",
                            product_id, warehouse_id, e
                        )
                    result['errors'] += 1

            # Ejecutar updates en batch
            if to_update:
                for op_id, vals in to_update.items():
                    try:
                        Orderpoint.browse(op_id).sudo().write(vals)
                        result['updated'] += 1
                    except Exception as e:
                        _logger.warning("Error actualizando orderpoint %s: %s", op_id, e)
                        result['errors'] += 1

            # Ejecutar creates en batch
            if to_create:
                try:
                    Orderpoint.sudo().create(to_create)
                    result['created'] += len(to_create)
                except Exception as e:
                    _logger.warning("Error creando orderpoints: %s", e)
                    result['errors'] += len(to_create)

        except Exception as e:
            _logger.error("Error en _update_orderpoints_batch: %s", e)
            result['errors'] += 1

        return result

    @api.model
    def cron_process_replenishment_queue(self, batch_size=1000, time_limit=55):
        """
        Método llamado por el cron job.

        Este es el entry point principal para el procesamiento de la cola.
        """
        return self.process_queue(
            batch_size=batch_size,
            time_limit=time_limit
        )

    @api.model
    def get_processing_stats(self):
        """
        Obtiene estadísticas del sistema de procesamiento.

        Returns:
            dict: Estadísticas completas del sistema
        """
        Queue = self.env['product.replenishment.queue']
        DeadLetter = self.env['product.replenishment.dead.letter']
        RollingStats = self.env['product.sales.stats.rolling']
        DailyStats = self.env['product.sales.stats.daily']

        queue_stats = Queue.get_queue_stats()
        dead_letter_stats = DeadLetter.get_dead_letter_stats()

        # Contar registros en daily y rolling stats
        self.env.cr.execute("SELECT COUNT(*) FROM product_sales_stats_daily")
        daily_count = self.env.cr.fetchone()[0]

        self.env.cr.execute("SELECT COUNT(*) FROM product_sales_stats_rolling")
        rolling_count = self.env.cr.fetchone()[0]

        return {
            'queue': queue_stats,
            'dead_letter': dead_letter_stats,
            'daily_stats_count': daily_count,
            'rolling_stats_count': rolling_count,
            'backpressure': Queue.check_backpressure(),
        }

    @api.model
    def recalculate_all_orderpoints(self, batch_size=1000):
        """
        Recalcula MAX/MIN para TODOS los productos con rolling stats.

        Útil después de migración o cambios en reglas de reabastecimiento.

        Args:
            batch_size: Tamaño del batch

        Returns:
            dict: {updated: int, created: int, errors: int}
        """
        _logger.info("Iniciando recálculo de todos los orderpoints...")

        # Obtener todos los pares producto/warehouse de rolling_stats
        self.env.cr.execute("""
            SELECT DISTINCT product_id, warehouse_id
            FROM product_sales_stats_rolling
            WHERE record_type = 'sale'
        """)
        pairs = self.env.cr.fetchall()

        total = len(pairs)
        result = {'updated': 0, 'created': 0, 'errors': 0}

        _logger.info("Recalculando orderpoints para %s pares producto/warehouse", total)

        for i in range(0, total, batch_size):
            batch = pairs[i:i + batch_size]
            try:
                batch_result = self._update_orderpoints_batch(list(batch))
                result['updated'] += batch_result.get('updated', 0)
                result['created'] += batch_result.get('created', 0)
                result['errors'] += batch_result.get('errors', 0)

                self.env.cr.commit()
                _logger.info(
                    "Orderpoints: batch %s/%s completado (updated=%s, created=%s)",
                    (i // batch_size) + 1,
                    (total // batch_size) + 1,
                    batch_result.get('updated', 0),
                    batch_result.get('created', 0)
                )
            except Exception as e:
                result['errors'] += 1
                _logger.error("Error en batch %s: %s", i, e)
                self.env.cr.rollback()

        _logger.info(
            "Recálculo de orderpoints completado: updated=%s, created=%s, errors=%s",
            result['updated'], result['created'], result['errors']
        )

        return result

    @api.model
    def cleanup_old_data(self, daily_stats_days=90, dead_letter_days=90,
                         event_log_days=90):
        """
        Limpia datos antiguos de todas las tablas.

        Args:
            daily_stats_days: Días para mantener daily stats
            dead_letter_days: Días para mantener dead letter resueltos
            event_log_days: Días para mantener particiones de event log

        Returns:
            dict: Contadores de registros eliminados
        """
        DailyStats = self.env['product.sales.stats.daily']
        DeadLetter = self.env['product.replenishment.dead.letter']
        EventLog = self.env['product.sale.event.log']
        RollingStats = self.env['product.sales.stats.rolling']

        stats = {
            'daily_stats_deleted': 0,
            'dead_letter_deleted': 0,
            'event_log_partitions_deleted': 0,
            'orphan_rolling_deleted': 0,
        }

        _logger.info("Iniciando limpieza de datos antiguos...")

        try:
            stats['daily_stats_deleted'] = DailyStats.cleanup_old_daily_stats(
                days=daily_stats_days
            )
        except Exception as e:
            _logger.error("Error limpiando daily stats: %s", e)

        try:
            stats['dead_letter_deleted'] = DeadLetter.cleanup_old_resolved(
                days=dead_letter_days
            )
        except Exception as e:
            _logger.error("Error limpiando dead letter: %s", e)

        try:
            stats['event_log_partitions_deleted'] = EventLog.cleanup_old_partitions(
                days=event_log_days
            )
        except Exception as e:
            _logger.error("Error limpiando event log: %s", e)

        try:
            stats['orphan_rolling_deleted'] = RollingStats.cleanup_orphan_stats()
        except Exception as e:
            _logger.error("Error limpiando orphan rolling stats: %s", e)

        _logger.info("Limpieza completada: %s", stats)

        return stats
