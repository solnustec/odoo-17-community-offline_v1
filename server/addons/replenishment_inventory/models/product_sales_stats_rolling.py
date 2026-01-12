# -*- coding: utf-8 -*-
"""
Estadísticas Rolling de Ventas - Arquitectura de 4 Capas

Tabla que mantiene estadísticas precalculadas (media, stddev, etc.)
para ventanas de tiempo rolling (30, 60, 90 días).

Esta es la capa que consultan los orderpoints para tomar decisiones
de reabastecimiento.
"""

import math
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# Constante para aproximación Poisson
MIN_OBSERVATIONS_FOR_STDDEV = 2


class ProductSalesStatsRolling(models.Model):
    """
    Estadísticas rolling precalculadas por producto/warehouse.

    Mantiene múltiples ventanas de tiempo (30, 60, 90 días) con:
    - Media diaria de ventas
    - Desviación estándar (con corrección de días sin venta)
    - Coeficiente de variación
    - Fecha de última actualización

    Esta tabla es la "vista materializada" que consultan los orderpoints.
    """
    _name = 'product.sales.stats.rolling'
    _description = 'Estadísticas Rolling de Ventas'
    _order = 'product_id, warehouse_id'

    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        ondelete='cascade'
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        required=True,
        ondelete='cascade'
    )
    record_type = fields.Selection(
        selection=[
            ('sale', 'Venta'),
            ('transfer', 'Transferencia'),
            ('combined', 'Combinado (Venta + Transferencia)'),
            ('global', 'Global (Todas las Bodegas)'),
        ],
        string='Tipo',
        required=True,
        default='sale'
    )

    # Estadísticas para 30 días
    mean_30d = fields.Float(
        string='Media 30 días',
        digits=(16, 4),
        default=0.0
    )
    stddev_30d = fields.Float(
        string='Desv. Est. 30 días',
        digits=(16, 4),
        default=0.0
    )
    cv_30d = fields.Float(
        string='Coef. Var. 30 días',
        digits=(16, 4),
        default=0.0,
        help='Coeficiente de variación = stddev/mean'
    )
    total_qty_30d = fields.Float(
        string='Total 30 días',
        digits=(16, 4),
        default=0.0
    )
    days_with_sales_30d = fields.Integer(
        string='Días con Venta 30d',
        default=0
    )

    # Estadísticas para 60 días
    mean_60d = fields.Float(
        string='Media 60 días',
        digits=(16, 4),
        default=0.0
    )
    stddev_60d = fields.Float(
        string='Desv. Est. 60 días',
        digits=(16, 4),
        default=0.0
    )
    cv_60d = fields.Float(
        string='Coef. Var. 60 días',
        digits=(16, 4),
        default=0.0
    )
    total_qty_60d = fields.Float(
        string='Total 60 días',
        digits=(16, 4),
        default=0.0
    )
    days_with_sales_60d = fields.Integer(
        string='Días con Venta 60d',
        default=0
    )

    # Estadísticas para 90 días
    mean_90d = fields.Float(
        string='Media 90 días',
        digits=(16, 4),
        default=0.0
    )
    stddev_90d = fields.Float(
        string='Desv. Est. 90 días',
        digits=(16, 4),
        default=0.0
    )
    cv_90d = fields.Float(
        string='Coef. Var. 90 días',
        digits=(16, 4),
        default=0.0
    )
    total_qty_90d = fields.Float(
        string='Total 90 días',
        digits=(16, 4),
        default=0.0
    )
    days_with_sales_90d = fields.Integer(
        string='Días con Venta 90d',
        default=0
    )

    # Metadata
    last_calculated = fields.Datetime(
        string='Última Actualización',
        default=fields.Datetime.now
    )
    calculation_source = fields.Selection(
        selection=[
            ('queue', 'Cola de Eventos'),
            ('full_recalc', 'Recálculo Completo'),
            ('migration', 'Migración'),
            ('global_calc', 'Cálculo Global'),
        ],
        string='Fuente de Cálculo',
        default='queue'
    )

    _sql_constraints = [
        ('unique_rolling_stat',
         'UNIQUE(product_id, warehouse_id, record_type)',
         'Ya existe un registro para este producto/almacén/tipo')
    ]

    @api.model
    def _calculate_mean_stddev(self, values):
        """
        Calcula media y desviación estándar de una lista de valores.

        IMPORTANTE: La lista debe incluir días sin venta como ceros
        para que el stddev sea correcto.

        Args:
            values: Lista de cantidades diarias (incluyendo ceros)

        Returns:
            tuple: (mean, stddev)
        """
        if not values:
            return 0.0, 0.0

        n = len(values)
        if n == 0:
            return 0.0, 0.0

        mean = sum(values) / n

        if n == 1:
            return mean, 0.0

        # Desviación estándar poblacional (igual que DESVEST.P en Excel)
        variance = sum((x - mean) ** 2 for x in values) / n
        stddev = math.sqrt(variance)

        return mean, stddev

    @api.model
    def _calculate_stats_for_period(self, daily_data, period_days):
        """
        Calcula estadísticas para un período dado.

        Args:
            daily_data: dict del método get_aggregated_for_rolling
            period_days: Días del período (30, 60, 90)

        Returns:
            dict: {mean, stddev, cv, total_qty, days_with_sales}
        """
        daily_quantities = daily_data.get('daily_quantities', [])
        total_qty = daily_data.get('total_quantity', 0)
        days_with_sales = len(daily_quantities)

        # CORRECCIÓN CRÍTICA: Incluir días sin venta como ceros
        days_without_sales = period_days - days_with_sales
        if days_without_sales > 0:
            full_values = daily_quantities + [0.0] * days_without_sales
        else:
            full_values = daily_quantities

        mean, stddev = self._calculate_mean_stddev(full_values)

        # Coeficiente de variación
        cv = stddev / mean if mean > 0 else 0.0

        return {
            'mean': round(mean, 4),
            'stddev': round(stddev, 4),
            'cv': round(cv, 4),
            'total_qty': round(total_qty, 4),
            'days_with_sales': days_with_sales
        }

    @api.model
    def update_rolling_stats(self, product_warehouse_pairs, source='queue'):
        """
        Actualiza las estadísticas rolling para los pares producto/warehouse.

        Este método es llamado después de procesar un batch de la cola.

        Args:
            product_warehouse_pairs: Lista de tuplas (product_id, warehouse_id)
            source: Fuente del cálculo ('queue', 'full_recalc', 'migration')

        Returns:
            int: Número de registros actualizados
        """
        from datetime import date, timedelta

        if not product_warehouse_pairs:
            return 0

        DailyStats = self.env['product.sales.stats.daily']
        today = date.today()

        # Definir períodos
        periods = {
            '30d': (today - timedelta(days=30), today, 30),
            '60d': (today - timedelta(days=60), today, 60),
            '90d': (today - timedelta(days=90), today, 90),
        }

        updated = 0

        for product_id, warehouse_id in product_warehouse_pairs:
            # Calcular stats para cada tipo de registro
            for record_type in ['sale', 'transfer', 'combined']:
                if record_type == 'combined':
                    record_types_filter = ['sale', 'transfer']
                else:
                    record_types_filter = [record_type]

                # Calcular para cada período
                stats_30d = stats_60d = stats_90d = None

                for period_key, (date_from, date_to, days) in periods.items():
                    daily_data = DailyStats.get_aggregated_for_rolling(
                        product_id=product_id,
                        warehouse_id=warehouse_id,
                        date_from=date_from,
                        date_to=date_to,
                        record_types=record_types_filter
                    )

                    stats = self._calculate_stats_for_period(daily_data, days)

                    if period_key == '30d':
                        stats_30d = stats
                    elif period_key == '60d':
                        stats_60d = stats
                    else:
                        stats_90d = stats

                # UPSERT rolling stats
                if stats_30d and stats_60d and stats_90d:
                    self._upsert_rolling_stat(
                        product_id=product_id,
                        warehouse_id=warehouse_id,
                        record_type=record_type,
                        stats_30d=stats_30d,
                        stats_60d=stats_60d,
                        stats_90d=stats_90d,
                        source=source
                    )
                    updated += 1

        # Actualizar estadísticas globales para bodega principal
        # Solo los productos que fueron actualizados en este batch
        global_updated = self._update_global_stats_for_products(
            product_warehouse_pairs, periods, today, source
        )
        updated += global_updated

        _logger.debug("Rolling stats actualizadas: %s registros", updated)
        return updated

    def _update_global_stats_for_products(self, product_warehouse_pairs, periods, today, source):
        """
        Actualiza estadísticas globales para los productos del batch.

        Suma las daily_stats de TODAS las bodegas para cada producto y
        actualiza el registro 'global' en la bodega principal.

        Args:
            product_warehouse_pairs: Lista de tuplas (product_id, warehouse_id)
            periods: Dict con períodos {key: (date_from, date_to, days)}
            today: Fecha actual
            source: Fuente del cálculo

        Returns:
            int: Número de registros globales actualizados
        """
        # Obtener productos únicos del batch
        product_ids = list(set(p[0] for p in product_warehouse_pairs))

        if not product_ids:
            return 0

        # Buscar bodega principal
        main_warehouse = self.env['stock.warehouse'].search([
            ('is_main_warehouse', '=', True)
        ], limit=1)

        if not main_warehouse:
            return 0

        main_wh_id = main_warehouse.id
        updated = 0

        # Para cada producto, calcular el global sumando TODAS las bodegas
        for product_id in product_ids:
            try:
                global_stats = self._calculate_global_stats_for_product(
                    product_id, periods, today
                )

                if global_stats:
                    self._upsert_rolling_stat(
                        product_id=product_id,
                        warehouse_id=main_wh_id,
                        record_type='global',
                        stats_30d=global_stats['30d'],
                        stats_60d=global_stats['60d'],
                        stats_90d=global_stats['90d'],
                        source=source
                    )
                    updated += 1
            except Exception as e:
                _logger.warning(
                    "Error actualizando global stats para producto %s: %s",
                    product_id, e
                )

        return updated

    def _calculate_global_stats_for_product(self, product_id, periods, today):
        """
        Calcula estadísticas globales para UN producto sumando TODAS las bodegas.

        Args:
            product_id: ID del producto
            periods: Dict con períodos
            today: Fecha actual

        Returns:
            dict: {'30d': stats, '60d': stats, '90d': stats} o None si no hay datos
        """
        from datetime import timedelta

        date_30d = periods['30d'][0]
        date_60d = periods['60d'][0]
        date_90d = periods['90d'][0]

        # Consulta SQL que suma todas las bodegas por fecha
        self.env.cr.execute("""
            WITH daily_global AS (
                SELECT date, SUM(quantity_total) as daily_qty
                FROM product_sales_stats_daily
                WHERE product_id = %s
                  AND record_type IN ('sale', 'transfer')
                  AND date >= %s
                GROUP BY date
            )
            SELECT
                -- Stats 30 días
                (SELECT COUNT(*) FROM daily_global WHERE date >= %s) as days_30,
                (SELECT COALESCE(SUM(daily_qty), 0) FROM daily_global WHERE date >= %s) as total_30,
                -- Stats 60 días
                (SELECT COUNT(*) FROM daily_global WHERE date >= %s) as days_60,
                (SELECT COALESCE(SUM(daily_qty), 0) FROM daily_global WHERE date >= %s) as total_60,
                -- Stats 90 días
                (SELECT COUNT(*) FROM daily_global) as days_90,
                (SELECT COALESCE(SUM(daily_qty), 0) FROM daily_global) as total_90
        """, (product_id, date_90d, date_30d, date_30d, date_60d, date_60d))

        row = self.env.cr.fetchone()

        if not row or (row[1] == 0 and row[3] == 0 and row[5] == 0):
            return None

        days_30, total_30 = row[0] or 0, row[1] or 0
        days_60, total_60 = row[2] or 0, row[3] or 0
        days_90, total_90 = row[4] or 0, row[5] or 0

        # Calcular medias (dividiendo por el período completo, no solo días con venta)
        mean_30 = total_30 / 30
        mean_60 = total_60 / 60
        mean_90 = total_90 / 90

        # Calcular stddev global
        stddev_30, stddev_60, stddev_90 = self._calculate_global_stddev(
            product_id, date_30d, date_60d, date_90d, today,
            mean_30, mean_60, mean_90
        )

        # Calcular CV
        cv_30 = stddev_30 / mean_30 if mean_30 > 0 else 0
        cv_60 = stddev_60 / mean_60 if mean_60 > 0 else 0
        cv_90 = stddev_90 / mean_90 if mean_90 > 0 else 0

        return {
            '30d': {
                'mean': round(mean_30, 4),
                'stddev': round(stddev_30, 4),
                'cv': round(cv_30, 4),
                'total_qty': round(total_30, 4),
                'days_with_sales': days_30
            },
            '60d': {
                'mean': round(mean_60, 4),
                'stddev': round(stddev_60, 4),
                'cv': round(cv_60, 4),
                'total_qty': round(total_60, 4),
                'days_with_sales': days_60
            },
            '90d': {
                'mean': round(mean_90, 4),
                'stddev': round(stddev_90, 4),
                'cv': round(cv_90, 4),
                'total_qty': round(total_90, 4),
                'days_with_sales': days_90
            }
        }

    def _upsert_rolling_stat(self, product_id, warehouse_id, record_type,
                             stats_30d, stats_60d, stats_90d, source='queue'):
        """
        Hace UPSERT de un registro de rolling stats.
        """
        self.env.cr.execute("""
            INSERT INTO product_sales_stats_rolling
                (product_id, warehouse_id, record_type,
                 mean_30d, stddev_30d, cv_30d, total_qty_30d, days_with_sales_30d,
                 mean_60d, stddev_60d, cv_60d, total_qty_60d, days_with_sales_60d,
                 mean_90d, stddev_90d, cv_90d, total_qty_90d, days_with_sales_90d,
                 last_calculated, calculation_source,
                 create_uid, create_date, write_uid, write_date)
            VALUES
                (%s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 NOW(), %s,
                 %s, NOW(), %s, NOW())
            ON CONFLICT (product_id, warehouse_id, record_type)
            DO UPDATE SET
                mean_30d = EXCLUDED.mean_30d,
                stddev_30d = EXCLUDED.stddev_30d,
                cv_30d = EXCLUDED.cv_30d,
                total_qty_30d = EXCLUDED.total_qty_30d,
                days_with_sales_30d = EXCLUDED.days_with_sales_30d,
                mean_60d = EXCLUDED.mean_60d,
                stddev_60d = EXCLUDED.stddev_60d,
                cv_60d = EXCLUDED.cv_60d,
                total_qty_60d = EXCLUDED.total_qty_60d,
                days_with_sales_60d = EXCLUDED.days_with_sales_60d,
                mean_90d = EXCLUDED.mean_90d,
                stddev_90d = EXCLUDED.stddev_90d,
                cv_90d = EXCLUDED.cv_90d,
                total_qty_90d = EXCLUDED.total_qty_90d,
                days_with_sales_90d = EXCLUDED.days_with_sales_90d,
                last_calculated = NOW(),
                calculation_source = EXCLUDED.calculation_source,
                write_uid = EXCLUDED.write_uid,
                write_date = NOW()
        """, (
            product_id, warehouse_id, record_type,
            stats_30d['mean'], stats_30d['stddev'], stats_30d['cv'],
            stats_30d['total_qty'], stats_30d['days_with_sales'],
            stats_60d['mean'], stats_60d['stddev'], stats_60d['cv'],
            stats_60d['total_qty'], stats_60d['days_with_sales'],
            stats_90d['mean'], stats_90d['stddev'], stats_90d['cv'],
            stats_90d['total_qty'], stats_90d['days_with_sales'],
            source,
            self.env.uid, self.env.uid
        ))

    @api.model
    def get_stats(self, product_id, warehouse_id, record_type='sale', days=30):
        """
        Obtiene estadísticas para un producto/warehouse.

        Este es el método principal que usan los orderpoints.

        Args:
            product_id: ID del producto
            warehouse_id: ID del almacén
            record_type: 'sale', 'transfer', o 'combined'
            days: Período (30, 60, o 90)

        Returns:
            dict: {mean, stddev, cv, total_qty, days_with_sales}
        """
        record = self.search([
            ('product_id', '=', product_id),
            ('warehouse_id', '=', warehouse_id),
            ('record_type', '=', record_type),
        ], limit=1)

        if not record:
            return {
                'mean': 0.0,
                'stddev': 0.0,
                'cv': 0.0,
                'total_qty': 0.0,
                'days_with_sales': 0,
                'found': False
            }

        if days == 30:
            return {
                'mean': record.mean_30d,
                'stddev': record.stddev_30d,
                'cv': record.cv_30d,
                'total_qty': record.total_qty_30d,
                'days_with_sales': record.days_with_sales_30d,
                'found': True
            }
        elif days == 60:
            return {
                'mean': record.mean_60d,
                'stddev': record.stddev_60d,
                'cv': record.cv_60d,
                'total_qty': record.total_qty_60d,
                'days_with_sales': record.days_with_sales_60d,
                'found': True
            }
        else:  # 90 días
            return {
                'mean': record.mean_90d,
                'stddev': record.stddev_90d,
                'cv': record.cv_90d,
                'total_qty': record.total_qty_90d,
                'days_with_sales': record.days_with_sales_90d,
                'found': True
            }

    @api.model
    def get_combined_stats(self, product_id, warehouse_id, days=30):
        """
        Obtiene estadísticas combinadas (venta + transferencia).

        Para warehouses híbridos que usan ambos tipos de movimientos.

        Args:
            product_id: ID del producto
            warehouse_id: ID del almacén
            days: Período (30, 60, o 90)

        Returns:
            dict: Estadísticas combinadas
        """
        return self.get_stats(
            product_id=product_id,
            warehouse_id=warehouse_id,
            record_type='combined',
            days=days
        )

    @api.model
    def recalculate_all_stats(self, batch_size=1000):
        """
        Recalcula TODOS los rolling stats existentes.

        Útil después de cambios en la lógica de cálculo (ej: Poisson floor).

        Returns:
            dict: {updated: int, errors: int}
        """
        _logger.info("Iniciando recálculo de todos los rolling stats...")

        # Obtener todos los pares únicos producto/warehouse
        self.env.cr.execute("""
            SELECT DISTINCT product_id, warehouse_id
            FROM product_sales_stats_rolling
        """)
        pairs = self.env.cr.fetchall()

        total = len(pairs)
        updated = 0
        errors = 0

        _logger.info("Recalculando %s pares producto/warehouse", total)

        for i in range(0, total, batch_size):
            batch = pairs[i:i + batch_size]
            try:
                count = self.update_rolling_stats(batch, source='full_recalc')
                updated += count
                self.env.cr.commit()
                _logger.info(
                    "Recálculo: batch %s/%s completado (%s registros)",
                    (i // batch_size) + 1,
                    (total // batch_size) + 1,
                    count
                )
            except Exception as e:
                errors += 1
                _logger.error("Error en batch %s: %s", i, e)
                self.env.cr.rollback()

        _logger.info(
            "Recálculo completado: %s actualizados, %s errores",
            updated, errors
        )

        return {'updated': updated, 'errors': errors}

    @api.model
    def cleanup_orphan_stats(self):
        """
        Elimina estadísticas de productos o warehouses que ya no existen.

        Returns:
            int: Número de registros eliminados
        """
        self.env.cr.execute("""
            DELETE FROM product_sales_stats_rolling r
            WHERE NOT EXISTS (
                SELECT 1 FROM product_product p WHERE p.id = r.product_id
            )
            OR NOT EXISTS (
                SELECT 1 FROM stock_warehouse w WHERE w.id = r.warehouse_id
            )
        """)

        deleted = self.env.cr.rowcount
        if deleted > 0:
            _logger.info("Rolling stats: %s registros huérfanos eliminados", deleted)

        return deleted

    # =========================================================================
    # ESTADÍSTICAS GLOBALES (Todas las Bodegas para Bodega Principal)
    # =========================================================================
    @api.model
    def update_global_rolling_stats(self, batch_size=1000):
        """
        Calcula y actualiza estadísticas globales para la bodega principal.

        Agrega las ventas de TODAS las bodegas por producto y las almacena
        con record_type='global' en la bodega principal.

        Optimizado para alto volumen (240+ bodegas, 10,000+ productos).

        Returns:
            dict: {updated: int, errors: int}
        """
        from datetime import date, timedelta

        _logger.info("Iniciando cálculo de estadísticas globales...")

        # Encontrar la bodega principal
        main_warehouse = self.env['stock.warehouse'].search([
            ('is_main_warehouse', '=', True)
        ], limit=1)

        if not main_warehouse:
            _logger.warning("No se encontró bodega principal (is_main_warehouse=True)")
            return {'updated': 0, 'errors': 0, 'message': 'No main warehouse found'}

        main_wh_id = main_warehouse.id
        today = date.today()

        # Períodos a calcular
        periods = [
            ('30d', today - timedelta(days=30), today, 30),
            ('60d', today - timedelta(days=60), today, 60),
            ('90d', today - timedelta(days=90), today, 90),
        ]

        updated = 0
        errors = 0

        try:
            # Paso 1: Obtener todos los productos únicos con estadísticas
            self.env.cr.execute("""
                SELECT DISTINCT product_id
                FROM product_sales_stats_daily
                WHERE record_type IN ('sale', 'transfer')
                  AND date >= %s
            """, (today - timedelta(days=90),))

            all_products = [row[0] for row in self.env.cr.fetchall()]
            total_products = len(all_products)

            _logger.info(
                "Calculando stats globales para %s productos en bodega %s",
                total_products, main_warehouse.name
            )

            # Paso 2: Procesar en batches para no saturar memoria
            for i in range(0, total_products, batch_size):
                batch_products = all_products[i:i + batch_size]

                try:
                    batch_updated = self._calculate_global_stats_batch(
                        batch_products, main_wh_id, periods, today
                    )
                    updated += batch_updated
                    self.env.cr.commit()

                    _logger.info(
                        "Global stats: batch %s/%s - %s productos actualizados",
                        (i // batch_size) + 1,
                        (total_products // batch_size) + 1,
                        batch_updated
                    )
                except Exception as e:
                    errors += 1
                    _logger.error("Error en batch %s: %s", i, e)
                    self.env.cr.rollback()

        except Exception as e:
            _logger.error("Error general en update_global_rolling_stats: %s", e)
            errors += 1

        _logger.info(
            "Cálculo global completado: %s actualizados, %s errores",
            updated, errors
        )

        return {'updated': updated, 'errors': errors}

    def _calculate_global_stats_batch(self, product_ids, main_wh_id, periods, today):
        """
        Calcula estadísticas globales para un batch de productos.

        Usa SQL directo para máxima eficiencia con alto volumen.

        Args:
            product_ids: Lista de IDs de productos
            main_wh_id: ID de la bodega principal
            periods: Lista de tuplas (key, date_from, date_to, days)
            today: Fecha actual

        Returns:
            int: Número de productos actualizados
        """
        if not product_ids:
            return 0

        # Consulta SQL que agrega todas las bodegas por producto y fecha
        # Calcula: total por día (sumando todas las bodegas), luego media y stddev
        query = """
            WITH daily_totals AS (
                -- Sumar cantidades de todas las bodegas por producto/fecha
                SELECT
                    product_id,
                    date,
                    SUM(quantity_total) as daily_qty
                FROM product_sales_stats_daily
                WHERE product_id = ANY(%s)
                  AND record_type IN ('sale', 'transfer')
                  AND date >= %s
                GROUP BY product_id, date
            ),
            stats_30d AS (
                SELECT
                    product_id,
                    COUNT(*) as days_with_sales,
                    SUM(daily_qty) as total_qty,
                    AVG(daily_qty) as avg_qty
                FROM daily_totals
                WHERE date >= %s
                GROUP BY product_id
            ),
            stats_60d AS (
                SELECT
                    product_id,
                    COUNT(*) as days_with_sales,
                    SUM(daily_qty) as total_qty,
                    AVG(daily_qty) as avg_qty
                FROM daily_totals
                WHERE date >= %s
                GROUP BY product_id
            ),
            stats_90d AS (
                SELECT
                    product_id,
                    COUNT(*) as days_with_sales,
                    SUM(daily_qty) as total_qty,
                    AVG(daily_qty) as avg_qty
                FROM daily_totals
                WHERE date >= %s
                GROUP BY product_id
            )
            SELECT
                COALESCE(s30.product_id, s60.product_id, s90.product_id) as product_id,
                COALESCE(s30.days_with_sales, 0) as days_30,
                COALESCE(s30.total_qty, 0) as total_30,
                COALESCE(s30.avg_qty, 0) as avg_30,
                COALESCE(s60.days_with_sales, 0) as days_60,
                COALESCE(s60.total_qty, 0) as total_60,
                COALESCE(s60.avg_qty, 0) as avg_60,
                COALESCE(s90.days_with_sales, 0) as days_90,
                COALESCE(s90.total_qty, 0) as total_90,
                COALESCE(s90.avg_qty, 0) as avg_90
            FROM stats_30d s30
            FULL OUTER JOIN stats_60d s60 ON s30.product_id = s60.product_id
            FULL OUTER JOIN stats_90d s90 ON COALESCE(s30.product_id, s60.product_id) = s90.product_id
        """

        date_90d = periods[2][1]  # 90 días atrás
        date_60d = periods[1][1]  # 60 días atrás
        date_30d = periods[0][1]  # 30 días atrás

        self.env.cr.execute(query, (
            product_ids,
            date_90d,  # Para daily_totals
            date_30d,  # Para stats_30d
            date_60d,  # Para stats_60d
            date_90d,  # Para stats_90d
        ))

        rows = self.env.cr.fetchall()

        if not rows:
            return 0

        # Calcular stddev y preparar UPSERTs
        # Para stddev necesitamos calcular la varianza de los totales diarios
        updated = 0

        for row in rows:
            product_id = row[0]
            if not product_id:
                continue

            days_30, total_30, avg_30 = row[1], row[2], row[3]
            days_60, total_60, avg_60 = row[4], row[5], row[6]
            days_90, total_90, avg_90 = row[7], row[8], row[9]

            # Calcular mean considerando días sin venta
            mean_30 = total_30 / 30 if total_30 else 0
            mean_60 = total_60 / 60 if total_60 else 0
            mean_90 = total_90 / 90 if total_90 else 0

            # Calcular stddev (necesitamos consulta separada para varianza)
            stddev_30, stddev_60, stddev_90 = self._calculate_global_stddev(
                product_id, date_30d, date_60d, date_90d, today,
                mean_30, mean_60, mean_90
            )

            # Calcular CV
            cv_30 = stddev_30 / mean_30 if mean_30 > 0 else 0
            cv_60 = stddev_60 / mean_60 if mean_60 > 0 else 0
            cv_90 = stddev_90 / mean_90 if mean_90 > 0 else 0

            # UPSERT
            self._upsert_rolling_stat(
                product_id=product_id,
                warehouse_id=main_wh_id,
                record_type='global',
                stats_30d={
                    'mean': round(mean_30, 4),
                    'stddev': round(stddev_30, 4),
                    'cv': round(cv_30, 4),
                    'total_qty': round(total_30, 4),
                    'days_with_sales': days_30
                },
                stats_60d={
                    'mean': round(mean_60, 4),
                    'stddev': round(stddev_60, 4),
                    'cv': round(cv_60, 4),
                    'total_qty': round(total_60, 4),
                    'days_with_sales': days_60
                },
                stats_90d={
                    'mean': round(mean_90, 4),
                    'stddev': round(stddev_90, 4),
                    'cv': round(cv_90, 4),
                    'total_qty': round(total_90, 4),
                    'days_with_sales': days_90
                },
                source='global_calc'
            )
            updated += 1

        return updated

    def _calculate_global_stddev(self, product_id, date_30d, date_60d, date_90d,
                                  today, mean_30, mean_60, mean_90):
        """
        Calcula la desviación estándar global para un producto.

        Agrega las cantidades diarias de todas las bodegas y calcula
        el stddev sobre esos totales.

        Returns:
            tuple: (stddev_30, stddev_60, stddev_90)
        """
        # Obtener totales diarios globales
        self.env.cr.execute("""
            SELECT date, SUM(quantity_total) as daily_total
            FROM product_sales_stats_daily
            WHERE product_id = %s
              AND record_type IN ('sale', 'transfer')
              AND date >= %s
            GROUP BY date
            ORDER BY date
        """, (product_id, date_90d))

        daily_data = {row[0]: row[1] for row in self.env.cr.fetchall()}

        def calc_stddev(date_from, period_days, mean):
            """Calcula stddev para un período, incluyendo días sin venta como 0."""
            from datetime import timedelta

            values = []
            current = date_from
            while current <= today:
                values.append(daily_data.get(current, 0.0))
                current += timedelta(days=1)

            # Asegurar que tenemos exactamente period_days valores
            if len(values) < period_days:
                values.extend([0.0] * (period_days - len(values)))
            elif len(values) > period_days:
                values = values[-period_days:]

            if not values or len(values) < 2:
                return 0.0

            # Varianza poblacional
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            return math.sqrt(variance)

        stddev_30 = calc_stddev(date_30d, 30, mean_30)
        stddev_60 = calc_stddev(date_60d, 60, mean_60)
        stddev_90 = calc_stddev(date_90d, 90, mean_90)

        return stddev_30, stddev_60, stddev_90
