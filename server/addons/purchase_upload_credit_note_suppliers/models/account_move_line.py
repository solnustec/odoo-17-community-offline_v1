from odoo import models, fields, api

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _apply_credit_note_account_rules(self, change_of_credit_note_type_flag):
        """Actualizar la cuenta contable de cada linea de acuerdo al tipo de nota de credito y al impuesto"""
        self.ensure_one()

        move = self.move_id

        if move.move_type != 'in_refund':
            return

        if not move.credit_note_type:
            return

        credit_note_type = move.credit_note_type
        account = credit_note_type.account_id
        second_account = credit_note_type.second_account_id

        taxes = self.tax_ids

        tax = taxes[0] if taxes else False

        tax_amount = tax.amount if tax else None

        if credit_note_type.code == 'product_return':
            if tax_amount == 15:
                if account:
                    self.account_id = account.id
            elif tax_amount == 0:
                if second_account:
                    self.account_id = second_account.id
            else:
                self.account_id = False
        else:
            if change_of_credit_note_type_flag:
                if account:
                    self.account_id = account.id

    @api.onchange('tax_ids')
    def _onchange_tax_ids_credit_note_line(self):
        self._apply_credit_note_account_rules(False)