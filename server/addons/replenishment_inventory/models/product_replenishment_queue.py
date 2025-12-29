# -*- coding: utf-8 -*-
"""
Cola de Reabastecimiento - Arquitectura de 4 Capas

Este módulo implementa una cola de procesamiento eficiente para el sistema
de reabastecimiento de alto volumen (2M+ registros).

Patrón: DELETE...RETURNING para consumo atómico sin locks
"""

import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ProductReplenishmentQueue(models.Model):
    """
    Cola de eventos de venta/transferencia pendientes de procesar.

    Características:
    - Inserción O(1) desde create() de product.warehouse.sale.summary
    - Consumo atómico con DELETE...RETURNING (sin FOR UPDATE locks)
    - Índice parcial en created_at para FIFO eficiente
    - Backpressure basado en edad del registro más antiguo
    """
    _name = 'product.replenishment.queue'
    _description = 'Cola de Reabastecimiento'
    _order = 'created_at'
    _log_access = False  # Deshabilitar write_date/create_uid para rendimiento

    # Campos de la cola
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
    quantity = fields.Float(
        string='Cantidad',
        required=True,
        default=0.0
    )
    event_date = fields.Date(
        string='Fecha del Evento',
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
    is_legacy_system = fields.Boolean(
        string='Sistema Legado',
        default=False,
        index=True
    )
    source_id = fields.Integer(
        string='ID Origen',
        help='ID del registro product.warehouse.sale.summary original'
    )
    created_at = fields.Datetime(
        string='Fecha Creación',
        default=fields.Datetime.now,
        required=True,
        index=True
    )
    retry_count = fields.Integer(
        string='Intentos',
        default=0
    )

    def init(self):
        """
        Crear índices optimizados para la cola.
        """
        # Índice parcial FIFO para consumo eficiente
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_replenishment_queue_fifo
            ON product_replenishment_queue (created_at)
            WHERE id IS NOT NULL
        """)

        # Índice compuesto para agregación por producto/warehouse
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_replenishment_queue_agg
            ON product_replenishment_queue (product_id, warehouse_id, event_date)
        """)

        # Índice para backpressure (obtener el más antiguo)
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_replenishment_queue_oldest
            ON product_replenishment_queue (created_at ASC)
        """)

    @api.model
    def consume_batch(self, batch_size=1000):
        """
        Consume un lote de registros usando DELETE...RETURNING.

        Este patrón es más eficiente que SELECT FOR UPDATE porque:
        - No requiere locks (DELETE es atómico)
        - No hay contención entre workers
        - Escala linealmente con múltiples consumidores

        Args:
            batch_size: Número máximo de registros a consumir

        Returns:
            list: Lista de diccionarios con los registros consumidos
        """
        query = """
            DELETE FROM product_replenishment_queue
            WHERE id IN (
                SELECT id
                FROM product_replenishment_queue
                ORDER BY created_at
                LIMIT %s
            )
            RETURNING id, product_id, warehouse_id, quantity,
                      event_date, record_type, is_legacy_system,
                      source_id, created_at, retry_count
        """
        self.env.cr.execute(query, (batch_size,))
        rows = self.env.cr.fetchall()

        if not rows:
            return []

        columns = [
            'id', 'product_id', 'warehouse_id', 'quantity',
            'event_date', 'record_type', 'is_legacy_system',
            'source_id', 'created_at', 'retry_count'
        ]

        return [dict(zip(columns, row)) for row in rows]

    @api.model
    def get_queue_stats(self):
        """
        Obtiene estadísticas de la cola para monitoreo y backpressure.

        Returns:
            dict: {
                'total_count': int,
                'oldest_age_seconds': float,
                'avg_age_seconds': float,
                'by_warehouse': {warehouse_id: count}
            }
        """
        # Nota: AVG() no funciona directamente con timestamps en PostgreSQL
        # Se debe convertir a epoch primero, promediar, y luego calcular la diferencia
        self.env.cr.execute("""
            SELECT
                COUNT(*) as total,
                EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) as oldest_age,
                EXTRACT(EPOCH FROM NOW()) - AVG(EXTRACT(EPOCH FROM created_at)) as avg_age
            FROM product_replenishment_queue
        """)
        row = self.env.cr.fetchone()

        stats = {
            'total_count': row[0] or 0,
            'oldest_age_seconds': row[1] or 0,
            'avg_age_seconds': row[2] or 0,
            'by_warehouse': {}
        }

        if stats['total_count'] > 0:
            self.env.cr.execute("""
                SELECT warehouse_id, COUNT(*)
                FROM product_replenishment_queue
                GROUP BY warehouse_id
            """)
            stats['by_warehouse'] = dict(self.env.cr.fetchall())

        return stats

    @api.model
    def check_backpressure(self, max_age_seconds=300, max_queue_size=50000):
        """
        Verifica si hay backpressure en la cola.

        Backpressure indica que el consumo no puede mantener el ritmo
        de producción y se deben tomar medidas (pausar inserciones,
        escalar workers, etc.)

        Args:
            max_age_seconds: Edad máxima permitida del registro más antiguo
            max_queue_size: Tamaño máximo permitido de la cola

        Returns:
            dict: {
                'has_backpressure': bool,
                'reason': str or None,
                'stats': dict
            }
        """
        stats = self.get_queue_stats()

        has_backpressure = False
        reason = None

        if stats['oldest_age_seconds'] > max_age_seconds:
            has_backpressure = True
            reason = f"Registro más antiguo tiene {stats['oldest_age_seconds']:.0f}s (max: {max_age_seconds}s)"
        elif stats['total_count'] > max_queue_size:
            has_backpressure = True
            reason = f"Cola tiene {stats['total_count']} registros (max: {max_queue_size})"

        return {
            'has_backpressure': has_backpressure,
            'reason': reason,
            'stats': stats
        }

    @api.model
    def enqueue_event(self, product_id, warehouse_id, quantity, event_date,
                      record_type='sale', is_legacy_system=False, source_id=None):
        """
        Encola un evento de venta/transferencia.

        Este método es llamado desde el hook create() de
        product.warehouse.sale.summary para inserción dual.

        Args:
            product_id: ID del producto
            warehouse_id: ID del almacén
            quantity: Cantidad vendida/transferida
            event_date: Fecha del evento
            record_type: 'sale' o 'transfer'
            is_legacy_system: Si viene del sistema legado
            source_id: ID del registro original en sale.summary

        Returns:
            bool: True si se encoló correctamente
        """
        # Verificar backpressure antes de encolar
        bp = self.check_backpressure()
        if bp['has_backpressure']:
            _logger.warning(
                "Backpressure detectado en cola de reabastecimiento: %s",
                bp['reason']
            )
            # Por ahora solo logueamos, pero podríamos:
            # - Rechazar la inserción
            # - Usar una cola secundaria
            # - Activar modo degradado

        # Inserción directa con SQL para máximo rendimiento
        self.env.cr.execute("""
            INSERT INTO product_replenishment_queue
                (product_id, warehouse_id, quantity, event_date,
                 record_type, is_legacy_system, source_id, created_at, retry_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), 0)
        """, (
            product_id, warehouse_id, quantity, event_date,
            record_type, is_legacy_system, source_id
        ))

        return True

    @api.model
    def enqueue_batch(self, events):
        """
        Encola múltiples eventos en una sola operación.

        Más eficiente que llamar enqueue_event() múltiples veces.

        Args:
            events: Lista de diccionarios con los campos del evento

        Returns:
            int: Número de eventos encolados
        """
        if not events:
            return 0

        # Construir INSERT masivo
        values = []
        params = []
        for evt in events:
            values.append("(%s, %s, %s, %s, %s, %s, %s, NOW(), 0)")
            params.extend([
                evt['product_id'],
                evt['warehouse_id'],
                evt['quantity'],
                evt['event_date'],
                evt.get('record_type', 'sale'),
                evt.get('is_legacy_system', False),
                evt.get('source_id')
            ])

        query = """
            INSERT INTO product_replenishment_queue
                (product_id, warehouse_id, quantity, event_date,
                 record_type, is_legacy_system, source_id, created_at, retry_count)
            VALUES {}
        """.format(', '.join(values))

        self.env.cr.execute(query, params)

        return len(events)
