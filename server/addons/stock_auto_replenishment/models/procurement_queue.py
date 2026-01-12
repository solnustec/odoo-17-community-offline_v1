# -*- coding: utf-8 -*-
"""
Cola de Ejecución de Procurements.

Este modelo implementa una cola de trabajo para ejecutar procurements
de forma controlada, evitando duplicados y soportando concurrencia.
"""
import logging
from datetime import date
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProcurementQueue(models.Model):
    """
    Cola de procurements pendientes de ejecución.

    Cada registro representa un orderpoint que necesita ejecutar
    su procurement (crear transferencia/compra).
    """
    _name = 'product.replenishment.procurement.queue'
    _description = 'Cola de Ejecución de Procurements'
    _order = 'create_date'

    orderpoint_id = fields.Many2one(
        'stock.warehouse.orderpoint',
        string='Regla de Reorden',
        required=True,
        ondelete='cascade',
        index=True,
    )
    qty_to_order_snapshot = fields.Float(
        string='Cantidad a Ordenar',
        required=True,
        digits='Product Unit of Measure',
        help='Cantidad capturada al momento de encolar',
    )
    dedupe_key = fields.Char(
        string='Clave de Deduplicación',
        required=True,
        index=True,
        help='Clave única para evitar duplicados: OP:{id}-Q:{qty}-D:{date}',
    )
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('done', 'Procesado'),
        ('failed', 'Fallido'),
    ], string='Estado', default='pending', required=True, index=True)
    retry_count = fields.Integer(
        string='Reintentos',
        default=0,
    )
    last_error = fields.Text(
        string='Último Error',
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Transferencia Creada',
        ondelete='set null',
    )

    _sql_constraints = [
        ('dedupe_key_unique', 'UNIQUE(dedupe_key)',
         'Ya existe un registro en cola para este orderpoint/cantidad/fecha'),
    ]

    @api.model
    def _generate_dedupe_key(self, orderpoint_id, qty_to_order):
        """
        Genera la clave de deduplicación.

        Formato: OP:{orderpoint_id}-Q:{qty_rounded}-D:{YYYYMMDD}

        La cantidad se redondea a 2 decimales para evitar diferencias
        por precisión de flotantes.
        """
        qty_rounded = round(qty_to_order, 2)
        today = date.today().strftime('%Y%m%d')
        return f"OP:{orderpoint_id}-Q:{qty_rounded}-D:{today}"

    @api.model
    def enqueue_orderpoints(self, orderpoint_ids):
        """
        Encola orderpoints para ejecución.

        Solo encola los que cumplen:
        - trigger = 'auto'
        - qty_to_order > 0
        - active = True
        - No tienen dedupe_key existente (evita duplicados)

        Args:
            orderpoint_ids: lista de IDs de orderpoints a encolar

        Returns:
            int: Número de orderpoints encolados
        """
        if not orderpoint_ids:
            return 0

        Orderpoint = self.env['stock.warehouse.orderpoint']

        # Filtrar orderpoints válidos
        orderpoints = Orderpoint.browse(orderpoint_ids).filtered(
            lambda op: op.trigger == 'auto'
                       and op.qty_to_order > 0
                       and op.active
        )

        if not orderpoints:
            return 0

        enqueued = 0
        for op in orderpoints:
            dedupe_key = self._generate_dedupe_key(op.id, op.qty_to_order)

            # Verificar si ya existe
            existing = self.search_count([('dedupe_key', '=', dedupe_key)])
            if existing:
                continue

            try:
                self.create({
                    'orderpoint_id': op.id,
                    'qty_to_order_snapshot': op.qty_to_order,
                    'dedupe_key': dedupe_key,
                    'state': 'pending',
                })
                enqueued += 1
            except Exception as e:
                # Si falla por constraint unique, ignorar (ya existe)
                if 'dedupe_key_unique' in str(e):
                    continue
                _logger.warning("Error encolando orderpoint %s: %s", op.id, e)

        if enqueued:
            _logger.info("Encolados %s orderpoints para procurement", enqueued)

        return enqueued

    @api.model
    def enqueue_single(self, orderpoint):
        """
        Encola un solo orderpoint (usado por botón "Forzar").

        Args:
            orderpoint: registro stock.warehouse.orderpoint

        Returns:
            bool: True si se encoló, False si ya existía o no cumple criterios
        """
        if not orderpoint or orderpoint.qty_to_order <= 0:
            return False

        dedupe_key = self._generate_dedupe_key(orderpoint.id, orderpoint.qty_to_order)

        existing = self.search_count([('dedupe_key', '=', dedupe_key)])
        if existing:
            return False

        try:
            self.create({
                'orderpoint_id': orderpoint.id,
                'qty_to_order_snapshot': orderpoint.qty_to_order,
                'dedupe_key': dedupe_key,
                'state': 'pending',
            })
            return True
        except Exception:
            return False

    @api.model
    def get_pending_batch(self, batch_size=100):
        """
        Obtiene un batch de registros pendientes con lock.

        Usa FOR UPDATE SKIP LOCKED para evitar contención entre workers.

        Args:
            batch_size: Número máximo de registros a obtener

        Returns:
            recordset de registros bloqueados para procesamiento
        """
        # Usar SQL directo para FOR UPDATE SKIP LOCKED
        self.env.cr.execute("""
            SELECT id FROM product_replenishment_procurement_queue
            WHERE state = 'pending'
            ORDER BY create_date
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        """, (batch_size,))

        ids = [row[0] for row in self.env.cr.fetchall()]
        return self.browse(ids)

    def mark_done(self, picking=None):
        """Marca el registro como procesado."""
        vals = {'state': 'done', 'last_error': False}
        if picking:
            vals['picking_id'] = picking.id
        self.write(vals)

    def mark_failed(self, error_message):
        """Marca el registro como fallido."""
        self.write({
            'state': 'failed',
            'retry_count': self.retry_count + 1,
            'last_error': error_message,
        })

    def reset_for_retry(self):
        """Resetea registros fallidos para reintento."""
        self.write({
            'state': 'pending',
            'last_error': False,
        })

    @api.model
    def cleanup_old_records(self, days=7):
        """
        Limpia registros antiguos procesados o fallidos.

        Args:
            days: Días de antigüedad para eliminar

        Returns:
            int: Número de registros eliminados
        """
        from datetime import timedelta
        cutoff = fields.Datetime.now() - timedelta(days=days)

        old_records = self.search([
            ('state', 'in', ['done', 'failed']),
            ('create_date', '<', cutoff),
        ])
        count = len(old_records)
        old_records.unlink()

        if count:
            _logger.info("Eliminados %s registros antiguos de la cola", count)

        return count

    @api.model
    def get_queue_stats(self):
        """Obtiene estadísticas de la cola."""
        self.env.cr.execute("""
            SELECT state, COUNT(*)
            FROM product_replenishment_procurement_queue
            GROUP BY state
        """)
        stats = dict(self.env.cr.fetchall())
        return {
            'pending': stats.get('pending', 0),
            'done': stats.get('done', 0),
            'failed': stats.get('failed', 0),
            'total': sum(stats.values()),
        }
