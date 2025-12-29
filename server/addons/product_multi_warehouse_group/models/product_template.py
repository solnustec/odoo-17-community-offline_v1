from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    warehouse_group_id = fields.Many2one(
        'stock.warehouse.group', string="Grupo de Almacenes"
    )

    @api.onchange('warehouse_group_id')
    def _onchange_group(self):
        if self.warehouse_group_id:
            # Obtener los almacenes asociados al grupo seleccionado
            warehouses = self.warehouse_group_id.warehouse_ids

            # Extraer las rutas de esos almacenes
            routes = warehouses.mapped('route_ids')

            # Registrar las rutas en el log para debug
            _logger.info(f"Rutas obtenidas del grupo de almacenes: {routes.ids}")

            # Asignar las rutas directamente al campo route_ids sin return
            self.route_ids = [(6, 0, routes.ids)]

    @api.model
    def create(self, vals):
        if 'warehouse_group_id' in vals:
            # Obtener el grupo de almacenes
            warehouse_group = self.env['stock.warehouse.group'].browse(
                vals['warehouse_group_id'])

            # Obtener las rutas asociadas a los almacenes del grupo
            routes = warehouse_group.warehouse_ids.mapped('route_ids')

            # Registrar las rutas en el log
            _logger.info(f"Rutas asignadas al crear: {routes.ids}")

            # Asignar las rutas directamente al producto
            vals['route_ids'] = [(6, 0, routes.ids)]

        return super(ProductTemplate, self).create(vals)

    def write(self, vals):
        if 'warehouse_group_id' in vals:
            # Obtener el grupo de almacenes
            warehouse_group = self.env['stock.warehouse.group'].browse(
                vals['warehouse_group_id'])

            # Obtener las rutas asociadas a los almacenes del grupo
            routes = warehouse_group.warehouse_ids.mapped('route_ids')

            # Registrar las rutas en el log
            _logger.info(f"Rutas asignadas al escribir: {routes.ids}")

            # Asignar las rutas directamente al producto
            vals['route_ids'] = [(6, 0, routes.ids)]

        return super(ProductTemplate, self).write(vals)
