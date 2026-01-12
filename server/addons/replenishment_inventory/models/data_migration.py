# -*- coding: utf-8 -*-
"""
Migración de Datos - Arquitectura de 4 Capas

Utilidad para migrar datos existentes del sistema anterior
a la nueva arquitectura de 4 capas.

Este módulo pobla:
1. product_sales_stats_daily desde product_warehouse_sale_summary
2. product_sales_stats_rolling calculando stats para cada producto/warehouse
"""

import logging
from datetime import date, timedelta
from odoo import models, api

_logger = logging.getLogger(__name__)


class DataMigration(models.AbstractModel):
    """
    Modelo abstracto para migración de datos.

    Proporciona métodos para:
    - Migrar datos históricos a daily stats
    - Calcular rolling stats iniciales
    - Verificar integridad de la migración
    """
    _name = 'replenishment.data.migration'
    _description = 'Migración de Datos de Reabastecimiento'

    @api.model
    def migrate_to_new_architecture(self, days_back=90, batch_size=5000):
        """
        Migra datos existentes a la nueva arquitectura de 4 capas.

        Este es el método principal para ejecutar la migración completa.

        Args:
            days_back: Días de historial a migrar
            batch_size: Tamaño del batch para procesamiento

        Returns:
            dict: Estadísticas de migración
        """
        _logger.info("=== INICIANDO MIGRACIÓN A ARQUITECTURA 4 CAPAS ===")
        _logger.info("Parámetros: days_back=%s, batch_size=%s", days_back, batch_size)

        stats = {
            'daily_stats_created': 0,
            'rolling_stats_created': 0,
            'errors': [],
        }

        # Paso 1: Migrar a daily stats
        _logger.info("Paso 1/2: Migrando a daily stats...")
        daily_result = self._migrate_to_daily_stats(days_back, batch_size)
        stats['daily_stats_created'] = daily_result.get('records_created', 0)

        if daily_result.get('errors'):
            stats['errors'].extend(daily_result['errors'])

        # Paso 2: Calcular rolling stats
        _logger.info("Paso 2/2: Calculando rolling stats...")
        rolling_result = self._calculate_all_rolling_stats(batch_size)
        stats['rolling_stats_created'] = rolling_result.get('records_created', 0)

        if rolling_result.get('errors'):
            stats['errors'].extend(rolling_result['errors'])

        _logger.info("=== MIGRACIÓN COMPLETADA ===")
        _logger.info("Resultados: %s", stats)

        return stats

    @api.model
    def _migrate_to_daily_stats(self, days_back=90, batch_size=5000):
        """
        Migra datos de product.warehouse.sale.summary a daily stats.

        Agrupa los registros por (product_id, warehouse_id, date, record_type)
        y los inserta en product_sales_stats_daily.

        Args:
            days_back: Días de historial a migrar
            batch_size: Tamaño del batch

        Returns:
            dict: {records_created, errors}
        """
        result = {
            'records_created': 0,
            'errors': []
        }

        date_from = date.today() - timedelta(days=days_back)

        _logger.info(
            "Migrando registros desde %s (últimos %s días)",
            date_from, days_back
        )

        # Query para agregar datos existentes
        # IMPORTANTE: Para ventas solo se toman datos del sistema legado,
        # para transferencias se toman todos los registros
        query = """
            INSERT INTO product_sales_stats_daily
                (product_id, warehouse_id, date, record_type,
                 quantity_total, event_count, last_updated,
                 create_uid, create_date, write_uid, write_date)
            SELECT
                product_id,
                warehouse_id,
                date,
                COALESCE(record_type, 'sale') as record_type,
                SUM(quantity_sold) as quantity_total,
                COUNT(*) as event_count,
                NOW() as last_updated,
                %s as create_uid,
                NOW() as create_date,
                %s as write_uid,
                NOW() as write_date
            FROM product_warehouse_sale_summary
            WHERE date >= %s
              AND product_id IS NOT NULL
              AND warehouse_id IS NOT NULL
              AND (
                  -- Para ventas: solo sistema legado
                  (COALESCE(record_type, 'sale') = 'sale' AND is_legacy_system = TRUE)
                  OR
                  -- Para transferencias: todos los registros
                  (record_type = 'transfer')
              )
            GROUP BY product_id, warehouse_id, date, COALESCE(record_type, 'sale')
            ON CONFLICT (product_id, warehouse_id, date, record_type)
            DO UPDATE SET
                quantity_total = EXCLUDED.quantity_total,
                event_count = EXCLUDED.event_count,
                last_updated = NOW(),
                write_date = NOW()
        """

        try:
            self.env.cr.execute(query, (self.env.uid, self.env.uid, date_from))
            result['records_created'] = self.env.cr.rowcount
            _logger.info(
                "Daily stats: %s registros creados/actualizados",
                result['records_created']
            )
        except Exception as e:
            error_msg = f"Error migrando a daily stats: {e}"
            _logger.error(error_msg)
            result['errors'].append(error_msg)

        return result

    @api.model
    def _calculate_all_rolling_stats(self, batch_size=5000):
        """
        Calcula rolling stats para todos los pares producto/warehouse.

        Args:
            batch_size: Tamaño del batch para procesamiento

        Returns:
            dict: {records_created, errors}
        """
        result = {
            'records_created': 0,
            'errors': []
        }

        # Obtener todos los pares únicos producto/warehouse
        self.env.cr.execute("""
            SELECT DISTINCT product_id, warehouse_id
            FROM product_sales_stats_daily
            WHERE product_id IS NOT NULL
              AND warehouse_id IS NOT NULL
        """)
        pairs = self.env.cr.fetchall()

        total_pairs = len(pairs)
        _logger.info("Rolling stats: %s pares producto/warehouse a procesar", total_pairs)

        RollingStats = self.env['product.sales.stats.rolling']

        # Procesar en batches
        for i in range(0, total_pairs, batch_size):
            batch = pairs[i:i + batch_size]

            try:
                updated = RollingStats.update_rolling_stats(
                    batch,
                    source='migration'
                )
                result['records_created'] += updated

                # Commit después de cada batch
                self.env.cr.commit()

                _logger.info(
                    "Rolling stats: batch %s/%s completado (%s registros)",
                    (i // batch_size) + 1,
                    (total_pairs // batch_size) + 1,
                    updated
                )

            except Exception as e:
                error_msg = f"Error calculando rolling stats (batch {i}): {e}"
                _logger.error(error_msg)
                result['errors'].append(error_msg)
                self.env.cr.rollback()

        _logger.info(
            "Rolling stats: %s registros creados en total",
            result['records_created']
        )

        return result

    @api.model
    def verify_migration(self):
        """
        Verifica la integridad de la migración.

        Compara los datos originales con los migrados para detectar
        discrepancias.

        Returns:
            dict: Resultados de la verificación
        """
        _logger.info("Verificando integridad de la migración...")

        result = {
            'status': 'ok',
            'issues': [],
            'counts': {},
            'details': {}
        }

        # Contar registros en cada tabla
        self.env.cr.execute("SELECT COUNT(*) FROM product_warehouse_sale_summary")
        original_count = self.env.cr.fetchone()[0]

        self.env.cr.execute("SELECT COUNT(*) FROM product_sales_stats_daily")
        daily_count = self.env.cr.fetchone()[0]

        self.env.cr.execute("SELECT COUNT(*) FROM product_sales_stats_rolling")
        rolling_count = self.env.cr.fetchone()[0]

        # Contar rolling stats por tipo (excluyendo 'global' del conteo principal)
        self.env.cr.execute("""
            SELECT record_type, COUNT(*)
            FROM product_sales_stats_rolling
            GROUP BY record_type
        """)
        rolling_by_type = dict(self.env.cr.fetchall())

        result['counts'] = {
            'original_records': original_count,
            'daily_stats': daily_count,
            'rolling_stats': rolling_count,
            'rolling_stats_global': rolling_by_type.get('global', 0),
            'rolling_stats_sale': rolling_by_type.get('sale', 0),
            'rolling_stats_transfer': rolling_by_type.get('transfer', 0),
            'rolling_stats_combined': rolling_by_type.get('combined', 0),
        }

        # Verificar que daily_stats cubre el mismo período
        self.env.cr.execute("""
            SELECT MIN(date), MAX(date), COUNT(DISTINCT product_id)
            FROM product_warehouse_sale_summary
            WHERE product_id IS NOT NULL
        """)
        orig = self.env.cr.fetchone()

        self.env.cr.execute("""
            SELECT MIN(date), MAX(date), COUNT(DISTINCT product_id)
            FROM product_sales_stats_daily
        """)
        daily = self.env.cr.fetchone()

        if orig[0] and daily[0]:
            if orig[0] < daily[0]:
                result['issues'].append(
                    f"Daily stats no cubre fechas antiguas: "
                    f"original desde {orig[0]}, daily desde {daily[0]}"
                )

            if orig[2] != daily[2]:
                diff = orig[2] - daily[2]
                result['issues'].append(
                    f"Diferencia en productos: "
                    f"original {orig[2]}, daily {daily[2]} ({diff} faltantes)"
                )

                # Analizar los productos faltantes
                missing_analysis = self._analyze_missing_products(daily[0])
                result['details']['missing_products'] = missing_analysis

                # Agregar resumen al issues
                if missing_analysis:
                    result['issues'].append(
                        f"  → Productos faltantes activos: {missing_analysis.get('active', 0)}"
                    )
                    result['issues'].append(
                        f"  → Productos faltantes inactivos: {missing_analysis.get('inactive', 0)}"
                    )
                    result['issues'].append(
                        f"  → Sin ventas en últimos 90 días: {missing_analysis.get('no_recent_sales', 0)}"
                    )

        # Verificar totales (con la misma lógica de filtrado)
        self.env.cr.execute("""
            SELECT SUM(quantity_sold)
            FROM product_warehouse_sale_summary
            WHERE date >= CURRENT_DATE - INTERVAL '90 days'
              AND (
                  (COALESCE(record_type, 'sale') = 'sale' AND is_legacy_system = TRUE)
                  OR
                  (record_type = 'transfer')
              )
        """)
        orig_total = self.env.cr.fetchone()[0] or 0

        self.env.cr.execute("""
            SELECT SUM(quantity_total)
            FROM product_sales_stats_daily
        """)
        daily_total = self.env.cr.fetchone()[0] or 0

        if abs(orig_total - daily_total) > 0.01:
            result['issues'].append(
                f"Diferencia en totales: original {orig_total:.2f}, "
                f"daily {daily_total:.2f}"
            )

        if result['issues']:
            result['status'] = 'warning'

        _logger.info("Verificación completada: %s", result)

        return result

    @api.model
    def _analyze_missing_products(self, daily_min_date):
        """
        Analiza los productos que están en original pero no en daily_stats.

        Args:
            daily_min_date: Fecha mínima en daily_stats

        Returns:
            dict: Análisis de productos faltantes
        """
        try:
            # Productos en original que NO están en daily_stats
            self.env.cr.execute("""
                WITH missing AS (
                    SELECT DISTINCT s.product_id
                    FROM product_warehouse_sale_summary s
                    WHERE s.product_id IS NOT NULL
                      AND s.product_id NOT IN (
                          SELECT DISTINCT product_id
                          FROM product_sales_stats_daily
                      )
                )
                SELECT
                    COUNT(*) as total_missing,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM product_product p
                            WHERE p.id = missing.product_id AND p.active = TRUE
                        )
                    ) as active_products,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM product_product p
                            WHERE p.id = missing.product_id AND p.active = FALSE
                        )
                    ) as inactive_products,
                    COUNT(*) FILTER (
                        WHERE NOT EXISTS (
                            SELECT 1 FROM product_warehouse_sale_summary s2
                            WHERE s2.product_id = missing.product_id
                              AND s2.date >= CURRENT_DATE - INTERVAL '90 days'
                        )
                    ) as no_recent_sales
                FROM missing
            """)

            row = self.env.cr.fetchone()

            if row:
                return {
                    'total': row[0] or 0,
                    'active': row[1] or 0,
                    'inactive': row[2] or 0,
                    'no_recent_sales': row[3] or 0,
                }

        except Exception as e:
            _logger.warning("Error analizando productos faltantes: %s", e)

        return {}

    @api.model
    def cleanup_and_reset(self):
        """
        Limpia las tablas de la nueva arquitectura.

        ADVERTENCIA: Esto elimina todos los datos migrados.
        Usar solo durante desarrollo/testing.

        Returns:
            dict: Contadores de registros eliminados
        """
        _logger.warning("=== LIMPIEZA Y RESET DE ARQUITECTURA 4 CAPAS ===")

        result = {}

        tables = [
            'product_replenishment_queue',
            'product_replenishment_dead_letter',
            'product_sales_stats_daily',
            'product_sales_stats_rolling',
        ]

        for table in tables:
            try:
                self.env.cr.execute(f"DELETE FROM {table}")
                result[table] = self.env.cr.rowcount
                _logger.info("%s: %s registros eliminados", table, result[table])
            except Exception as e:
                _logger.error("Error limpiando %s: %s", table, e)
                result[table] = f"Error: {e}"

        self.env.cr.commit()

        _logger.warning("Limpieza completada: %s", result)

        return result

    @api.model
    def run_initial_migration(self):
        """
        Método de conveniencia para ejecutar la migración inicial.

        Puede ser llamado desde un cron job o manualmente después
        de instalar el módulo.
        """
        _logger.info("Ejecutando migración inicial...")

        # Verificar si ya hay datos migrados
        self.env.cr.execute("SELECT COUNT(*) FROM product_sales_stats_daily")
        existing = self.env.cr.fetchone()[0]

        if existing > 0:
            _logger.info(
                "Ya existen %s registros en daily stats. "
                "Usa cleanup_and_reset() primero si quieres remigrar.",
                existing
            )
            return {'status': 'skipped', 'reason': 'data_already_exists'}

        # Ejecutar migración
        return self.migrate_to_new_architecture(days_back=90, batch_size=5000)
