# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta
import pytz
from odoo import api, models, fields

GUAYAQUIL_TZ = pytz.timezone("America/Guayaquil")


class ReportPosDailyWarehouseTicket(models.AbstractModel):
    _name = "report.consolidated_pos.pos_daily_warehouse_ticket"
    _description = "Ticket Ventas del Día por Bodega"

    @staticmethod
    def _local_day_bounds_utc(day_local):
        start_local = GUAYAQUIL_TZ.localize(datetime.combine(day_local, time(0, 0, 0)))
        next_local = start_local + timedelta(days=1)
        return start_local.astimezone(pytz.utc), next_local.astimezone(pytz.utc)

    def _compute_kpis(self, warehouse, report_date):
        start_utc, next_utc = self._local_day_bounds_utc(report_date)
        domain = [
            ("state", "in", ["paid", "invoiced", "done"]),
            ("config_id.picking_type_id.warehouse_id", "=", warehouse.id),
            ("date_order", ">=", start_utc),
            ("date_order", "<", next_utc),
        ]
        orders = self.env["pos.order"].sudo().search(domain)

        sums = dict(cash=0.0, card=0.0, chk_trans=0.0, credit=0.0, total=0.0)
        counts = dict(cash=0, card=0, chk_trans=0, credit=0)
        for o in orders.sudo():
            sums["total"] += o.amount_total
            for p in o.payment_ids.sudo():
                amt = p.amount
                pm = p.payment_method_id.sudo()
                code = (pm.code_payment_method or "").strip()
                if pm.is_cash_count:
                    sums["cash"] += amt;
                    counts["cash"] += 1
                elif code == "TARJETA":
                    sums["card"] += amt;
                    counts["card"] += 1
                elif code == "CHEQUE/TRANSF":
                    sums["chk_trans"] += amt;
                    counts["chk_trans"] += 1
                elif code == "CREDITO":
                    sums["credit"] += amt;
                    counts["credit"] += 1
        return orders, sums, counts

    def _sum_bills_and_coins(self, warehouse, report_date):
        if "pos.close.session.bills" not in self.env:
            return None

        start_utc, next_utc = self._local_day_bounds_utc(report_date)
        sessions = self.env["pos.session"].sudo().search([
            ("config_id.picking_type_id.warehouse_id", "=", warehouse.id),
            ("stop_at", ">=", start_utc),
            ("stop_at", "<", next_utc),
        ])

        if not sessions:
            return None

        acc = {
            "b100": 0, "b50": 0, "b20": 0, "b10": 0, "b5": 0, "b1": 0,
            "m100": 0, "m50": 0, "m25": 0, "m10": 0, "m5": 0, "m1": 0,
        }

        Bills = self.env["pos.close.session.bills"].sudo()
        found_any = False
        for s in sessions:
            b = Bills.search([("pos_session_id", "=", s.id)], limit=1)
            if b and b.bills_data:
                found_any = True
                data = b.bills_data
                for k in acc.keys():
                    acc[k] += float(data.get(k, 0) or 0)

        if not found_any:
            return None

        # Totales en USD
        total_bills = (
                acc["b100"] * 100 + acc["b50"] * 50 + acc["b20"] * 20 +
                acc["b10"] * 10 + acc["b5"] * 5 + acc["b1"] * 1
        )
        total_coins = (
                acc["m100"] * 1 + acc["m50"] * 0.50 + acc["m25"] * 0.25 +
                acc["m10"] * 0.10 + acc["m5"] * 0.05 + acc["m1"] * 0.01
        )

        # **Conteo total** de piezas
        total_bills_count = acc["b100"] + acc["b50"] + acc["b20"] + acc["b10"] + acc["b5"] + acc["b1"]
        total_coins_count = acc["m100"] + acc["m50"] + acc["m25"] + acc["m10"] + acc["m5"] + acc["m1"]

        acc["total_bills"] = total_bills
        acc["total_coins"] = total_coins
        acc["total_bills_count"] = total_bills_count
        acc["total_coins_count"] = total_coins_count
        acc["total_count"] = total_bills_count + total_coins_count

        return acc

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["pos.daily.warehouse.report"].browse(docids).sudo()
        lines = []
        now_local = fields.Datetime.context_timestamp(self, fields.Datetime.now())

        for r in docs:
            warehouse = r.warehouse_id.sudo()
            company = warehouse.company_id.sudo()

            # KPIs del POS (esperado por sistema)
            orders, sums, counts = self._compute_kpis(warehouse, r.report_date)

            # Billetes/monedas contados por el cajero (puede ser None)
            bills = self._sum_bills_and_coins(warehouse, r.report_date)

            # ---- Diferencias contado vs esperado ----
            counted_cash = 0.0
            if bills:
                counted_cash = float(bills.get("total_bills", 0) or 0.0) + \
                               float(bills.get("total_coins", 0) or 0.0)

            expected_cash = float(sums.get("cash", 0.0) or 0.0)

            # faltante / sobrante
            diff = round(counted_cash - expected_cash, 2)
            sobrante = max(0.0, diff)
            faltante = max(0.0, -diff)

            # Total a depositar basado en lo realmente contado
            total_deposit = counted_cash + float(sums.get("card", 0.0) or 0.0) + \
                            float(sums.get("chk_trans", 0.0) or 0.0)

            lines.append({
                "rec": r,
                "company": company,
                "warehouse": warehouse,
                "date_local": r.report_date,
                "printed_at": now_local,
                "sums": sums,
                "counts": counts,
                "orders_count": len(orders),
                "bills": bills,  # None si no hay datos de cierre
                "faltante": faltante,
                "sobrante": sobrante,
                "total_deposit": total_deposit,
            })

        return {
            "doc_ids": docids,
            "doc_model": "pos.daily.warehouse.report",
            "docs": docs,
            "lines": lines,
        }

