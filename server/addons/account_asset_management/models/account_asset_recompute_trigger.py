# Copyright 2009-2018 Noviat
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountAssetRecomputeTrigger(models.Model):
    _name = "account.asset.recompute.trigger"
    _description = "Asset table recompute triggers"

    reason = fields.Char(required=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True)
    date_trigger = fields.Datetime(
        "Fecha de Trigger",
        readonly=True,
        help="Fecha del evento que genera la necesidad de recalcular las tablas de activos.",
    )
    date_completed = fields.Datetime("Fecha de finalización", readonly=True)
    state = fields.Selection(
        selection=[("open", "Abierto"), ("done", "Completado")],
        default="open",
        readonly=True,
        string="Estado",
    )
