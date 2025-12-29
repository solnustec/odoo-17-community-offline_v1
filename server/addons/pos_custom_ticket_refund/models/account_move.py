# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    note_credit = fields.Monetary(string='Valor Original da Nota de Crédito', ondelete='cascade', currency_field='currency_id')

    # @api.model
    # def create(self, vals):
    #     move = super(AccountMove, self).create(vals)
    #     if move.move_type == 'out_refund' and self.test(move.id):
    #         print("Se llama el método de note")
    #         move.note_credit = move.amount_total
    #     return move




class PosOrderCustom(models.Model):
    _inherit = 'pos.order'

    def _generate_pos_order_invoice(self):
        generate = super()._generate_pos_order_invoice()

        for order in self:
            if order.account_move.move_type == 'out_refund' and self.verify_method(order):
                order.account_move.note_credit = order.account_move.amount_total

        return generate

    def verify_method(self, order):

        is_payment_anticipe = False
        if order:
            for payment in order.payment_ids:
                if payment.payment_method_id.code_payment_method == "CTACLIENTE":
                    is_payment_anticipe = True
                    break

        return is_payment_anticipe


