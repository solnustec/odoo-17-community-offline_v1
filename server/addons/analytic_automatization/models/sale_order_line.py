from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def create(self, vals_list):
        res = super().create(vals_list)
        if not vals_list.get('analytic_distribution'):
            raise ValidationError(
                "La linea o lineas, de la orden de venta no tiene una cuenta analítica asignada. Contacte con el administrador."
            )
        return res

    def write(self, vals):
        res = super().write(vals)
        if not self.analytic_distribution:
            raise ValidationError(
                "La linea o lineas, de la orden de venta no tiene una cuenta analítica asignada. Contacte con el administrador."
            )

        return res

    @api.onchange('product_id')
    def _onchange_product_set_analytic_distribution(self):
        self.ensure_one()
        if not self.order_id.warehouse_id.analytic_account_id:
            raise ValidationError(
                "La bodega asociada a la orden de venta no tiene una cuenta analítica asignada."
            )
        self.analytic_distribution = {
            self.order_id.warehouse_id.analytic_account_id.id: 100}
    #
    #     if self.analytic_distribution:
    #         return None
    #     user = self.env.user
    #     employee = self.env['hr.employee'].search([('user_id', '=', user.id)],
    #                                               limit=1)
    #     print(employee, employee.department_id)
    #     if not employee or not employee.department_id:
    #         self.product_id = False
    #         return {
    #             'error': {
    #                 'title': "Departamento no asignado",
    #                 'message': "No se puede asignar una cuenta analítica automáticamente porque el empleado no tiene departamento asignado. Contacte con el administrador.",
    #                 'type': 'notification',
    #             }
    #         }
    #     # verificar que el empleado tenfda el departamento configuradpk
    #     print(employee, employee.department_id,
    #           employee.department_id.analytic_account_ids)
    #     if employee and employee.department_id and employee.department_id.analytic_account_ids:
    #         analytic_account = employee.department_id.analytic_account_ids[0]
    #         # agrega la distribucion analitoc a la linea con el 100 % de acuerdo a la confiruracion
    #         self.analytic_distribution = {analytic_account.id: 100}
    #         return None
    #     raise ValidationError(
    #         "Error: El empleado no tiene departamento asignado. Contacte con el administrador."
    #     )
