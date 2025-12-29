from odoo import models, fields, api
import re


class PosConfig(models.Model):
    _inherit = 'pos.config'

    point_of_sale_series = fields.Char(string="Serie punto de venta")
    point_of_sale_id = fields.Char(string="Id bodega")
    point_of_sale_customer = fields.Char(string="Serie punto de venta")
    ip_maquina_local = fields.Char(string="ip_maquina_local")

    # Método para obtener el punto de venta del empleado
    def get_pos_by_employee(self, employee_id):
        pos_config = self.env['pos.config'].sudo().search([
            ('basic_employee_ids', 'in', [employee_id])
        ], limit=1)
        if pos_config:
            warehouse = pos_config.picking_type_id.warehouse_id
            if warehouse:
                data = {
                    "id": warehouse.id,
                    "name": warehouse.name,
                    "external_id": warehouse.external_id.lstrip("0"),
                    "point_of_sale_series": pos_config.point_of_sale_series,
                }
                return data
        return None

    def get_pos_by_ware_and_pos_c(self, warehouse, pos_config):
        if warehouse:
            data = {
                "id": warehouse.id,
                "name": warehouse.name,
                "external_id": warehouse.external_id.lstrip("0"),
                "point_of_sale_series": pos_config.point_of_sale_series,
            }
            return data
        return None