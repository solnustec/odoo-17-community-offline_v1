from datetime import timedelta

from odoo import api, fields, models


class InventorySchedule(models.Model):
    _name = 'inventory.schedule'
    _inherit = ['mail.thread', ]

    _description = 'Cronograma de Inventario por Laboratorio'
    name = fields.Char(string='Nombre', required=False, tracking=True)

    laboratory_ids = fields.Many2many('product.laboratory',
                                      string='Laboratorios', required=True,
                                      tracking=True)
    warehouse_ids = fields.Many2many('stock.warehouse',
                                     string='Sucursales',
                                     required=False, tracking=True)
    start_date = fields.Date(string='Inicio', required=True,
                             default=fields.Date.today(), tracking=True)
    end_date = fields.Date(string='Fin', required=True,
                           default=fields.Date.today() + timedelta(days=30),
                           tracking=True)
    user_id = fields.Many2one('res.users', string='Creado por',
                              default=lambda self: self.env.user)
    schedule_detail_ids = fields.One2many('inventory.schedule.detail',
                                          'schedule_id', string='Detalles')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('process', 'En proceso'),
        ('done', 'Completado')
    ], default='draft', string='Estado', tracking=True)
    active = fields.Boolean(default=True, tracking=True, string='Activo')

    def unlink(self):
        self.write({"active": False})
        return super().unlink()

    def action_process(self):
        self.write({'state': 'process'})
        self.schedule_detail_ids.write({'status': 'in_progress'})
        self._activate_pos_stock_regulation(status=True)
        return True

    def _check_all_details_completed(self):
        """Verifica si todos los detalles están completados y actualiza el estado del padre."""
        for schedule in self:
            all_completed = all(
                detail.status == 'completed'
                for detail in schedule.schedule_detail_ids
            )
            if all_completed:
                self._activate_pos_stock_regulation(status=False)
                schedule.write({'state': 'done'})

    #     return records
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Si no hay sucursales seleccionadas, obtener todas
            if not vals.get('warehouse_ids'):
                all_warehouses = self.env['stock.warehouse'].search([])
                vals['warehouse_ids'] = [(6, 0, all_warehouses.ids)]
        records = super().create(vals_list)
        for record in records:
            self._create_schedule_details(record)
        return records

    def write(self, vals):
        if 'warehouse_ids' in vals and not vals['warehouse_ids']:
            self._clean_related_records(vals)
            all_warehouses = self.env['stock.warehouse'].search([])
            vals['warehouse_ids'] = [(6, 0, all_warehouses.ids)]
        if 'laboratory_ids' in vals or 'warehouse_ids' in vals:
            self._clean_related_records(vals)
        result = super().write(vals)
        for record in self:
            if 'warehouse_ids' in vals or 'laboratory_ids' in vals:
                self._create_schedule_details(record)
        return result

    def _activate_pos_stock_regulation(self, status=False):
        for record in self:
            for warehouse in record.warehouse_ids:
                stock_picking = self.env['stock.picking.type'].search(
                    [('warehouse_id', '=', warehouse.id),
                     ('sequence_code', '=', 'POS')])

                pos = self.env['pos.config'].search(
                    [('picking_type_id', '=', stock_picking.id)]).write(
                    {'stock_regulation': status})

    def _clean_related_records(self, vals):
        if 'laboratory_ids' or 'warehouse_ids' in vals:
            self.env['inventory.schedule.detail'].search([
                ('schedule_id', '=', self[0].id)
            ]).unlink()

    def _create_schedule_details(self, record):
        existing_details = self.env['inventory.schedule.detail'].search([
            ('schedule_id', '=', record.id), ('status', '!=', 'completed')
        ])

        existing_combinations = set(
            (detail.warehouse_id.id, detail.laboratory_id.id)
            for detail in existing_details
        )

        details = []
        for warehouse in record.warehouse_ids:
            for laboratory in record.laboratory_ids:
                if (warehouse.id, laboratory.id) not in existing_combinations:
                    details.append({
                        'schedule_id': record.id,
                        'warehouse_id': warehouse.id,
                        'laboratory_id': laboratory.id,
                        'status': 'draft',  # Estado pendiente
                    })

        if details:
            self.env['inventory.schedule.detail'].create(details)


class InventoryScheduleDetail(models.Model):
    _name = 'inventory.schedule.detail'
    _description = 'Detalle de Cronograma de Inventario'

    schedule_id = fields.Many2one('inventory.schedule', string='Cronograma',
                                  required=True, ondelete='cascade')
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén',
                                   required=True)
    laboratory_id = fields.Many2one('product.laboratory', string='Laboratorio',
                                    required=True)
    completion_date = fields.Date(string='Fecha de Realización', )

    completion_user_id = fields.Many2one('res.users',
                                         string='Registrado por', )
    status = fields.Selection([
        ('draft', 'Borrador'),
        ('in_progress', 'En Proceso'),
        ('completed', 'Completado'),
        ('cancelled', 'Cancelado')
    ], default='draft', string='Estado')
    active = fields.Boolean(default=True, string="Activo")

    def unlink(self):
        self.write({"active": False})
        return super().unlink()

    def write(self, vals):
        """Actualiza el estado del cronograma padre si es necesario."""
        res = super(InventoryScheduleDetail, self).write(vals)
        if 'status' in vals:
            schedules = self.mapped('schedule_id')
            schedules._check_all_details_completed()
        return res

    # total_products = fields.Integer(string='Total Productos',
    #                                 compute='_compute_total_products')
    # inventory_value = fields.Float(string='Valor de Inventario',
    #                                compute='_compute_inventory_value')

    # @api.depends('warehouse_id', 'laboratory_id')
    # def _compute_total_products(self):
    #     for record in self:
    #         record.total_products = self.env['product.product'].search_count([
    #             ('laboratory_id', '=', record.laboratory_id.id),
    #             ('warehouse_id', '=', record.warehouse_id.id)
    #         ])
    #
    # @api.depends('warehouse_id', 'laboratory_id')
    # def _compute_inventory_value(self):
    #     for record in self:
    #         products = self.env['product.product'].search([
    #             ('laboratory_id', '=', record.laboratory_id.id)
    #         ])
    #         record.inventory_value = sum(
    #             self.env['stock.quant'].search([
    #                 ('product_id', 'in', products.ids),
    #                 ('warehouse_id', '=', record.warehouse_id.id)
    #             ]).mapped('value')
    #         )
