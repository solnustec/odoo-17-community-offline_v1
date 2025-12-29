from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    note = fields.Text(string="Note")
    reward_product_id = fields.Integer(string="Product Reward")



    def _get_sale_order_fields(self):
        fields = super()._get_sale_order_fields()

        fields.append("reward_product_id")
        return fields