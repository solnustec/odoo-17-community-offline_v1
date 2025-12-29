from odoo import api, fields, models, tools


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    reward_product_id = fields.Integer(string='Reward Product ID')
    product_free = fields.Boolean(string='Free Product', default=False)
    original_id_reward = fields.Integer(string='Original ID Product Reward')
    amount_applied = fields.Integer(string='Cantidad de producto aplicado promoción')

    @api.model
    def get_order_id(self, pos_order_line_id):
        order_line = self.browse(pos_order_line_id)
        if order_line:
            return order_line.order_id.id
        else:
            return False

    def _export_for_ui(self, orderline):

        result = super()._export_for_ui(orderline)
        result['amount_applied'] = orderline.amount_applied
        result['reward_product_id'] = orderline.reward_product_id
        return result

    @api.model
    def _order_line_fields(self, line, session_id=None):
        if isinstance(line, (list, tuple)) and len(line) == 3:
            line_dict = line[2] or {}
            if 'coupon_id' in line_dict and line_dict['coupon_id'] is None:
                line_dict['coupon_id'] = False
            if 'reward_id' in line_dict and line_dict['reward_id'] is None:
                line_dict['reward_id'] = False
        elif isinstance(line, dict):
            if 'coupon_id' in line and line['coupon_id'] is None:
                line['coupon_id'] = False
            if 'reward_id' in line and line['reward_id'] is None:
                line['reward_id'] = False

        res = super()._order_line_fields(line, session_id)

        line_vals = line[2] if isinstance(line, list) else line
        amount_applied = line_vals.get('amount_applied')
        reward_product_id = line_vals.get('reward_product_id')
        if isinstance(res, list):
            res[2].update({
                'amount_applied': amount_applied,
                'reward_product_id': reward_product_id,
            })
        else:
            res.update({
                'amount_applied': amount_applied,
                'reward_product_id': reward_product_id,
            })
        return res
