from odoo import fields
from odoo import models, api
import pytz
from odoo.exceptions import UserError
from ast import literal_eval
import json
from datetime import datetime, date
import logging

_logger = logging.getLogger(__name__)


class PosCloseSessionBills(models.Model):
    _name = "pos.close.session.bills"
    _description = "Pos Close Session Bills"

    pos_session_id = fields.Many2one("pos.session", string="Sesión", required=False)
    bills_data = fields.Json(string="Pos Session Bills Data", readonly=True)


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def ping_server(self):
        return {'status': 'ok'}

    out_money_point_of_sale = fields.Float(
        string="Out money point of sale", digits=(10, 2), store=True
    )

    def _loader_params_pos_session(self):
        result = super()._loader_params_pos_session()
        result["search_params"]["fields"].append("out_money_point_of_sale")
        return result

    def update_out_money(self, session_id, out_money_value):
        """Método para actualizar el campo `out_money_point_of_sale` en la sesión POS"""
        session = self.browse(session_id)
        if session.exists():
            session.write({"out_money_point_of_sale": out_money_value})
            return {"success": True, "message": "Valor actualizado correctamente"}
        return {"success": False, "error": "Sesión no encontrada"}

    @api.model
    def action_pos_session_close(
            self,
            balancing_account=False,
            amount_to_balance=0,
            bank_payment_method_diffs=None,
    ):
        _logger.info(f"Cerrando sesión POS {self.id} (usuario: {self.user_id.id})")
        res = super(PosSession, self).action_pos_session_close(
            balancing_account, amount_to_balance, bank_payment_method_diffs
        )
        ecuador_tz = pytz.timezone("America/Guayaquil")

        def convert_to_ecuador_time(dt):
            if dt:
                dt_utc = dt.replace(tzinfo=pytz.utc)  # Asegurar que es UTC
                return dt_utc.astimezone(ecuador_tz).strftime("%Y-%m-%d %H:%M:%S")
            return None

        pos_session = self.env["pos.session"].sudo().browse(self.id)
        user_id = pos_session.user_id.id
        # session = self.env["pos.session"].browse(pos_session.id)
        # session.try_cash_in_out(
        #     "out",  # Tipo: 'in' (entrada) o 'out' (salida)
        #     pos_session.out_money_point_of_sale,  # Monto de la transacción
        #     "VENTAS DEL DIA",  # Razón de la transaccipoón
        #     {"translatedType": "Cash Out"},  # Extras opcionales
        # )
        # # restar lasalida de efectivo de la sesion
        # session.write(
        #     {
        #         "cash_register_balance_end_real": session.cash_register_balance_end_real
        #         - pos_session.out_money_point_of_sale
        #     }
        # )

        # Buscar el empleado asociado al usuario

        hr_employee = (
            self.env["hr.employee"].sudo().search([("user_id", "=", user_id)], limit=1)
        )

        pos_close_session_bills = (
            self.env["pos.close.session.bills"]
            .sudo()
            .search_read(
                [("pos_session_id", "=", pos_session.id)], ["bills_data"], limit=1
            )
        )

        pos_bills_default = {
            "b100": 0,
            "b50": 0,
            "b20": 0,
            "b10": 0,
            "b5": 0,
            "b1": 0,
            "btotal": 0,
            "m100": 0,
            "m50": 0,
            "m25": 0,
            "m10": 0,
            "m5": 0,
            "m1": 0,
            "mtotal": 0,
        }

        # Definición de denominaciones: (clave, valor)
        BILL_DENOMINATIONS = [
            ("b100", 100),
            ("b50", 50),
            ("b20", 20),
            ("b10", 10),
            ("b5", 5),
            ("b1", 1),
        ]

        COIN_DENOMINATIONS = [
            ("m100", 1.00),
            ("m50", 0.50),
            ("m25", 0.25),
            ("m10", 0.10),
            ("m5", 0.05),
            ("m1", 0.01),
        ]

        FONDO_CAJA = self.cash_register_balance_start  # Constante para el fondo de caja

        def _calculate_total(data, denominations):
            """Calcula el total basado en las denominaciones."""
            return sum(
                (data.get(key) or 0) * value
                for key, value in denominations
            )

        # Actualizar datos si existen
        if pos_close_session_bills:
            bills_data = pos_close_session_bills[0].get("bills_data") or {}
            pos_bills_default.update(bills_data)

        # Calcular totales
        total_bills = _calculate_total(pos_bills_default, BILL_DENOMINATIONS)
        total_coins = _calculate_total(pos_bills_default, COIN_DENOMINATIONS)
        total_ef = (total_bills + total_coins) or self.cash_register_balance_end_real

        # Actualizar diccionario
        pos_bills_default.update({
            "btotal": total_bills,
            "mtotal": total_coins,
            "total_ef": total_ef - FONDO_CAJA,
        })

        self.env["pos.close.session.bills"].sudo().create(
            {"bills_data": pos_bills_default, "pos_session_id": self.id}
        )

        pos_session_data = {
            "iduser": hr_employee.id_employeed_old,
            "date": datetime.now(ecuador_tz).strftime("%Y%m%d"),
            "l_close": 1,
            "l_sync": 0,
            "l_file": 0,
            "l_void": 0,
            "t_init": convert_to_ecuador_time(self[0].start_at),
            "t_close": convert_to_ecuador_time(self[0].stop_at),
            "cash_register_total_entry_encoding": pos_session.cash_register_difference,
        }

        pos_session_data.update(pos_bills_default)
        self.env["json.pos.close.session"].sudo().create(
            {
                "json_data": pos_session_data,
                "pos_session_id": self.id,
                "pos_config_id": pos_session.config_id.id,
                "id_point_of_sale": int(
                    pos_session.config_id.picking_type_id.warehouse_id.external_id
                ),
                "create_date": datetime.now(ecuador_tz).strftime("%Y%m%d"),
            }
        )

        self.process_session_for_dashboard(pos_session, pos_bills_default, total_ef - FONDO_CAJA)

        ticket_vals = {
            "employee": hr_employee.name or "Desconocido",
            "point_of_sale": pos_session.config_id.picking_type_id.warehouse_id.name,
            # Store exactly what the cashier counted:
            "values": json.dumps(pos_bills_default),
            "pos_session_id": self.id,
            "user_id": self.env.uid,
        }
        Ticket = self.env["pos.close.session.user.ticket"]
        existing = Ticket.search([("pos_session_id", "=", self.id)], limit=1)
        if existing:
            existing.write(ticket_vals)
        else:
            Ticket.create(ticket_vals)

        return res

    def process_session_for_dashboard(self, pos_session, pos_bills_default, _total_ef):
        totals_by_employee_date_warehouse = {}

        # Obtener warehouse_id de la sesión POS
        warehouse_id = pos_session.config_id.picking_type_id.warehouse_id.id
        warehouse_name = pos_session.config_id.picking_type_id.warehouse_id.name

        for order in pos_session.order_ids:
            order_date_time = self.convertir_a_hora_ecuador(order.create_date)
            order_date = order_date_time.date()
            employee_id = order.employee_id.id

            # Calcular los totales de esta orden
            order_totals = self.calculate_order_payment_totals(order)

            # La clave ahora incluye warehouse_id para separar registros por almacén
            key = (employee_id, order_date, warehouse_id)
            if key not in totals_by_employee_date_warehouse:
                totals_by_employee_date_warehouse[key] = {
                    "warehouse_id": warehouse_id,
                    "warehouse_name": warehouse_name,
                    "date_order": order_date,
                    "cashier_employee": order.employee_id.name,
                    "employee_id": employee_id,
                    "sale_cash": 0.0,
                    "sale_card": 0.0,
                    "sale_check_transfer": 0.0,
                    "sale_credit": 0.0,
                    "note_credit_cash": 0.0,
                    "note_credit_card": 0.0,
                    "note_credit_check_transfer": 0.0,
                    "note_credit_credit": 0.0,
                    "scope_card": 0.0,
                    "scope_check_transfer": 0.0,
                    "scope_credit": 0.0,
                    "scope_advance": 0.0,
                    "note_credit_scope_card": 0.0,
                    "note_credit_scope_check_transfer": 0.0,
                    "note_credit_scope_credit": 0.0,
                    "retention": 0.0,
                    "advance_cash": 0.0,
                    "note_credit_advance_cash": 0.0,
                    "total_scope": 0.0,
                    "total_cash": 0.0,
                    "counting_cash": 0.0,
                    "missing": 0.0,
                    "surplus": 0.0,
                }

            totals = totals_by_employee_date_warehouse[key]
            for k, v in order_totals.items():
                totals[k] += v

        # Procesar los totales acumulados
        for key, cash_summary_vals in totals_by_employee_date_warehouse.items():
            employee_id, order_date, wh_id = key
            date_pos_sesion = self.convertir_a_hora_ecuador(pos_session.stop_at)
            if order_date == date_pos_sesion.date():
                cash_summary_vals["counting_cash"] = _total_ef or 0.0

            # Buscar registro existente por empleado, fecha Y almacén
            existing_record = self.env["pos.order.dashboard"].search(
                [
                    ("employee_id", "=", employee_id),
                    ("date_order", "=", order_date),
                    ("warehouse_id", "=", wh_id),
                ],
                limit=1,
            )

            if existing_record.exists():
                # Actualizar valores acumulando con lo existente
                for k in [
                    "sale_cash",
                    "sale_card",
                    "sale_check_transfer",
                    "sale_credit",
                    "note_credit_cash",
                    "note_credit_card",
                    "note_credit_check_transfer",
                    "note_credit_credit",
                    "scope_card",
                    "scope_check_transfer",
                    "scope_credit",
                    "scope_advance",
                    "note_credit_scope_card",
                    "note_credit_scope_check_transfer",
                    "note_credit_scope_credit",
                    "retention",
                    "advance_cash",
                    "note_credit_advance_cash",
                    "total_scope",
                    "total_cash",
                    "counting_cash",
                ]:
                    cash_summary_vals[k] += existing_record[k]

            # Calcular diferencia
            difference = (
                    cash_summary_vals["total_cash"] - cash_summary_vals["counting_cash"]
            )
            if difference < 0:
                cash_summary_vals["surplus"] = abs(difference)
                cash_summary_vals["missing"] = 0
            elif difference > 0:
                cash_summary_vals["missing"] = difference
                cash_summary_vals["surplus"] = 0
            else:
                cash_summary_vals["missing"] = 0
                cash_summary_vals["surplus"] = 0

            # Crear o actualizar en dashboard
            if existing_record.exists():
                existing_record.write(cash_summary_vals)
            else:
                self.env["pos.order.dashboard"].create(cash_summary_vals)

        return True

    def _sanitize_for_json(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_for_json(v) for v in obj]
        return obj

    def calculate_order_payment_totals(self, order):
        payment_totals = {
            "sale_cash": 0.0,
            "sale_card": 0.0,
            "sale_check_transfer": 0.0,
            "sale_credit": 0.0,
            "note_credit_cash": 0.0,
            "note_credit_card": 0.0,
            "note_credit_check_transfer": 0.0,
            "note_credit_credit": 0.0,
            "scope_card": 0.0,
            "scope_check_transfer": 0.0,
            "scope_credit": 0.0,
            "scope_advance": 0.0,
            "note_credit_scope_card": 0.0,
            "note_credit_scope_check_transfer": 0.0,
            "note_credit_scope_credit": 0.0,
            "retention": 0.0,
            "advance_cash": 0.0,
            "note_credit_advance_cash": 0.0,
            "total_cash": 0.0,
            "total_scope": 0.0,
        }

        # Identificar los métodos de pago presentes
        payment_methods = [payment.payment_method_id for payment in order.payment_ids]
        is_refunded = order.lines and order.lines[0].refunded_orderline_id

        if len(order.payment_ids) == 1:
            payment = order.payment_ids[0]
            amount = abs(payment.amount) if is_refunded else payment.amount

            if is_refunded:
                if payment.payment_method_id.is_cash_count:
                    payment_totals["note_credit_cash"] += amount
                    payment_totals["total_cash"] -= amount
                elif payment.payment_method_id.code_payment_method == "CREDITO":
                    payment_totals["note_credit_credit"] += amount
                elif payment.payment_method_id.code_payment_method == "TARJETA":
                    payment_totals["note_credit_card"] += amount
                elif payment.payment_method_id.code_payment_method == "CHEQUE/TRANSF":
                    payment_totals["note_credit_check_transfer"] += amount
                elif payment.payment_method_id.code_payment_method == "CTACLIENTE":
                    payment_totals["note_credit_advance_cash"] += amount
            else:
                if payment.payment_method_id.is_cash_count:
                    payment_totals["sale_cash"] += amount
                    payment_totals["total_cash"] += amount
                elif payment.payment_method_id.code_payment_method == "CREDITO":
                    payment_totals["sale_credit"] += amount
                elif payment.payment_method_id.code_payment_method == "TARJETA":
                    payment_totals["sale_card"] += amount
                elif payment.payment_method_id.code_payment_method == "CHEQUE/TRANSF":
                    payment_totals["sale_check_transfer"] += amount
                elif payment.payment_method_id.code_payment_method == "CTACLIENTE":
                    payment_totals["advance_cash"] += amount

        # Caso 2: Orden con múltiples métodos de pago
        elif len(order.payment_ids) > 1:
            first_payment = order.payment_ids[0]
            first_method = first_payment.payment_method_id.code_payment_method
            first_is_cash = first_payment.payment_method_id.is_cash_count

            all_same_method = all(
                (payment.payment_method_id.is_cash_count and first_is_cash)
                or (
                        not payment.payment_method_id.is_cash_count
                        and not first_is_cash
                        and payment.payment_method_id.code_payment_method == first_method
                )
                for payment in order.payment_ids
            )

            if all_same_method:
                payment = order.payment_ids[0]
                positive_payments = [payment.amount for payment in order.payment_ids]
                payments_for_refund = [
                    abs(payment.amount) for payment in order.payment_ids
                ]

                if is_refunded:
                    if payment.payment_method_id.is_cash_count:
                        payment_totals["note_credit_cash"] += sum(payments_for_refund)
                        payment_totals["total_cash"] -= sum(payments_for_refund)
                    elif payment.payment_method_id.code_payment_method == "CREDITO":
                        payment_totals["note_credit_credit"] += sum(payments_for_refund)
                    elif payment.payment_method_id.code_payment_method == "TARJETA":
                        payment_totals["note_credit_card"] += sum(payments_for_refund)
                    elif (
                            payment.payment_method_id.code_payment_method == "CHEQUE/TRANSF"
                    ):
                        payment_totals["note_credit_check_transfer"] += sum(
                            payments_for_refund
                        )
                    elif payment.payment_method_id.code_payment_method == "CTACLIENTE":
                        payment_totals["note_credit_advance_cash"] += sum(
                            payments_for_refund
                        )
                else:
                    if payment.payment_method_id.is_cash_count:
                        payment_totals["sale_cash"] += sum(positive_payments)
                        payment_totals["total_cash"] += sum(positive_payments)
                    elif payment.payment_method_id.code_payment_method == "CREDITO":
                        payment_totals["sale_credit"] += sum(positive_payments)
                    elif payment.payment_method_id.code_payment_method == "TARJETA":
                        payment_totals["sale_card"] += sum(positive_payments)
                    elif (
                            payment.payment_method_id.code_payment_method == "CHEQUE/TRANSF"
                    ):
                        payment_totals["sale_check_transfer"] += sum(positive_payments)
                    elif payment.payment_method_id.code_payment_method == "CTACLIENTE":
                        payment_totals["advance_cash"] += sum(positive_payments)

            else:
                cash_amount = 0.0
                has_cash = any(pm.is_cash_count for pm in payment_methods)

                for payment in order.payment_ids:
                    if payment.payment_method_id.is_cash_count:
                        cash_sum = payment.amount
                        cash_amount = abs(cash_sum) if is_refunded else cash_sum

                        if is_refunded:
                            payment_totals["total_cash"] -= cash_amount
                            payment_totals["total_scope"] -= cash_amount
                        else:
                            payment_totals["total_scope"] += cash_amount
                            payment_totals["total_cash"] += cash_amount

                for payment in order.payment_ids:
                    if not payment.payment_method_id.is_cash_count and has_cash:
                        amount_cash = sum(
                            payment.amount
                            for payment in order.payment_ids
                            if payment.payment_method_id.is_cash_count
                        )
                        amount_cash = abs(amount_cash) if is_refunded else amount_cash
                        amount = abs(payment.amount) if is_refunded else payment.amount
                        if is_refunded:
                            if (
                                    payment.payment_method_id.code_payment_method
                                    == "CREDITO"
                            ):
                                payment_totals[
                                    "note_credit_scope_credit"
                                ] += amount_cash
                                payment_totals["note_credit_credit"] += amount
                            elif (
                                    payment.payment_method_id.code_payment_method
                                    == "TARJETA"
                            ):
                                payment_totals["note_credit_scope_card"] += amount_cash
                                payment_totals["note_credit_card"] += amount
                            elif (
                                    payment.payment_method_id.code_payment_method
                                    == "CHEQUE/TRANSF"
                            ):
                                payment_totals[
                                    "note_credit_scope_check_transfer"
                                ] += amount_cash
                                payment_totals["note_credit_check_transfer"] += amount
                        else:
                            if (
                                    payment.payment_method_id.code_payment_method
                                    == "CREDITO"
                            ):
                                payment_totals["scope_credit"] += amount_cash
                                payment_totals["sale_credit"] += amount
                            elif (
                                    payment.payment_method_id.code_payment_method
                                    == "TARJETA"
                            ):
                                payment_totals["scope_card"] += amount_cash
                                payment_totals["sale_card"] += amount
                            elif (
                                    payment.payment_method_id.code_payment_method
                                    == "CHEQUE/TRANSF"
                            ):
                                payment_totals["scope_check_transfer"] += amount_cash
                                payment_totals["sale_check_transfer"] += amount
                            elif (
                                    payment.payment_method_id.code_payment_method
                                    == "CTACLIENTE"
                            ):
                                payment_totals["scope_advance"] += amount_cash
                                payment_totals["advance_cash"] += amount

        return payment_totals

    def convertir_a_hora_ecuador(self, hora_utc):
        # Zona horaria de Ecuador
        ecuador_tz = pytz.timezone("America/Guayaquil")
        utc_tz = pytz.utc
        utc_time = utc_tz.localize(hora_utc)
        whitout_time_zone = utc_time.astimezone(ecuador_tz)
        return whitout_time_zone.replace(tzinfo=None)


class ReportUserTicket(models.AbstractModel):
    _name = "report.pos_close_session.report_user_ticket"
    _description = "Reporte cierre POS usuario"

    @api.model
    def _get_report_values(self, docids, data=None):
        # Cargamos el ticket (el record de pos.close.session.user.ticket)
        Ticket = self.env["pos.close.session.user.ticket"]
        docs = Ticket.browse(docids)
        doc = docs[0]

        # 1) Calculamos los totales de pagos (efectivo, tarjeta…)
        total_cash = total_card = total_cheque = total_credit = 0.0
        for order in doc.pos_session_id.order_ids:
            for payment in order.payment_ids:
                code = payment.payment_method_id.code_payment_method or ""
                amt = payment.amount
                if payment.payment_method_id.is_cash_count:
                    total_cash += amt
                elif code == "TARJETA":
                    total_card += amt
                elif code == "CHEQUE/TRANSF":
                    total_cheque += amt
                elif code == "CREDITO":
                    total_credit += amt

        # 2) Obtenemos el JSON de los billetes/monedas
        Bills = self.env["pos.close.session.bills"]
        bill_record = Bills.search(
            [("pos_session_id", "=", doc.pos_session_id.id)], limit=1
        )
        bills_data = bill_record.bills_data or {}

        # 3) Cargamos missing / surplus desde los valores guardados en el ticket
        try:
            vals = json.loads(doc.values or "{}")
        except Exception:
            vals = {}
        missing = vals.get("missing", 0.0)
        surplus = vals.get("surplus", 0.0)

        return {
            "doc_ids": docids,
            "doc_model": "pos.close.session.user.ticket",
            "docs": docs,
            "sale_cash": total_cash,
            "sale_card": total_card,
            "sale_check_transfer": total_cheque,
            "sale_credit": total_credit,
            "bills_data": bills_data,
            "missing": missing,
            "surplus": surplus,
        }


class PosCloseSessionUserTicket(models.Model):
    _name = "pos.close.session.user.ticket"
    _description = "Pos Close Session User Ticket"
    _order = "create_date desc"

    employee = fields.Char(string="Dependiente", required=True)
    point_of_sale = fields.Char(string="Punto de venta", required=True)
    values = fields.Char(string="Datos", required=True)
    pos_session_id = fields.Many2one("pos.session", string="Sesión", required=False)
    user_id = fields.Many2one(
        "res.users", string="Usuario", default=lambda self: self.env.user
    )

    def action_download_pdf(self):
        self.ensure_one()
        return {
            "type": "ir.actions.report",
            "report_name": "pos_close_session.report_user_ticket",
            "report_type": "qweb-pdf",
            "res_id": self.id,
        }
