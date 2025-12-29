from odoo import models, fields

class StockWarehouseGroup(models.Model):
    _name = 'stock.warehouse.group'
    _description = 'Grupo de Almacenes'

    name = fields.Char(string='Nombre del grupo', required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Almacenes')
