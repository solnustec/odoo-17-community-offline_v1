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

        # Desviación estándar poblacional
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

        # Aproximación Poisson como piso mínimo SIEMPRE
        # Para farmacias/retail con ventas en unidades enteras: stddev >= sqrt(mean)
        # Esto evita stddev = 0 cuando hay ventas constantes pero esporádicas
        stddev_poisson = math.sqrt(mean) if mean > 0 else 0.0
        stddev = max(stddev, stddev_poisson)

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

        _logger.debug("Rolling stats actualizadas: %s registros", updated)
        return updated

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
