# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Ranjith R(odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.

###############################################################################
from odoo import api, fields, models
from odoo.fields import Command


class PosConfig(models.Model):
    """Inherited model for adding new field to configuration settings
                that allows to transfer stock from pos session"""
    _inherit = 'pos.config'

    stock_transfer = fields.Boolean(string="Enable Stock Transfer",
                                    help="Enable if you want to transfer "
                                         "stock from PoS session")

    @api.model
    def get_stock_transfer_list(self):
        """To get selection field values of stock transfer popup

            :return dict: returns list of dictionary with stock picking types,
            stock location, and stock warehouse.
        """
        main = {}
        main['picking_type'] = self.env['stock.picking.type'].search_read(
            [('company_id', '=', self.env.user.company_id.id)],
            ['display_name', 'code'])
        # main['location'] = self.env['stock.location'].search_read([
        #     ('usage', '=', 'internal'),
        #     ('company_id', '=', self.env.user.company_id.id)], [
        #     'warehouse_id.name'])
        locations = self.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', '=', self.env.user.company_id.id)])

        main['location'] = [{
            'id': loc.id,
            'name': loc.name,
            'warehouse_name': loc.warehouse_id.name if loc.warehouse_id else False
        } for loc in locations]

        # Opción 2: Obtener solo el PRIMER warehouse
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.user.company_id.id)
        ], limit=1)

        main['wh_stock'] = warehouse.lot_stock_id.id if warehouse else False

        return main

    @api.model
    def create_transfer(self, source_id, dest_id, type_transfer, note, line):
        """ Create a stock transfer based on the popup value

            :param pick_id(string): id of stock picking type
            :param source_id(string): id of source stock location
            :param dest_id(string): id of destination stock location
            :param state(string): state of stock picking
            :param line(dictionary): dictionary values with product ids and  quantity

            :return dict: returns dictionary of values with created stock transfer
                id and name
        """
        stock_location = self.env['stock.location'].sudo().search([
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', source_id),
            ('replenish_location', '=', True),
            ('company_id', '=', self.env.user.company_id.id),
        ], limit=1)

        stock_location_dest_id = self.env['stock.location'].sudo().search([
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', dest_id),
            ('replenish_location', '=', True),
            ('company_id', '=', self.env.user.company_id.id),
        ], limit=1)

        stock_picking_type = self.env['stock.picking.type'].sudo().search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', source_id)
        ], limit=1)

        transfer = self.env['stock.picking'].sudo().create({
            'picking_type_id': int(stock_picking_type.id),
            'location_id': int(stock_location.id),
            'location_dest_id': int(stock_location_dest_id.id),
            'type_transfer': str(type_transfer),
            'state': 'draft',
            'note': note,
            'move_ids': [Command.create({
                'product_id': line['pro_id'][rec],
                'product_uom_qty': line['qty'][rec],
                'location_id': int(stock_location.id),
                'location_dest_id': int(stock_location_dest_id.id),
                'name': "Product"
            }) for rec in range(len(line['pro_id']))],
        })

        # Confirmar y asignar la transferencia para reducir el stock inmediatamente
        # Esto reserva el stock en la ubicación de origen
        transfer.action_confirm()
        transfer.action_assign()

        # Obtener el stock actualizado después de la reserva para cada producto
        stock_updates = self._get_stock_updates_for_products(
            line['pro_id'], stock_location.id, stock_location_dest_id.id
        )

        # Enviar notificación de actualización de stock a todos los POS
        self._notify_stock_update(line['pro_id'], source_id, dest_id, stock_updates)

        return {
            'id': transfer.id,
            'name': transfer.name
        }

    @api.model
    def _get_stock_updates_for_products(self, product_ids, source_location_id, dest_location_id):
        """Obtiene los valores actualizados de stock para los productos"""
        stock_updates = []
        for product_id in product_ids:
            product = self.env['product.product'].browse(product_id)

            # Stock en ubicación origen
            source_quant = self.env['stock.quant'].sudo().search([
                ('product_id', '=', product_id),
                ('location_id', '=', source_location_id),
            ], limit=1)
            source_stock = source_quant.quantity - source_quant.reserved_quantity if source_quant else 0

            # Stock pendiente por recibir en ubicación destino
            pending_moves = self.env['stock.move'].sudo().search([
                ('product_id', '=', product_id),
                ('location_dest_id', '=', dest_location_id),
                ('state', 'in', ['draft', 'waiting', 'confirmed', 'assigned']),
            ])
            incoming_stock = sum(pending_moves.mapped('product_uom_qty'))

            stock_updates.append({
                'product_id': product_id,
                'product_name': product.name,
                'source_stock': source_stock,
                'incoming_stock': incoming_stock,
            })

        return stock_updates

    @api.model
    def _notify_stock_update(self, product_ids, source_warehouse_id, dest_warehouse_id, stock_updates=None):
        """Envía notificación a los POS para actualizar el stock de los productos transferidos"""
        if 'bus.bus' not in self.env:
            return

        if stock_updates is None:
            stock_updates = []
            for product_id in product_ids:
                product = self.env['product.product'].browse(product_id)
                stock_updates.append({
                    'product_id': product_id,
                    'product_name': product.name,
                })

        # Enviar notificación broadcast para actualizar stock en el POS origen
        self.env['bus.bus']._sendone('broadcast', 'POS_STOCK_UPDATE', {
            'message': 'Stock actualizado por transferencia',
            'product_ids': product_ids,
            'source_warehouse_id': source_warehouse_id,
            'dest_warehouse_id': dest_warehouse_id,
            'stock_updates': stock_updates,
        })
