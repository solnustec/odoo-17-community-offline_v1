# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models
from datetime import timedelta
import pytz
from datetime import datetime


class PosConfig(models.Model):
    """Inherited model for adding new field to configuration settings
                that allows to transfer stock from pos session"""
    _inherit = 'pos.config'

    stock_regulation = fields.Boolean(string="Habilitar Regulación de Stock",
                                      help="Habilitar para transferir stock de la sesión de venta",
                                      )
    time_refresh = fields.Integer(string="Tiempo de Actualización (Segundos)",
                                  default=30)
    sync_data = fields.Boolean(string="Sincronizar Datos", default=True,
                               help="Habilitar para sincronizar los datos con el sistema antiguo", )

    @api.model
    def get_time_refresh(self, pos_id):
        pos_config_id = self.env['pos.config'].browse(pos_id)
        if not pos_config_id.time_refresh:
            return 0
        return pos_config_id.time_refresh

    # TODO falta funcion para verificar si el empleado tiene id_employeed_old y el almcen tiene id_external siempre y cuando este activa la funcion de sincronizar datos

    @api.model
    def get_stock_transfer_list_api(self, *args, **kwargs):

        stock_picking_type_id = kwargs.get('stock_picking_type_id')
        sync_data = kwargs.get('sync_data')

        if not stock_picking_type_id:
            return {"success": False,
                    "error": "ID de tipo de picking no proporcionado."}

        # Obtener el empleado con su id_employeed_old
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.user.id)], limit=1)
        if not employee.id_employeed_old and sync_data:
            return {
                "success": False,
                "error": "El ID anterior del empleado no fue proporcionado, por favor comuníquese con el administrador."
            }

        # Obtener información del tipo de picking y validar existencia
        picking_type = self.env['stock.picking.type'].browse(
            stock_picking_type_id)
        if not picking_type.exists():
            return {"success": False,
                    "error": "No se pudo obtener la información de la sucursal."}

        # Obtener el almacén directamente desde el picking type
        warehouse = picking_type.warehouse_id
        if not warehouse.external_id and sync_data:
            return {"success": False,
                    "error": "El almacén no tiene configurado un ID externo."}

        # Obtener laboratorios desde el cronograma
        laboratory_ids = self._get_laboratories_inventory_schedule(
            warehouse.id)
        if not laboratory_ids:
            return {
                "success": False,
                "error": "No se pudo obtener la información para la regulación de inventario o la fecha de actualización finalizó."
            }

        # Filtrar laboratorios
        laboratories = self.env['product.laboratory'].search_read(
            [("id", "in", laboratory_ids)], ['id', 'name', 'id_database_old'])

        inventory_schedule = self.env['inventory.schedule'].search([
            ('state', 'in', ['process', ]),
            ('start_date', '<=', fields.Date.today()),
            ('end_date', '>=', fields.Date.today()),
            ('warehouse_ids', 'in', [warehouse.id, ])
        ], limit=1, order='id desc')

        return {
            "success": True,
            "location_id": picking_type.default_location_src_id.id,
            "laboratories": laboratories,
            "warehouse_id": warehouse.id,
            "warehouse_name": warehouse.name,
            "warehouse_external_id": warehouse.external_id,
            "employee_id_old": employee.id_employeed_old,
            "start_date": inventory_schedule.start_date if inventory_schedule else '',
            "end_date": inventory_schedule.end_date if inventory_schedule else ''
        }

    @api.model
    def get_products_by_laboratory(self, laboratory_id, picking_type_id):
        """Method to get products by laboratory"""

        stock_warehouse_id = self.env['stock.picking.type'].browse(
            picking_type_id)
        stock_location_id = stock_warehouse_id.default_location_src_id.id

        laboratory = self.env['product.laboratory'].browse(int(laboratory_id))
        products = self.env['product.template'].search([
            ('type', '!=', 'service'),
            ('available_in_pos', '=', True),('id_database_old', '!=', False),
            ('laboratory_id', '=', laboratory.id)
        ])
        product_ids = products.mapped('id')

        stock_quants = self.env['stock.quant'].search(
            [('location_id', '=', stock_location_id),
             ("product_tmpl_id", "in", product_ids)])
        result = []
        quant_map = {}
        for quant in stock_quants:
            quant_map[
                quant.product_tmpl_id.id] = quant  # si hay más de uno, podrías sumar quantity
        # 4. Armar la lista final, incluso si no hay stock
        for product in products:
            if not product.available_in_pos or not product.id_database_old:
                continue

            quant = quant_map.get(product.id)
            result.append({
                'product_id': product.id,
                'product_name': product.name,
                'id_database_old': product.id_database_old or '',
                'default_code': product.default_code or '',
                'barcode': product.barcode or '',
                'quantity': quant.quantity if quant else 0.0,
                'available_quantity': quant.available_quantity if quant else 0.0,
                'uom_name': product.uom_po_id.name,
                'list_price': product.list_price,
                'standard_price': product.standard_price,
            })
        result.sort(key=lambda r: r['quantity'], reverse=True)
        return result

    def _get_laboratories_inventory_schedule(self, warehouse_id):
        """Method to get laboratories for inventory schedule"""
        today = fields.Date.today()
        inventory_schedule = self.env['inventory.schedule'].search([
            ('state', 'in', ['process', ]),
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('warehouse_ids', 'in', [warehouse_id, ])
        ], limit=1, order='id desc')
        if not inventory_schedule:
            return []
        inventory_schedule_detail = self.env[
            'inventory.schedule.detail'].search([
            ('schedule_id', '=', inventory_schedule.id),
            ('status', 'not in', ['draft', 'completed', 'cancelled']),
            ('warehouse_id', '=', warehouse_id),
        ])
        laboratory_ids = inventory_schedule_detail.mapped('laboratory_id').ids
        return laboratory_ids

    @api.model
    def adjust_inventory_from_pos(self, products, extr_data, pos_config,
                                  sync_data):
        """Method to adjust inventory from POS"""
        if len(products) == 0:
            return [
                {'success': False, 'message': 'No se encontraron productos'}
            ]

        c_det = {
            "fields": ["iditem", "cantidad", "faltante", "sobrante"],
            "data": []
        }
        datos = []
        detail_id = None
        for product in products:
            product_template = self.env['product.template'].browse(
                int(product.get('product_id')))
            product_id_old = product_template.id_database_old
            product_price = product_template.list_price
            if not product_template:
                continue
            quant = self.env['stock.quant'].search([
                ('product_tmpl_id', '=', product_template.id),
                ('location_id', '=', extr_data.get('location_id'))
            ])
            if sync_data:
                recibir = self.env[
                    'stock.picking'].search_count([
                    ('state', 'in', ['confirmed', 'waiting', 'assigned']),
                    ('picking_type_id.code', '=', 'incoming'),
                    ('product_id', '=', product.get("product_id")),
                ])
                c_det["data"].append(
                    [int(product_id_old),
                     int(product.get('stock_counted')),
                     int(product.get('stock_missing')),
                     int(product.get('stock_over')), ]
                )
            if quant:
                quant.with_context(inventory=True,
                                   inventory_mode=True).sudo().write({
                    'inventory_quantity': int(product.get('stock_counted')),
                    "user_id": self.env.user.id,
                    'inventory_date': fields.Date.today(),
                })
                laboratory_id = extr_data.get('laboratory_id')
                current_detail_id = self._update_inventory_schedule(
                    int(laboratory_id),
                    extr_data.get('warehouse_id'))
                quant.action_apply_inventory()

                # marcar como hecho al cronograma de inventario
            else:
                quant = self.env['stock.quant'].with_context(
                    inventory_mode=True
                ).sudo().create({
                    'product_id': product_template.product_variant_id.id,
                    # Usar la variante del producto
                    'location_id': extr_data.get('location_id'),
                    'inventory_quantity': float(product.get('stock_counted')),
                    # Convertir a float
                    'user_id': self.env.user.id,
                    'inventory_date': fields.Date.today(),
                })
                quant.action_apply_inventory()
                # quant = self.env['stock.quant'].with_context(
                #     inventory=True, inventory_mode=True).sudo().create({
                #     'product_tmpl_id': product_template.id,
                #     'location_id': extr_data.get('location_id'),
                #     'inventory_quantity': int(product.get('stock_counted')),
                #     "user_id": self.env.user.id,
                #     'inventory_date': fields.Date.today(),
                # })
                # quant._apply_inventory()
                laboratory_id = extr_data.get('laboratory_id')
                current_detail_id = self._update_inventory_schedule(
                    int(laboratory_id),
                    extr_data.get('warehouse_id'))
            if current_detail_id:
                detail_id = current_detail_id
                # guardar datos en el json
        if sync_data:
            ec_time_zone = pytz.timezone('America/Guayaquil')
            ec_date_time = datetime.now(ec_time_zone)
            l_sync_date = ec_date_time + timedelta(minutes=3)
            date_time_format = ec_date_time.strftime(
                '%Y-%m-%d %H:%M:%S')
            date_time_lsync = l_sync_date.strftime('%Y-%m-%d %H:%M:%S')
            # c_det["data"].extend(datos)
            idbodega = extr_data.get('warehouse_external_id')
            inventory_regulation = {
                "iduser": extr_data.get('employee_id_old'),
                "idbodega": idbodega.lstrip("0"),
                "l_close": 1,
                "l_sync": 0,
                "l_file": 0,
                "t_init": date_time_format,
                "t_close": date_time_format,
                "t_sync": date_time_format,
                "t_lsync": date_time_lsync,
                "t_file": "",
                "l_sel": 0,
                "total": 0,
                "nota": "",
                "responsable": extr_data.get('laboratory_name'),
                "id_laboratorio": extr_data.get("laboratory_id_old"),
                "c_det": c_det
            }

            json_stock_regulation = self.env['json.stock.regulation']

            json_stock_regulation.sudo().create({
                'json_data': json.dumps([inventory_regulation], indent=4),
                'pos_config_id': pos_config,
                'id_point_of_sale': idbodega.lstrip("0"),
                'laboratory_id': extr_data.get('laboratory_id'),
                'warehouse_id': extr_data.get('warehouse_id'),
            })

        return [
            {'success': True, 'message': 'Stock actualizado correctamente',
             'detail_id': detail_id or None}]

    def _update_inventory_schedule(self, laboratory_id, warehouse_id):
        inventory_schedule_detail = self.env[
            'inventory.schedule.detail'].search([
            ('warehouse_id', '=', warehouse_id),
            ('status', '=', 'in_progress'),
            ('laboratory_id', '=', laboratory_id)
        ], limit=1)

        if not inventory_schedule_detail:
            return False

        inventory_schedule_detail.write({
            'status': 'completed',
            'completion_date': fields.Date.today(),
            'completion_user_id': self.env.user.id,
        })
        return inventory_schedule_detail.id
