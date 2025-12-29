from odoo import models, fields, api, _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def get_order_detail_chatbot(self,order_id):
        order = self.env['sale.order'].search([('id', '=', order_id)])
        list_order = []
        data = {
            "x_channel": order.x_channel,
            "x_tipo_pago": order.x_tipo_pago,
            # "card_info": order.card_info,
            "digital_media": order.digital_media,
            "pay_deuna_id":order.pay_deuna_id,
            "pay_ahorita_id":order.pay_ahorita_id
        }
        list_order.append(data)
        return list_order

    @api.model
    def get_order_detail_chatbot_name(self,order_id):
        order = self.env['sale.order'].search([('name', '=', order_id)])
        list_order = []
        data = {
            "x_channel": order.x_channel,
            "x_tipo_pago": order.x_tipo_pago,
            "digital_media": order.digital_media,
            "pay_deuna_id":order.pay_deuna_id,
            "pay_ahorita_id":order.pay_ahorita_id
        }
        list_order.append(data)
        return list_order

