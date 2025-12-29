# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AssetMassAssignmentWizard(models.TransientModel):
    _name = "asset.mass.assignment.wizard"
    _description = "Wizard para asignación masiva de activos"

    asset_ids = fields.Many2many(
        "account.asset",
        string="Activos Seleccionados",
        readonly=True,
    )

    custodian_id = fields.Many2one(
        "hr.employee",
        string="Custodio",
        required=True,
    )

    assign_date = fields.Date(
        string="Fecha de Asignación",
        required=True,
        default=fields.Date.context_today,
    )

    note = fields.Text(string="Observaciones")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get("active_ids")
        if active_ids:
            res["asset_ids"] = [(6, 0, active_ids)]
        return res

    def action_confirm_assignment(self):
        """Crear asignaciones masivas (pendientes de firma del custodio)."""
        if not self.asset_ids:
            raise UserError(_("No se han seleccionado activos."))

        # Validar que ninguno tenga custodio ya asignado
        activos_con_custodio = self.asset_ids.filtered(lambda a: a.asset_custodian_id)
        if activos_con_custodio:
            raise UserError(_(
                "Los siguientes activos ya tienen custodio asignado:\n%s"
            ) % "\n".join(activos_con_custodio.mapped("name")))

        for asset in self.asset_ids:
            # Crear asignación inicial en estado pendiente
            self.env["asset.assignment"].create({
                "asset_id": asset.id,
                "custodian_id": self.custodian_id.id,
                "assign_date": self.assign_date,
                "note": self.note,
                "state": "pending",
                "signed_by_custodian": False,
            })
            # Actualizar custodio en el activo
            asset.asset_custodian_id = self.custodian_id

        return {
            "type": "ir.actions.act_window",
            "res_model": "asset.assignment",
            "view_mode": "tree,form",
            "name": _("Asignaciones Generadas"),
            "domain": [("asset_id", "in", self.asset_ids.ids)],
        }
