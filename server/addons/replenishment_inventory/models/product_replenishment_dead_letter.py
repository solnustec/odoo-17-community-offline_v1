# -*- coding: utf-8 -*-
"""
Cola de Cartas Muertas (Dead Letter Queue) - Arquitectura de 4 Capas

Almacena eventos que fallaron después de múltiples reintentos
para análisis posterior y reprocesamiento manual.
"""

import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ProductReplenishmentDeadLetter(models.Model):
    """
    Cola de cartas muertas para eventos que no pudieron procesarse.

    Un evento llega aquí después de:
    - Exceder MAX_RETRIES intentos de procesamiento
    - Error irrecuperable (producto eliminado, warehouse inactivo, etc.)

    Características:
    - Almacena el error original para diagnóstico
    - Permite reprocesamiento manual
    - Alertas automáticas por umbral de errores
    """
    _name = 'product.replenishment.dead.letter'
    _description = 'Cola de Cartas Muertas - Reabastecimiento'
    _order = 'failed_at desc'

    # Datos del evento original
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        index=True,
        ondelete='set null'  # Mantener registro aunque se borre el producto
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        index=True,
        ondelete='set null'
    )
    quantity = fields.Float(
        string='Cantidad',
        default=0.0
    )
    event_date = fields.Date(
        string='Fecha del Evento',
        index=True
    )
    record_type = fields.Selection(
        selection=[
            ('sale', 'Venta'),
            ('transfer', 'Transferencia'),
        ],
        string='Tipo',
        default='sale'
    )
    is_legacy_system = fields.Boolean(
        string='Sistema Legado',
        default=False
    )
    source_id = fields.Integer(
        string='ID Origen',
        help='ID del registro product.warehouse.sale.summary original'
    )

    # Metadatos del fallo
    original_queue_id = fields.Integer(
        string='ID Cola Original',
        help='ID del registro en product_replenishment_queue antes de fallar'
    )
    original_created_at = fields.Datetime(
        string='Fecha Creación Original',
        help='Cuándo se creó el evento originalmente'
    )
    failed_at = fields.Datetime(
        string='Fecha de Fallo',
        default=fields.Datetime.now,
        required=True,
        index=True
    )
    retry_count = fields.Integer(
        string='Intentos Realizados',
        default=0
    )
    error_message = fields.Text(
        string='Mensaje de Error',
        help='Último error que causó el fallo'
    )
    error_traceback = fields.Text(
        string='Traceback',
        help='Stack trace completo del error'
    )
    error_type = fields.Selection(
        selection=[
            ('max_retries', 'Máximo de Reintentos'),
            ('product_deleted', 'Producto Eliminado'),
            ('warehouse_inactive', 'Almacén Inactivo'),
            ('validation_error', 'Error de Validación'),
            ('database_error', 'Error de Base de Datos'),
            ('unknown', 'Desconocido'),
        ],
        string='Tipo de Error',
        default='unknown',
        index=True
    )

    # Estado de reprocesamiento
    state = fields.Selection(
        selection=[
            ('pending', 'Pendiente'),
            ('reprocessing', 'Reprocesando'),
            ('resolved', 'Resuelto'),
            ('discarded', 'Descartado'),
        ],
        string='Estado',
        default='pending',
        index=True
    )
    resolved_at = fields.Datetime(
        string='Fecha Resolución'
    )
    resolved_by = fields.Many2one(
        'res.users',
        string='Resuelto Por'
    )
    resolution_notes = fields.Text(
        string='Notas de Resolución'
    )

    def init(self):
        """
        Crear índices para la cola de cartas muertas.
        """
        # Índice para buscar pendientes por tipo de error
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_dead_letter_pending_type
            ON product_replenishment_dead_letter (error_type, failed_at)
            WHERE state = 'pending'
        """)

        # Índice para análisis por producto
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_dead_letter_product
            ON product_replenishment_dead_letter (product_id, failed_at)
        """)

    @api.model
    def send_to_dead_letter(self, queue_record, error_message, error_traceback=None,
                            error_type='unknown'):
        """
        Envía un registro de la cola principal a la cola de cartas muertas.

        Args:
            queue_record: dict con los datos del registro de la cola
            error_message: Mensaje de error
            error_traceback: Stack trace completo (opcional)
            error_type: Tipo de error para clasificación

        Returns:
            record: El registro creado en dead letter
        """
        values = {
            'product_id': queue_record.get('product_id'),
            'warehouse_id': queue_record.get('warehouse_id'),
            'quantity': queue_record.get('quantity', 0),
            'event_date': queue_record.get('event_date'),
            'record_type': queue_record.get('record_type', 'sale'),
            'is_legacy_system': queue_record.get('is_legacy_system', False),
            'source_id': queue_record.get('source_id'),
            'original_queue_id': queue_record.get('id'),
            'original_created_at': queue_record.get('created_at'),
            'retry_count': queue_record.get('retry_count', 0),
            'error_message': error_message[:4000] if error_message else None,
            'error_traceback': error_traceback[:10000] if error_traceback else None,
            'error_type': error_type,
            'state': 'pending',
        }

        record = self.create(values)

        _logger.error(
            "Evento enviado a dead letter: product=%s, warehouse=%s, error=%s",
            queue_record.get('product_id'),
            queue_record.get('warehouse_id'),
            error_type
        )

        return record

    @api.model
    def get_dead_letter_stats(self):
        """
        Obtiene estadísticas de la cola de cartas muertas.

        Returns:
            dict: Estadísticas por tipo de error y estado
        """
        self.env.cr.execute("""
            SELECT
                error_type,
                state,
                COUNT(*) as count,
                MIN(failed_at) as oldest,
                MAX(failed_at) as newest
            FROM product_replenishment_dead_letter
            GROUP BY error_type, state
            ORDER BY count DESC
        """)
        rows = self.env.cr.fetchall()

        stats = {
            'by_type': {},
            'by_state': {},
            'total_pending': 0,
            'total': 0
        }

        for row in rows:
            error_type, state, count, oldest, newest = row

            if error_type not in stats['by_type']:
                stats['by_type'][error_type] = {'total': 0, 'by_state': {}}
            stats['by_type'][error_type]['total'] += count
            stats['by_type'][error_type]['by_state'][state] = count

            if state not in stats['by_state']:
                stats['by_state'][state] = 0
            stats['by_state'][state] += count

            stats['total'] += count
            if state == 'pending':
                stats['total_pending'] += count

        return stats

    def action_reprocess(self):
        """
        Intenta reprocesar los registros seleccionados.
        """
        Queue = self.env['product.replenishment.queue']

        for record in self.filtered(lambda r: r.state == 'pending'):
            # Marcar como reprocesando
            record.state = 'reprocessing'

            # Volver a encolar
            Queue.enqueue_event(
                product_id=record.product_id.id if record.product_id else None,
                warehouse_id=record.warehouse_id.id if record.warehouse_id else None,
                quantity=record.quantity,
                event_date=record.event_date,
                record_type=record.record_type,
                is_legacy_system=record.is_legacy_system,
                source_id=record.source_id
            )

            _logger.info(
                "Evento reencolado desde dead letter: id=%s, product=%s",
                record.id,
                record.product_id.id if record.product_id else 'N/A'
            )

        return True

    def action_discard(self):
        """
        Marca los registros seleccionados como descartados.
        """
        self.write({
            'state': 'discarded',
            'resolved_at': fields.Datetime.now(),
            'resolved_by': self.env.uid,
        })
        return True

    def action_mark_resolved(self):
        """
        Marca los registros como resueltos manualmente.
        """
        self.write({
            'state': 'resolved',
            'resolved_at': fields.Datetime.now(),
            'resolved_by': self.env.uid,
        })
        return True

    @api.model
    def cleanup_old_resolved(self, days=90):
        """
        Limpia registros resueltos/descartados antiguos.

        Args:
            days: Eliminar registros resueltos hace más de N días

        Returns:
            int: Número de registros eliminados
        """
        self.env.cr.execute("""
            DELETE FROM product_replenishment_dead_letter
            WHERE state IN ('resolved', 'discarded')
              AND resolved_at < NOW() - INTERVAL '%s days'
        """, (days,))

        deleted = self.env.cr.rowcount
        if deleted > 0:
            _logger.info(
                "Limpieza de dead letter: %s registros eliminados (> %s días)",
                deleted, days
            )

        return deleted
