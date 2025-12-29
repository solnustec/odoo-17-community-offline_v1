# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta
import pytz
from odoo import models, fields, api, _
from odoo.exceptions import UserError

GUAYAQUIL_TZ = pytz.timezone("America/Guayaquil")


class PosDailyWarehouseReport(models.Model):
    _name = "pos.daily.warehouse.report"
    _description = "POS Daily Sales by Warehouse (Local Day)"
    _order = "report_date desc, warehouse_id"

    # ---------------- Campos ----------------
    report_date = fields.Date(
        string="Report Date (Local)",
        required=True,
        default=lambda s: fields.Date.context_today(s),
    )

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        index=True,
        default=lambda self: self._default_warehouse_id(),
    )

    # Selector seguro (NO almacenado)
    warehouse_selector = fields.Selection(
        selection="_get_warehouse_selection",
        string="Warehouse",
        compute="_compute_warehouse_selector",
        inverse="_inverse_warehouse_selector",
        compute_sudo=True,
        store=False,
        help="Safe selector that avoids name_search; sets warehouse_id.",
    )

    # Nombre seguro para listas
    warehouse_name = fields.Char(
        string="Warehouse (safe)",
        compute="_compute_warehouse_name",
        compute_sudo=True,
        store=False,
    )

    # KPIs
    sale_cash = fields.Monetary(string="Cash", currency_field="currency_id", default=0.0)
    sale_card = fields.Monetary(string="Card", currency_field="currency_id", default=0.0)
    sale_check_transfer = fields.Monetary(string="Cheque/Transfer", currency_field="currency_id", default=0.0)
    sale_credit = fields.Monetary(string="Credit", currency_field="currency_id", default=0.0)
    orders_count = fields.Integer(string="Orders", default=0)
    total_amount = fields.Monetary(string="Total Amount", currency_field="currency_id", default=0.0)

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.sudo().currency_id.id,
        readonly=True,
    )

    _sql_constraints = [
        ("unique_day_warehouse", "unique(report_date, warehouse_id)", "One row per day and warehouse.")
    ]

    # ---------------- Defaults/Helpers ----------------
    @api.model
    def _default_warehouse_id(self):
        """Warehouse por defecto (primero que exista)."""
        wh = self.env["stock.warehouse"].sudo().search([], limit=1)
        return wh.id if wh else False

    @staticmethod
    def _local_day_bounds_utc(day_local):
        start_local = GUAYAQUIL_TZ.localize(datetime.combine(day_local, time(0, 0, 0)))
        next_local = start_local + timedelta(days=1)
        return start_local.astimezone(pytz.utc), next_local.astimezone(pytz.utc)

    # ---------------- Selector seguro ----------------
    @api.model
    def _get_warehouse_selection(self):
        warehouses = self.env["stock.warehouse"].sudo().search([], order="name")
        return [(str(w.id), w.display_name) for w in warehouses]

    def _compute_warehouse_selector(self):
        for rec in self:
            wid = rec.warehouse_id.id
            rec.warehouse_selector = str(wid) if wid else False

    def _inverse_warehouse_selector(self):
        # Inverse se usa en import/escrituras programáticas
        for rec in self:
            if rec.warehouse_selector:
                wid = int(rec.warehouse_selector)
                rec.warehouse_id = rec.env["stock.warehouse"].sudo().browse(wid)
            else:
                rec.warehouse_id = False

    @api.onchange("warehouse_selector")
    def _onchange_warehouse_selector(self):
        # Onchange garantiza que en formulario se fije warehouse_id ANTES del create
        for rec in self:
            if rec.warehouse_selector:
                wid = int(rec.warehouse_selector)
                rec.warehouse_id = rec.env["stock.warehouse"].sudo().browse(wid)
            else:
                rec.warehouse_id = False

    def _compute_warehouse_name(self):
        for rec in self:
            rec.warehouse_name = rec.warehouse_id.sudo().display_name if rec.warehouse_id else False

    # ---------------- Create/Write blindados ----------------
    @api.model
    def create(self, vals):
        # Mapear selector → FK si viene del cliente
        ws = vals.pop("warehouse_selector", False)
        if ws and not vals.get("warehouse_id"):
            vals["warehouse_id"] = int(ws)

        # Si aún no viene warehouse_id, aplicar default aquí mismo
        if not vals.get("warehouse_id"):
            wid = self._default_warehouse_id()
            if not wid:
                # Sin warehouse en la BD: no se puede crear
                raise UserError(_("No hay almacenes configurados. Cree al menos uno."))
            vals["warehouse_id"] = wid

        return super().create(vals)

    def write(self, vals):
        # Mapear selector → FK si alguien intenta escribir con el selector
        ws = vals.pop("warehouse_selector", False)
        if ws and not vals.get("warehouse_id"):
            vals["warehouse_id"] = int(ws)
        return super().write(vals)

    # ---------------- Cálculo principal ----------------
    @api.model
    def _compute_totals_for_warehouse_day(self, warehouse, day_local):
        if not warehouse:
            return {
                "sale_cash": 0.0, "sale_card": 0.0, "sale_check_transfer": 0.0, "sale_credit": 0.0,
                "orders_count": 0, "total_amount": 0.0,
            }

        start_utc, next_utc = self._local_day_bounds_utc(day_local)

        domain_orders = [
            ("state", "in", ["paid", "invoiced", "done"]),
            ("config_id.picking_type_id.warehouse_id", "=", warehouse.id),
            ("date_order", ">=", start_utc),
            ("date_order", "<", next_utc),
        ]
        orders = self.env["pos.order"].sudo().search(domain_orders)

        sale_cash = sale_card = sale_check_transfer = sale_credit = 0.0
        total_amount = 0.0
        orders_count = len(orders)

        for order in orders.sudo():
            total_amount += order.amount_total
            for payment in order.payment_ids.sudo():
                amt = payment.amount
                pm = payment.payment_method_id.sudo()
                code = (pm.code_payment_method or "").strip()
                if pm.is_cash_count:
                    sale_cash += amt
                elif code == "TARJETA":
                    sale_card += amt
                elif code == "CHEQUE/TRANSF":
                    sale_check_transfer += amt
                elif code == "CREDITO":
                    sale_credit += amt

        return {
            "sale_cash": sale_cash,
            "sale_card": sale_card,
            "sale_check_transfer": sale_check_transfer,
            "sale_credit": sale_credit,
            "orders_count": orders_count,
            "total_amount": total_amount,
        }

    # ---------------- Acciones ----------------
    def action_rebuild(self):
        for rec in self:
            vals = self._compute_totals_for_warehouse_day(rec.sudo().warehouse_id, rec.report_date)
            rec.sudo().write(vals)
        return True

    @api.model
    def action_build_today_all_warehouses(self):
        today_local = fields.Date.context_today(self)
        warehouses = self.env["stock.warehouse"].sudo().search([])
        created = self.env["pos.daily.warehouse.report"]
        for wh in warehouses:
            existing = self.sudo().search(
                [("report_date", "=", today_local), ("warehouse_id", "=", wh.id)], limit=1
            )
            vals = {"report_date": today_local, "warehouse_id": wh.id}
            vals.update(self._compute_totals_for_warehouse_day(wh, today_local))
            if existing:
                existing.sudo().write(vals)
            else:
                created |= self.sudo().create(vals)
        action = self.env.ref("consolidated_pos.action_pos_daily_warehouse_report").sudo().read()[0]
        action["domain"] = [("report_date", "=", today_local)]
        return action

    def action_print_ticket(self):
        self.ensure_one()
        return self.env.ref(
            "consolidated_pos.action_report_pos_daily_warehouse_ticket"
        ).report_action(self)
