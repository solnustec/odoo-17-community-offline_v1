# -*- coding: utf-8 -*-
"""
Estadísticas Diarias de Ventas - Arquitectura de 4 Capas

Tabla normalizada que mantiene agregados diarios de ventas por
producto/warehouse. Alimenta el cálculo de stats rolling.

Patrón: UPSERT (INSERT...ON CONFLICT) para actualización incremental
"""

import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ProductSalesStatsDaily(models.Model):
    """
    Agregados diarios de ventas/transferencias por producto y almacén.

    Esta tabla es el primer nivel de agregación:
    - Se actualiza incrementalmente con cada batch consumido de la cola
    - Usa UPSERT para evitar duplicados y race conditions
    - Sirve como fuente para calcular rolling stats

    Constraint único: (product_id, warehouse_id, date, record_type)
    """
    _name = 'product.sales.stats.daily'
    _description = 'Estadísticas Diarias de Ventas'
    _order = 'date desc, product_id'

    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        index=True,
        ondelete='cascade'
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        required=True,
        index=True,
        ondelete='cascade'
    )
    date = fields.Date(
        string='Fecha',
        required=True,
        index=True
    )
    record_type = fields.Selection(
        selection=[
            ('sale', 'Venta'),
            ('transfer', 'Transferencia'),
        ],
        string='Tipo',
        required=True,
        default='sale',
        index=True
    )

    # Métricas agregadas del día
    quantity_total = fields.Float(
        string='Cantidad Total',
        default=0.0,
        help='Suma de cantidades vendidas/transferidas en el día'
    )
    event_count = fields.Integer(
        string='Número de Eventos',
        default=0,
        help='Cantidad de eventos (ventas/transferencias) en el día'
    )

    # Timestamps para auditoría
    first_event_at = fields.Datetime(
        string='Primer Evento',
        help='Timestamp del primer evento del día'
    )
    last_event_at = fields.Datetime(
        string='Último Evento',
        help='Timestamp del último evento del día'
    )
    last_updated = fields.Datetime(
        string='Última Actualización',
        default=fields.Datetime.now
    )

    _sql_constraints = [
        ('unique_daily_stat',
         'UNIQUE(product_id, warehouse_id, date, record_type)',
         'Ya existe un registro para este producto/almacén/fecha/tipo')
    ]

    def init(self):
        """
        Crear índices y constraint para UPSERT eficiente.
        """
        # Índice compuesto para consultas de rolling stats
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_stats_daily_rolling
            ON product_sales_stats_daily (product_id, warehouse_id, date DESC)
        """)

        # Índice para filtrar por tipo de registro
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_stats_daily_type
            ON product_sales_stats_daily (record_type, date)
        """)

        # Índice para agregación por fecha
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_stats_daily_date_agg
            ON product_sales_stats_daily (date, warehouse_id)
        """)

    @api.model
    def upsert_daily_stats(self, records):
        """
        Actualiza o inserta estadísticas diarias usando UPSERT.

        Este método es llamado después de consumir un batch de la cola.
        Agrega los eventos por (product_id, warehouse_id, date, record_type)
        y hace UPSERT atómico.

        Args:
            records: Lista de diccionarios con los eventos consumidos
                     [{product_id, warehouse_id, quantity, event_date,
                       record_type, created_at}, ...]

        Returns:
            int: Número de registros actualizados/insertados
        """
        if not records:
            return 0

        # Agregar por clave única
        aggregated = {}
        for rec in records:
            key = (
                rec['product_id'],
                rec['warehouse_id'],
                rec['event_date'],
                rec.get('record_type', 'sale')
            )

            if key not in aggregated:
                aggregated[key] = {
                    'quantity': 0,
                    'count': 0,
                    'first_at': rec.get('created_at'),
                    'last_at': rec.get('created_at')
                }

            aggregated[key]['quantity'] += rec.get('quantity', 0)
            aggregated[key]['count'] += 1

            created_at = rec.get('created_at')
            if created_at:
                if not aggregated[key]['first_at'] or created_at < aggregated[key]['first_at']:
                    aggregated[key]['first_at'] = created_at
                if not aggregated[key]['last_at'] or created_at > aggregated[key]['last_at']:
                    aggregated[key]['last_at'] = created_at

        # Construir UPSERT masivo
        values = []
        params = []

        for key, data in aggregated.items():
            product_id, warehouse_id, event_date, record_type = key
            values.append("""
                (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """)
            params.extend([
                product_id,
                warehouse_id,
                event_date,
                record_type,
                data['quantity'],
                data['count'],
                data['first_at'],
                data['last_at']
            ])

        if not values:
            return 0

        query = """
            INSERT INTO product_sales_stats_daily
                (product_id, warehouse_id, date, record_type,
                 quantity_total, event_count, first_event_at, last_event_at,
                 last_updated)
            VALUES {}
            ON CONFLICT (product_id, warehouse_id, date, record_type)
            DO UPDATE SET
                quantity_total = product_sales_stats_daily.quantity_total + EXCLUDED.quantity_total,
                event_count = product_sales_stats_daily.event_count + EXCLUDED.event_count,
                first_event_at = LEAST(product_sales_stats_daily.first_event_at, EXCLUDED.first_event_at),
                last_event_at = GREATEST(product_sales_stats_daily.last_event_at, EXCLUDED.last_event_at),
                last_updated = NOW()
        """.format(', '.join(values))

        self.env.cr.execute(query, params)

        affected = len(aggregated)
        _logger.debug("UPSERT daily stats: %s registros afectados", affected)

        return affected

    @api.model
    def get_daily_totals(self, product_id, warehouse_id, date_from, date_to,
                         record_type=None):
        """
        Obtiene los totales diarios para un producto/warehouse en un rango.

        Args:
            product_id: ID del producto
            warehouse_id: ID del almacén
            date_from: Fecha inicio
            date_to: Fecha fin
            record_type: Filtrar por tipo ('sale', 'transfer') o None para todos

        Returns:
            list: Lista de diccionarios con date, quantity_total, event_count
        """
        domain = [
            ('product_id', '=', product_id),
            ('warehouse_id', '=', warehouse_id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]

        if record_type:
            domain.append(('record_type', '=', record_type))

        records = self.search(domain, order='date')

        return [{
            'date': rec.date,
            'quantity_total': rec.quantity_total,
            'event_count': rec.event_count,
            'record_type': rec.record_type
        } for rec in records]

    @api.model
    def get_aggregated_for_rolling(self, product_id, warehouse_id, date_from,
                                   date_to, record_types=None):
        """
        Obtiene datos agregados para calcular rolling stats.

        Devuelve la suma de cantidades por día, considerando los
        tipos de registro especificados.

        Args:
            product_id: ID del producto
            warehouse_id: ID del almacén
            date_from: Fecha inicio
            date_to: Fecha fin
            record_types: Lista de tipos a incluir ['sale', 'transfer']

        Returns:
            dict: {
                'total_quantity': float,
                'total_days_with_sales': int,
                'daily_quantities': [float, ...],  # Lista de cantidades por día
                'period_days': int  # Días en el período
            }
        """
        if record_types is None:
            record_types = ['sale']

        type_filter = "AND record_type = ANY(%s)" if record_types else ""

        query = f"""
            SELECT
                date,
                SUM(quantity_total) as daily_qty
            FROM product_sales_stats_daily
            WHERE product_id = %s
              AND warehouse_id = %s
              AND date >= %s
              AND date <= %s
              {type_filter}
            GROUP BY date
            ORDER BY date
        """

        params = [product_id, warehouse_id, date_from, date_to]
        if record_types:
            params.append(record_types)

        self.env.cr.execute(query, params)
        rows = self.env.cr.fetchall()

        daily_quantities = [row[1] for row in rows]
        total_quantity = sum(daily_quantities)

        # Calcular días en el período
        from datetime import datetime
        if isinstance(date_from, str):
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        if isinstance(date_to, str):
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()

        period_days = (date_to - date_from).days + 1

        return {
            'total_quantity': total_quantity,
            'total_days_with_sales': len(daily_quantities),
            'daily_quantities': daily_quantities,
            'period_days': period_days
        }

    @api.model
    def cleanup_old_daily_stats(self, days=90):
        """
        Limpia estadísticas diarias antiguas.

        Los datos muy antiguos ya no son necesarios una vez que
        rolling stats está actualizado.

        Args:
            days: Eliminar registros más antiguos que N días

        Returns:
            int: Número de registros eliminados
        """
        self.env.cr.execute("""
            DELETE FROM product_sales_stats_daily
            WHERE date < CURRENT_DATE - INTERVAL '%s days'
        """, (days,))

        deleted = self.env.cr.rowcount
        if deleted > 0:
            _logger.info(
                "Limpieza de daily stats: %s registros eliminados (> %s días)",
                deleted, days
            )

        return deleted
