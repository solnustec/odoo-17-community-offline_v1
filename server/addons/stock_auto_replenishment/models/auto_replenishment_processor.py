# -*- coding: utf-8 -*-
"""
Procesador de Cola de Procurements.

Este módulo consume la cola de procurements y ejecuta las transferencias
de forma controlada, respetando modos individual/agrupado.
"""
import logging
import time
import traceback
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class AutoReplenishmentProcessor(models.AbstractModel):
    """
    Procesador de la cola de procurements.

    Consume registros de product.replenishment.procurement.queue
    y ejecuta los procurements según el modo configurado.
    """
    _name = 'auto.replenishment.processor'
    _description = 'Procesador de Reabastecimiento Automático'

    @api.model
    def _get_settings(self):
        """Obtiene la configuración del módulo."""
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'enabled': ICP.get_param(
                'stock_auto_replenishment.enabled', 'False') == 'True',
            'mode': ICP.get_param(
                'stock_auto_replenishment.mode', 'individual'),
            'batch_limit': int(ICP.get_param(
                'stock_auto_replenishment.batch_limit', '100')),
            'check_stock': ICP.get_param(
                'stock_auto_replenishment.check_stock', 'True') == 'True',
            'auto_confirm': ICP.get_param(
                'stock_auto_replenishment.auto_confirm', 'True') == 'True',
        }

    @api.model
    def process_queue(self, batch_size=None, time_limit=55):
        """
        Procesa la cola de procurements.

        Args:
            batch_size: Tamaño del batch (default desde settings)
            time_limit: Tiempo máximo en segundos

        Returns:
            dict: Estadísticas de procesamiento
        """
        settings = self._get_settings()

        if not settings['enabled']:
            _logger.info("Procesador de reabastecimiento deshabilitado")
            return {'skipped': True, 'reason': 'disabled'}

        if batch_size is None:
            batch_size = settings['batch_limit']

        start_time = time.time()
        Queue = self.env['product.replenishment.procurement.queue']

        stats = {
            'processed': 0,
            'pickings_created': 0,
            'skipped': 0,
            'failed': 0,
            'time_elapsed': 0,
        }

        _logger.info(
            "Iniciando procesamiento de cola [batch_size=%s, time_limit=%ss, mode=%s]",
            batch_size, time_limit, settings['mode']
        )

        while True:
            elapsed = time.time() - start_time
            if elapsed >= time_limit:
                _logger.info("Tiempo límite alcanzado")
                break

            # Obtener batch con lock
            queue_items = Queue.get_pending_batch(batch_size=batch_size)
            if not queue_items:
                _logger.info("Cola vacía")
                break

            for item in queue_items:
                try:
                    result = self._process_queue_item(item, settings)

                    if result.get('created'):
                        stats['pickings_created'] += 1
                    elif result.get('skipped'):
                        stats['skipped'] += 1

                    stats['processed'] += 1

                except Exception as e:
                    _logger.error(
                        "Error procesando item %s: %s\n%s",
                        item.id, e, traceback.format_exc()
                    )
                    item.mark_failed(str(e))
                    stats['failed'] += 1

            # Commit después de cada batch
            self.env.cr.commit()

        stats['time_elapsed'] = time.time() - start_time

        _logger.info(
            "Procesamiento completado: %s procesados, %s pickings, %s omitidos, %s fallidos, %.2fs",
            stats['processed'], stats['pickings_created'],
            stats['skipped'], stats['failed'], stats['time_elapsed']
        )

        return stats

    def _process_queue_item(self, queue_item, settings):
        """
        Procesa un item de la cola.

        Args:
            queue_item: registro product.replenishment.procurement.queue
            settings: dict con configuración

        Returns:
            dict: {created: bool, skipped: bool, picking_id: int}
        """
        orderpoint = queue_item.orderpoint_id

        # Revalidar: orderpoint existe y sigue activo
        if not orderpoint.exists():
            queue_item.mark_done()
            return {'skipped': True, 'reason': 'orderpoint_deleted'}

        # Revalidar: sigue en auto y con qty_to_order > 0
        if orderpoint.trigger != 'auto' or orderpoint.qty_to_order <= 0:
            queue_item.mark_done()
            return {'skipped': True, 'reason': 'no_longer_needs_replenishment'}

        # Verificar si ya existe picking pendiente
        if self._has_pending_picking(orderpoint):
            queue_item.mark_done()
            return {'skipped': True, 'reason': 'pending_picking_exists'}

        # Ejecutar según modo
        if settings['mode'] == 'individual':
            result = self._execute_individual(orderpoint, settings)
        else:
            result = self._execute_grouped(orderpoint, settings)

        if result.get('picking'):
            queue_item.mark_done(picking=result['picking'])
            return {'created': True, 'picking_id': result['picking'].id}
        elif result.get('error'):
            if queue_item.retry_count >= MAX_RETRIES:
                queue_item.mark_failed(result['error'])
            else:
                queue_item.mark_failed(result['error'])
            return {'skipped': True, 'reason': result['error']}
        else:
            queue_item.mark_done()
            return {'skipped': True, 'reason': 'no_action_taken'}

    def _has_pending_picking(self, orderpoint):
        """Verifica si ya existe un picking pendiente para este orderpoint."""
        return self.env['stock.picking'].search_count([
            ('is_auto_replenishment', '=', True),
            ('auto_replenishment_orderpoint_id', '=', orderpoint.id),
            ('state', 'not in', ['done', 'cancel']),
        ]) > 0

    def _execute_individual(self, orderpoint, settings):
        """
        Ejecuta procurement en modo individual.

        Crea un picking directo sin usar el mecanismo estándar de Odoo.
        """
        # Obtener ubicación origen
        source_location = self._get_source_location(orderpoint)
        if not source_location:
            return {'error': 'No source warehouse configured'}

        # Verificar stock si está configurado
        if settings['check_stock']:
            available = self._get_available_stock(
                orderpoint.product_id, source_location
            )
            if available <= 0:
                return {'error': 'No stock available in source'}

        # Crear picking
        try:
            picking = self._create_picking(orderpoint, source_location, settings)
            return {'picking': picking}
        except Exception as e:
            return {'error': str(e)}

    def _execute_grouped(self, orderpoint, settings):
        """
        Ejecuta procurement en modo agrupado (estándar Odoo).

        Usa _procure_orderpoint_confirm que agrupa por procurement.group.
        """
        try:
            # Asegurar que tiene group_id para agrupar
            # El comportamiento estándar de Odoo agrupa por group_id
            orderpoint._procure_orderpoint_confirm(
                company_id=orderpoint.company_id
            )

            # Buscar picking creado
            picking = self.env['stock.picking'].search([
                ('origin', 'ilike', orderpoint.name),
                ('state', '!=', 'cancel'),
            ], limit=1, order='create_date desc')

            if picking:
                # Marcar como auto-replenishment
                picking.write({
                    'is_auto_replenishment': True,
                    'auto_replenishment_orderpoint_id': orderpoint.id,
                })
                return {'picking': picking}

            return {'error': 'No picking created by standard flow'}

        except Exception as e:
            return {'error': str(e)}

    def _get_source_location(self, orderpoint):
        """Obtiene la ubicación origen para la transferencia."""
        warehouse = orderpoint.warehouse_id

        # 1. Verificar configuración específica del warehouse
        source_warehouse = getattr(
            warehouse, 'auto_replenishment_source_warehouse_id', False
        )
        if source_warehouse:
            return source_warehouse.lot_stock_id

        # 2. Buscar almacén principal
        main_warehouse = self.env['stock.warehouse'].search([
            ('is_main_warehouse', '=', True),
            ('company_id', '=', warehouse.company_id.id),
        ], limit=1)

        if main_warehouse and main_warehouse.id != warehouse.id:
            return main_warehouse.lot_stock_id

        return False

    def _get_available_stock(self, product, location):
        """Obtiene el stock disponible."""
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ])
        return sum(quants.mapped('available_quantity'))

    def _create_picking(self, orderpoint, source_location, settings):
        """Crea el picking individual."""
        product = orderpoint.product_id
        dest_location = orderpoint.location_id
        qty_to_order = orderpoint.qty_to_order

        picking_type = self._get_internal_picking_type(
            source_location.warehouse_id
        )

        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'origin': f'AUTO/{orderpoint.name}',
            'scheduled_date': fields.Datetime.now(),
            'company_id': orderpoint.company_id.id,
            'is_auto_replenishment': True,
            'auto_replenishment_orderpoint_id': orderpoint.id,
            'move_ids': [(0, 0, {
                'name': product.display_name,
                'product_id': product.id,
                'product_uom_qty': qty_to_order,
                'product_uom': product.uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
            })],
        }

        picking = self.env['stock.picking'].create(picking_vals)

        if settings['auto_confirm']:
            picking.action_confirm()
            picking.action_assign()

        _logger.info(
            "Picking %s creado para %s (qty=%s)",
            picking.name, orderpoint.name, qty_to_order
        )

        return picking

    def _get_internal_picking_type(self, source_warehouse):
        """Obtiene el picking type para transferencia interna."""
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', source_warehouse.id),
        ], limit=1)

        if not picking_type:
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('company_id', '=', source_warehouse.company_id.id),
            ], limit=1)

        if not picking_type:
            raise ValueError(
                f"No internal picking type for {source_warehouse.name}"
            )

        return picking_type

    @api.model
    def cron_process_queue(self):
        """Método llamado por el cron."""
        _logger.info("Ejecutando cron de procesamiento de cola")
        return self.process_queue()

    @api.model
    def cron_cleanup_queue(self):
        """Limpia registros antiguos de la cola y cancela transferencias expiradas."""
        Queue = self.env['product.replenishment.procurement.queue']

        # 1. Limpiar registros antiguos de la cola
        deleted = Queue.cleanup_old_records(days=7)
        _logger.info("Limpieza de cola: %s registros eliminados", deleted)

        # 2. Cancelar transferencias expiradas
        cancelled = self._cancel_expired_transfers()

        return {'queue_deleted': deleted, 'pickings_cancelled': cancelled}

    @api.model
    def _cancel_expired_transfers(self):
        """
        Cancela transferencias automáticas que no han sido validadas
        después de X días configurados.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        expiration_days = int(ICP.get_param(
            'stock_auto_replenishment.expiration_days', '5'
        ))

        if expiration_days <= 0:
            _logger.info("Cancelación de transferencias expiradas desactivada")
            return 0

        # Calcular fecha límite
        from datetime import timedelta
        cutoff_date = fields.Datetime.now() - timedelta(days=expiration_days)

        # Buscar transferencias automáticas no validadas creadas antes de la fecha límite
        expired_pickings = self.env['stock.picking'].search([
            ('is_auto_replenishment', '=', True),
            ('state', 'not in', ['done', 'cancel']),
            ('create_date', '<', cutoff_date),
        ])

        cancelled_count = 0
        for picking in expired_pickings:
            try:
                picking.action_cancel()
                _logger.info(
                    "Transferencia %s cancelada por expiración (%s días sin validar)",
                    picking.name, expiration_days
                )
                cancelled_count += 1
            except Exception as e:
                _logger.error(
                    "Error cancelando transferencia expirada %s: %s",
                    picking.name, e
                )

        if cancelled_count > 0:
            _logger.info(
                "Canceladas %s transferencias expiradas (>%s días)",
                cancelled_count, expiration_days
            )

        return cancelled_count
