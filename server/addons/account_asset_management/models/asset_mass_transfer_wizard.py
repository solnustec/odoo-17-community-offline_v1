# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AssetMassTransferWizard(models.TransientModel):
    _name = "asset.mass.transfer.wizard"
    _description = "Wizard para transferencias masivas de activos"

    asset_ids = fields.Many2many(
        "account.asset",
        string="Activos Seleccionados",
        readonly=True,
    )

    new_custodian_id = fields.Many2one(
        "hr.employee",
        string="Nuevo Custodio",
        required=True,
    )

    transfer_date = fields.Date(
        string="Fecha de Transferencia",
        required=True,
        default=fields.Date.context_today,
    )

    note = fields.Text(string="Observaciones")

    @api.model
    def default_get(self, fields_list):
        """ Cargar automáticamente los activos seleccionados desde active_ids """
        res = super().default_get(fields_list)
        active_ids = self.env.context.get("active_ids")
        if active_ids:
            res["asset_ids"] = [(6, 0, active_ids)]
        return res

    def action_confirm_transfer(self):
        """ Confirmar la transferencia masiva de activos """
        if not self.asset_ids:
            raise UserError(_("No se han seleccionado activos."))
        assets_to_transfer = self.asset_ids

        for asset in assets_to_transfer:
            self.env["asset.transfer"].create({
                "asset_id": asset.id,
                "custodian_from_id": asset.asset_custodian_id.id if asset.asset_custodian_id else False,
                "custodian_to_id": self.new_custodian_id.id,
                "transfer_date": self.transfer_date,
                "note": self.note,
            })

            asset.asset_custodian_id = self.new_custodian_id

        return {
            "type": "ir.actions.act_window",
            "res_model": "asset.transfer",
            "view_mode": "tree,form",
            "name": _("Transferencias Generadas"),
            "domain": [("asset_id", "in", self.asset_ids.ids)],
        }
