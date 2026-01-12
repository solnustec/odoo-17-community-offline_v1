# -*- coding: utf-8 -*-
"""
Hook de integración con replenishment_inventory.

Extiende el QueueProcessor para encolar orderpoints después de que
son actualizados/creados por el procesador de replenishment_inventory.
"""
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class QueueProcessorHook(models.AbstractModel):
    """
    Extiende el procesador de cola de replenishment_inventory.

    Después de que _update_orderpoints_batch actualiza los orderpoints,
    encola los que tienen trigger='auto' y qty_to_order > 0.
    """
    _inherit = 'replenishment.queue.processor'

    def _update_orderpoints_batch(self, product_warehouse_pairs):
        """
        Extiende el método para encolar orderpoints después de actualizar.

        Después de que el método base actualiza/crea orderpoints,
        buscamos los que quedaron con trigger='auto' y qty_to_order > 0
        y los encolamos para ejecución.
        """
        # Llamar al método original
        result = super()._update_orderpoints_batch(product_warehouse_pairs)

        # Verificar si el módulo está habilitado
        ICP = self.env['ir.config_parameter'].sudo()
        enabled = ICP.get_param(
            'stock_auto_replenishment.enabled', 'False'
        ) == 'True'

        if not enabled:
            return result

        # Encolar orderpoints que necesitan procurement
        try:
            self._enqueue_orderpoints_for_procurement(product_warehouse_pairs)
        except Exception as e:
            _logger.warning(
                "Error encolando orderpoints para procurement: %s", e
            )

        return result

    def _enqueue_orderpoints_for_procurement(self, product_warehouse_pairs):
        """
        Encola orderpoints que necesitan procurement.

        Busca los orderpoints para los pares producto/warehouse que
        cumplan:
        - trigger = 'auto'
        - qty_to_order > 0
        - active = True
        """
        if not product_warehouse_pairs:
            return 0

        Orderpoint = self.env['stock.warehouse.orderpoint']
        Queue = self.env['product.replenishment.procurement.queue']

        # Obtener los warehouse_ids de los pares
        warehouse_ids = list(set(p[1] for p in product_warehouse_pairs))
        product_ids = list(set(p[0] for p in product_warehouse_pairs))

        # Buscar orderpoints que necesitan encolarse
        orderpoints = Orderpoint.search([
            ('product_id', 'in', product_ids),
            ('warehouse_id', 'in', warehouse_ids),
            ('trigger', '=', 'auto'),
            ('qty_to_order', '>', 0),
            ('active', '=', True),
        ])

        if not orderpoints:
            return 0

        # Encolar
        enqueued = Queue.enqueue_orderpoints(orderpoints.ids)

        if enqueued:
            _logger.info(
                "Encolados %s orderpoints para procurement automático",
                enqueued
            )

        return enqueued
