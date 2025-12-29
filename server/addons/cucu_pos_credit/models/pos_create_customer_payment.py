from odoo import fields, models
from datetime import datetime


# class AccountPayment(models.Model):
#     _inherit = 'account.payment'
#
#     pos_session_id = fields.Many2one('pos.session', string='Pos Session')


class pos_create_customer_payment(models.Model):
    _name = "pos.create.customer.payment"
    _description = "Pos Create Customer Payment"

    def create_customer_payment(self, partner_id, journal, amount, note, session_id):
        account_payment_obj = self.env["account.payment"]
        values = {
            "payment_type": "inbound",
            "amount": amount,
            "date": datetime.now().date(),
            "journal_id": int(journal),
            "payment_method_id": 1,
            "notes_pos": note,
            "partner_type": "customer",
            "partner_id": partner_id,
            "pos_session_id": session_id,
        }
        payment_create = account_payment_obj.sudo().create(values)
        payment_create.action_post()  # Confirm Account Payment
        return True

    def get_hist_payments(self, partner_id, invoice):
        payments = self.env["account.payment"].search(
            [("ref", "=", invoice["name"]), ("partner_id", "=", partner_id)]
        )
        res = []
        for payment in payments:
            res.append(
                {
                    "id": payment.id,
                    "amount": payment.amount,
                    "name": payment.journal_id.name,
                    "date": payment.create_date.strftime("%d/%m/%Y"),
                }
            )
        return sorted(res, key=lambda pay: pay["id"])

    def create_customer_payment_inv(
        self, partner_id, journal, amount, invoice, note, session_id
    ):
        payment_object = self.env["account.payment"]
        partner_object = self.env["res.partner"]  # noqa
        inv_obj = self.env["account.move"].search([("id", "=", invoice["id"])], limit=1)
        vals = {
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": partner_id,
            "journal_id": int(journal),
            "currency_id": inv_obj.currency_id.id,
            "ref": inv_obj.name,
            "notes_pos": note,
            "amount": amount,
            "date": fields.Date.today(),
            "payment_method_id": 1,
            "pos_session_id": session_id,
        }

        a = payment_object.create(vals)  # Create Account Payment
        a.action_post()  # Confirm Account Payment

        to_reconcile = []
        to_reconcile.append(inv_obj.line_ids)
        domain = [
            (
                "account_id.account_type",
                "in",
                ("asset_receivable", "liability_payable"),
            ),
            ("reconciled", "=", False),
        ]
        for payment_object, lines in zip(a, to_reconcile):
            payment_lines = payment_object.line_ids.filtered_domain(domain)
            for account in payment_lines.account_id:
                (payment_lines + lines).filtered_domain(
                    [("account_id", "=", account.id), ("reconciled", "=", False)]
                ).reconcile()

        return True
