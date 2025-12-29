# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import datetime
from odoo import api, fields, models
from datetime import datetime, time


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    expiration_date_date = fields.Date(
        string="Fecha de Caducidad",
        compute="_compute_expiration_date_date",
        inverse="_inverse_expiration_date_date",
        store=True
    )

    @api.onchange("expiration_date_date")
    def _onchange_expiration_date_date(self):
        for r in self:
            if r.expiration_date_date:
                r.expiration_date = datetime.combine(r.expiration_date_date, time.min)
                r._compute_expiration_date()
            else:
                r.expiration_date = False
                r._compute_expiration_date()

    @api.depends("expiration_date")
    def _compute_expiration_date_date(self):
        for record in self:
            if record.expiration_date:
                record.expiration_date_date = record.expiration_date.date()
            else:
                record.expiration_date_date = False

    def _inverse_expiration_date_date(self):
        for record in self:
            if record.expiration_date_date:
                record.expiration_date = datetime.combine(
                    record.expiration_date_date, time.min
                )
            else:
                record.expiration_date = False

    def _prepare_new_lot_vals(self):
        vals = super()._prepare_new_lot_vals()
        if self.expiration_date:
            vals['expiration_date'] = self.expiration_date
        return vals