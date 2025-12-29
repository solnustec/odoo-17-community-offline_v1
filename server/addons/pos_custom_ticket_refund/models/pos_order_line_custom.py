from odoo import fields, models, api

class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    reward_prod_id = fields.Integer(
        string='Reward Product Trigger ID',
        help="Producto activador de promoción"
    )

    program_id = fields.Integer(
        string='Reward Program ID',
        help="Programa de promoción"
    )

    @api.model_create_multi
    def create(self, vals_list):
        for line in vals_list:
            if line.get('reward_product_id'):
                line['reward_prod_id'] = line['reward_product_id']
        res = super().create(vals_list)
        return res

    def _export_for_ui(self, orderline):
        result = super()._export_for_ui(orderline)
        result['reward_product_id'] = orderline.reward_prod_id
        result['program_id'] = orderline.program_id
        result['original_id_reward'] = orderline.original_id_reward
        return result
