# models/stock_picking.py

from odoo import api, fields, models
from odoo.fields import Command


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_print_receipt(self):
        return self.env.ref(
            'guide_remision.report_stock_picking_receipt'
        ).report_action(self)

    def button_validate(self):
        """Override para enviar notificación de actualización de stock al POS cuando se valida la transferencia"""
        # Guardar IDs de los pickings antes de validar
        pickings_to_notify = self.filtered(lambda p: p.picking_type_id.code == 'internal')

        result = super().button_validate()

        # Enviar notificación de actualización de stock para transferencias internas
        # Verificar después de la validación si el estado cambió a 'done'
        for picking in pickings_to_notify:
            # Refrescar el registro para obtener el estado actualizado
            picking.invalidate_recordset(['state'])
            if picking.state == 'done':
                self._notify_pos_stock_validated(picking)

        return result

    def _notify_pos_stock_validated(self, picking):
        """Envía notificación a los POS para actualizar el stock cuando se valida una transferencia"""
        if 'bus.bus' not in self.env:
            return

        # Obtener IDs de productos de la transferencia
        product_ids = picking.move_ids.mapped('product_id.id')

        if not product_ids:
            return

        # Obtener los warehouses de origen y destino
        source_warehouse_id = picking.location_id.warehouse_id.id if picking.location_id.warehouse_id else False
        dest_warehouse_id = picking.location_dest_id.warehouse_id.id if picking.location_dest_id.warehouse_id else False

        # Calcular el stock actualizado para cada producto
        stock_updates = self._get_validated_stock_updates(
            product_ids,
            picking.location_id.id,
            picking.location_dest_id.id
        )

        # Enviar notificación broadcast para actualizar stock en todos los POS
        self.env['bus.bus']._sendone('broadcast', 'POS_STOCK_UPDATE', {
            'message': 'Transferencia validada - Stock actualizado',
            'product_ids': product_ids,
            'source_warehouse_id': source_warehouse_id,
            'dest_warehouse_id': dest_warehouse_id,
            'transfer_validated': True,
            'stock_updates': stock_updates,
        })

    def _get_validated_stock_updates(self, product_ids, source_location_id, dest_location_id):
        """Obtiene los valores de stock actualizados después de validar una transferencia"""
        stock_updates = []

        for product_id in product_ids:
            product = self.env['product.product'].browse(product_id)

            # Stock en ubicación origen (después de la transferencia, la reserva se libera)
            source_quant = self.env['stock.quant'].sudo().search([
                ('product_id', '=', product_id),
                ('location_id', '=', source_location_id),
            ], limit=1)
            source_stock = source_quant.quantity - source_quant.reserved_quantity if source_quant else 0

            # Stock en ubicación destino (después de la transferencia, se incrementa)
            dest_quant = self.env['stock.quant'].sudo().search([
                ('product_id', '=', product_id),
                ('location_id', '=', dest_location_id),
            ], limit=1)
            dest_stock = dest_quant.quantity - dest_quant.reserved_quantity if dest_quant else 0

            # Stock pendiente por recibir en ubicación destino (ya no hay pendiente después de validar)
            pending_moves_dest = self.env['stock.move'].sudo().search([
                ('product_id', '=', product_id),
                ('location_dest_id', '=', dest_location_id),
                ('state', 'in', ['draft', 'waiting', 'confirmed', 'assigned']),
            ])
            incoming_stock_dest = sum(pending_moves_dest.mapped('product_uom_qty'))

            # Stock pendiente por recibir en ubicación origen
            pending_moves_source = self.env['stock.move'].sudo().search([
                ('product_id', '=', product_id),
                ('location_dest_id', '=', source_location_id),
                ('state', 'in', ['draft', 'waiting', 'confirmed', 'assigned']),
            ])
            incoming_stock_source = sum(pending_moves_source.mapped('product_uom_qty'))

            stock_updates.append({
                'product_id': product_id,
                'product_name': product.name,
                'source_stock': source_stock,
                'dest_stock': dest_stock,
                'incoming_stock': incoming_stock_dest,
                'incoming_stock_source': incoming_stock_source,
                'source_location_id': source_location_id,
                'dest_location_id': dest_location_id,
            })

        return stock_updates

    @api.model
    def get_transfer_config(self, config_id):
        """Obtiene la configuración del POS para las transferencias.

        Devuelve información sobre si se deben mostrar las transferencias
        automáticas y si el campo is_auto_replenishment existe en el modelo.

        :param config_id: ID de la configuración del POS
        :return dict: Diccionario con la configuración
        """
        result = {
            'show_auto_transfers': True,  # Por defecto mostrar todo
            'has_auto_replenishment_field': False,
            'filter_auto_transfers': False,
        }

        try:
            if not config_id:
                return result

            config = self.env['pos.config'].sudo().browse(config_id)

            if not config.exists():
                return result

            # Verificar si el campo is_auto_replenishment existe en stock.picking
            has_field = 'is_auto_replenishment' in self._fields
            result['has_auto_replenishment_field'] = has_field

            # Obtener la configuración de show_auto_transfers
            show_auto = getattr(config, 'show_auto_transfers', True)
            result['show_auto_transfers'] = show_auto

            # Solo filtrar si el campo existe Y la configuración indica no mostrar
            result['filter_auto_transfers'] = has_field and not show_auto

        except Exception:
            pass

        return result