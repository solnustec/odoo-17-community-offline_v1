import json
from datetime import datetime

from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    _order = 'scheduled_date desc, id desc'  # Orden descendente (más recientes primero)

    picking_type_code = fields.Selection(
        related='picking_type_id.code',
        string='Tipo de Operación',
        store=True,
        readonly=True,
    )

    origin_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén Origen',
        compute='_compute_origin_warehouse',
        store=True,
        readonly=False,  # permite edición manual
        precompute=True,
    )

    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén Destino',
        compute='_compute_dest_warehouse',
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends('location_id')
    def _compute_origin_warehouse(self):
        for record in self:
            if record.location_id:
                record.origin_warehouse_id = self._get_warehouse_from_location(record.location_id)
            else:
                record.origin_warehouse_id = False

    @api.depends('location_dest_id')
    def _compute_dest_warehouse(self):
        for record in self:
            if record.location_dest_id:
                record.dest_warehouse_id = self._get_warehouse_from_location(record.location_dest_id)
            else:
                record.dest_warehouse_id = False

    def _get_warehouse_from_location(self, location):
        return self.env['stock.warehouse'].search([
            '|', '|',
            ('lot_stock_id', '=', location.id),
            ('wh_input_stock_loc_id', '=', location.id),
            ('view_location_id', 'parent_of', location.id),
        ], limit=1)

    # Mantén los onchange para la relación inversa (warehouse -> location)
    @api.onchange('origin_warehouse_id')
    def _onchange_origin_warehouse(self):
        """Actualiza location_id cuando cambia el almacén de origen manualmente"""
        if self.origin_warehouse_id and not self._origin.origin_warehouse_id == self.origin_warehouse_id:
            self.location_id = self.origin_warehouse_id.lot_stock_id

    @api.onchange('dest_warehouse_id')
    def _onchange_dest_warehouse(self):
        """Actualiza location_dest_id cuando cambia el almacén de destino manualmente"""
        if self.dest_warehouse_id and not self._origin.dest_warehouse_id == self.dest_warehouse_id:
            self.location_dest_id = self.dest_warehouse_id.lot_stock_id

    @api.model_create_multi
    def create(self, vals_list):
        records = super(StockPicking, self).create(vals_list)
        for record in records:
            if record.picking_type_id.code == 'internal' and not record.key_transfer and not record.location_id.warehouse_id.code == 'BODMA':
                record.create_transfer_edit_from_branch_to_branch()
        return records

    def create_transfer_edit_from_branch_to_branch(self):
        list_transfers = []

        for record in self:
            if not record.location_id.warehouse_id or not record.location_dest_id.warehouse_id:
                continue

            employee_name = "Unknown"
            if record.user_id and record.user_id.employee_ids:
                employee_name = record.user_id.employee_ids[0].name

            # Usar move_ids en lugar de move_line_ids porque al crear el picking
            # las move_line_ids aún no existen (se crean en action_assign)
            moves = record.move_ids_without_package
            order_lines_data = []
            transfer_products_list = []

            for index, move in enumerate(moves):
                product_id = move.product_id.product_tmpl_id.id_database_old or None
                quantity = move.product_uom_qty  # Cantidad demandada (borrador)
                price = move.product_id.list_price or 0.0

                transfer_products_list.append({
                    "llave": index + 1,
                    "orden": "10",
                    "iditem": product_id,
                    "cantidad": quantity,
                    "precio": price,
                    "idlote": 0,
                    "disponible": 0,
                    "recibido": 0,
                })

                order_lines_data.append([
                    "10",
                    product_id,
                    quantity,
                    price,
                    0.0,
                ])

            pos_conf = self.env['pos.config'].sudo().search([
                ('picking_type_id.warehouse_id', '=', record.location_id.warehouse_id.id),
                ('point_of_sale_series', '!=', False),
            ], limit=1)

            data = {
                "transfer": {
                    "llave": "",
                    "iduser": record.user_id.employee_ids and record.user_id.employee_ids[0].id_employeed_old or '',
                    "idbodfrom": record.location_id.warehouse_id.external_id,
                    "idbodto": record.location_dest_id.warehouse_id.external_id,
                    "serie": pos_conf.point_of_sale_series or "",
                    "secuencia": 0,
                    "tipo": 1,
                    "l_close": 0,
                    "l_recibido": 0,
                    "l_sync": 0,
                    "l_file": 0,
                    "l_void": 0,
                    "t_init": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "t_close": "",
                    "t_recibido": "",
                    "t_sync": "",
                    "t_void": None,
                    "t_file": None,
                    "l_sel": 0,
                    "total": "",
                    "nota": record.note or "",
                    "responsable": record.user_id.email or "",
                    "cdet": {
                        "fields": ["orden", "iditem", "cantidad", "precio", "idlote"],
                        "data": order_lines_data
                    },
                    "express": record.type_transfer or "",
                },
                "transfer_products": transfer_products_list
            }

            obj = {
                'json_data': json.dumps([data], indent=4),
                'external_id': record.location_id.warehouse_id.external_id or "",
                'point_of_sale_series': pos_conf.point_of_sale_series or "",
                'stock_picking_id': record.id,
                'sync_date': None,
                'db_key': "",
                'sent': False,
                'employee': employee_name,
                'origin': record.location_id.warehouse_id.name or "Unknown",
                'destin': record.location_dest_id.warehouse_id.name or "Unknown",
            }

            list_transfers.append(obj)

        if list_transfers:
            self.env['json.pos.transfers.edits'].sudo().create(list_transfers)