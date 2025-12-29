from odoo import models

from collections import defaultdict


class PosOrder(models.Model):
    _inherit = "pos.order"

    def get_move_by_partner(self, partner_id):
        moves = self.env["pos.order"].search(
            [("partner_id", "=", partner_id), ("to_invoice", "=", True)]
        )
        count = 0
        for move in moves.account_move:
            if (
                move.payment_state != "paid"
                and move.state == "posted"
                and move.move_type == "out_invoice"
            ):
                count = count + 1
        return count > 0

    def _load_params_account_move(self):
        return {
            "search_params": {
                "domain": [
                    ["state", "=", "posted"],
                    ["move_type", "=", "out_invoice"],
                    ["payment_state", "!=", "paid"],
                ],
                "fields": [
                    "partner_id",
                    "amount_total",
                    "amount_residual",
                    "currency_id",
                    "state",
                    "payment_state",
                    "name",
                ],
            }
        }

    def get_moves_partner(self, partner_id):
        params = self._load_params_account_move()
        params["search_params"]["domain"].append(["partner_id", "=", partner_id])
        moves = self.env["account.move"].search_read(**params["search_params"])
        return moves

    def get_moves_partner_all(self):
        params = self._load_params_account_move()
        moves = self.env["account.move"].search_read(**params["search_params"])
        return moves

    def get_moves_partner_pos_session(self, config_id):
        params = self._load_params_account_move()
        params["search_params"]["domain"].append(["pos_config_id", "=", config_id])
        moves = self.env["account.move"].search_read(**params["search_params"])
        return moves

    def _load_params_payments_session_id(self, session_id):
        return {
            "search_params": {
                "domain": [
                    ["pos_session_id", "=", session_id],
                    ["partner_type", "=", "customer"],
                ],
                "fields": ["amount"],
            }
        }

    def get_payments_session_id(self, session_id):
        # params = self._load_params_payments_session_id(session_id)
        payments = self.env["account.payment"].search(
            [
                ("pos_session_id", "=", session_id),
                ("partner_type", "=", "customer"),
            ],
        )
        res = []
        for payment in payments:
            res.append(
                {
                    "amount": payment.amount,
                    "payment_type": payment.journal_id.display_name,
                }
            )
        return res

    def get_payments_report(self, session_id):
        # params = self._load_params_payments_session_id(session_id)
        payments = self.env["account.payment"].search(
            [
                ("pos_session_id", "=", session_id),
                ("partner_type", "=", "customer"),
            ],
        )
        if len(payments) == 0:
            return False
        res = defaultdict(int)
        for payment in payments:
            res[payment.journal_id.display_name] += payment.amount
        return res


class PosOrderLoad(models.Model):
    _inherit = "pos.session"

    def _get_pos_ui_res_partner(self, params):
        partners = super(PosOrderLoad, self)._get_pos_ui_res_partner(params)
        res = []
        for partner in partners:
            partner["to_credit"] = self.env["pos.order"].get_move_by_partner(
                partner["id"]
            )
            res.append(partner)
        return res

    def _pos_ui_models_to_load(self):
        result = super()._pos_ui_models_to_load()
        result += [
            "account.move",
            "account.journal",
        ]
        return result

    def _loader_params_account_move(self):
        return {
            "search_params": {
                "domain": [
                    ["move_type", "=", "out_invoice"],
                    ["state", "=", "posted"],
                    ["payment_state", "!=", "paid"],
                ],
                "fields": [
                    "name",
                    "partner_id",
                    "amount_total",
                    "amount_residual",
                    "currency_id",
                    "amount_residual",
                    "state",
                    "move_type",
                ],
            }
        }

    def _get_pos_ui_account_move(self, params):
        return self.env["account.move"].search_read(**params["search_params"])

    def _loader_params_account_journal(self):
        return {
            "search_params": {
                "domain": [["type", "in", ["cash", "bank"]]],
                "fields": [
                    "id",
                    "name",
                    "type",
                ],
            }
        }

    def _get_pos_ui_account_journal(self, params):
        config = self.config_id
        res = []
        for method in config.payment_method_ids:
            journal_id = method.journal_id
            if journal_id:
                res.append(
                    {
                        "id": journal_id.id,
                        "name": journal_id.name,
                        "type": journal_id.type,
                    }
                )
        # self.env["account.journal"].search_read(**params["search_params"])
        return res

    def load_pos_data(self):
        loaded_data = super(PosOrderLoad, self).load_pos_data()
        poscurrency = self.env["res.currency"].search_read(
            domain=[("active", "=", True)],
            fields=["name", "symbol", "position", "rounding", "rate"],
        )
        loaded_data["poscurrency"] = poscurrency
        return loaded_data

    def _loader_params_pos_payment_method(self):
        res = super()._loader_params_pos_payment_method()
        add_fields = ["payment_key"]
        for field in add_fields:
            res["search_params"]["fields"].append(field)
        return res
