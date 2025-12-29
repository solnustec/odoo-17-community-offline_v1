
import logging

from odoo import models, api, fields
from odoo.exceptions import UserError
from datetime import datetime, time

_logger = logging.getLogger(__name__)


class StockLot(models.Model):
    _inherit = 'stock.lot'

    expiration_date_date = fields.Date(
        string="Fecha de caducidad", tracking=True
    )
    removal_date_date = fields.Date(
        string="Fecha de remoción", tracking=True
    )
    use_date_date = fields.Date(
        string="Fecha de consumo preferente", tracking=True
    )
    alert_date_date = fields.Date(
        string="Fecha de alerta", tracking=True
    )

    def _dt_to_date_min(self, dt):
        if not dt:
            return False
        if isinstance(dt, str):
            try:
                dt = fields.Datetime.from_string(dt)
            except Exception:
                return False
        return dt.date()

    @api.model
    def create(self, vals):
        vals = vals.copy()
        if vals.get('expiration_date'):
            vals['expiration_date_date'] = self._dt_to_date_min(vals['expiration_date'])
        if vals.get('removal_date'):
            vals['removal_date_date'] = self._dt_to_date_min(vals['removal_date'])
        if vals.get('use_date'):
            vals['use_date_date'] = self._dt_to_date_min(vals['use_date'])
        if vals.get('alert_date'):
            vals['alert_date_date'] = self._dt_to_date_min(vals['alert_date'])
        res = super().create(vals)
        res._compute_dates()

        return res

    def write(self, vals):
        vals = vals.copy()
        if 'expiration_date' in vals:
            vals['expiration_date_date'] = self._dt_to_date_min(vals['expiration_date'])
        if 'removal_date' in vals:
            vals['removal_date_date'] = self._dt_to_date_min(vals['removal_date'])
        if 'use_date' in vals:
            vals['use_date_date'] = self._dt_to_date_min(vals['use_date'])
        if 'alert_date' in vals:
            vals['alert_date_date'] = self._dt_to_date_min(vals['alert_date'])
        res = super().write(vals)
        return res



    @api.onchange(
        'expiration_date_date', 'removal_date_date',
        'use_date_date', 'alert_date_date'
    )
    def _onchange_sync_date_fields(self):
        for record in self:
            if record.expiration_date_date:
                record.expiration_date = datetime.combine(record.expiration_date_date, time.min)
                record._compute_dates()


    @api.onchange(
        'expiration_date', 'alert_date',
        'removal_date','use_date'
    )
    def _onchange_sync_datetime_fields(self):
        for record in self:
            if record.removal_date:
                dt = record.removal_date.replace(hour=0, minute=0, second=0, microsecond=0)
                record.removal_date_date = dt.date()

            if record.use_date:
                dt = record.use_date.replace(hour=0, minute=0, second=0, microsecond=0)
                record.use_date_date = dt.date()

            if record.alert_date:
                dt = record.alert_date.replace(hour=0, minute=0, second=0, microsecond=0)
                record.alert_date_date = dt.date()