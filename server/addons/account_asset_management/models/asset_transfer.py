# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AssetTransfer(models.Model):
    _name = "asset.transfer"
    _description = "Transferencias de Custodio de Activos"
    _order = "transfer_date desc"

    asset_id = fields.Many2one(
        "account.asset",
        string="Activo",
        required=True,
        ondelete="cascade",
        index=True,
    )

    custodian_from_id = fields.Many2one(
        "hr.employee",
        string="Custodio Anterior",
        readonly=True,
        index=True,
    )
    custodian_to_id = fields.Many2one(
        "hr.employee",
        string="Nuevo Custodio",
        required=True,
        index=True,
    )

    transfer_date = fields.Date(
        string="Fecha de Transferencia",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    note = fields.Text(string="Observaciones")

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    signed_by_from = fields.Boolean(
        string="Firmado por Custodio Anterior",
        default=False,
        readonly=True,
    )
    signed_by_to = fields.Boolean(
        string="Firmado por Nuevo Custodio",
        default=False,
        readonly=True,
    )
    signed_by_admin = fields.Boolean(
        string="Firmado por Administrador",
        default=False,
        readonly=True,
    )

    admin_employee_id = fields.Many2one(
        "hr.employee",
        string="Administrador que firma",
        readonly=True,
    )

    # ------------------------------
    # Onchange: precargar custodio anterior
    # ------------------------------
    @api.onchange("asset_id")
    def _onchange_asset_id(self):
        if not self.asset_id:
            self.custodian_from_id = False
            return

        last_transfer = self.env["asset.transfer"].search(
            [("asset_id", "=", self.asset_id.id)],
            order="transfer_date desc, id desc",
            limit=1,
        )
        if last_transfer and last_transfer.custodian_to_id:
            self.custodian_from_id = last_transfer.custodian_to_id
        else:
            self.custodian_from_id = self.asset_id.asset_custodian_id or False

    # ------------------------------
    # Validación: custodian_from_id != custodian_to_id
    # ------------------------------
    def _check_custodians(self, vals):
        """Evita que el custodio anterior y nuevo sean el mismo."""
        from_id = vals.get("custodian_from_id") or self.custodian_from_id.id
        to_id = vals.get("custodian_to_id") or self.custodian_to_id.id
        if from_id and to_id and from_id == to_id:
            raise UserError(_("El custodio anterior y el nuevo custodio no pueden ser el mismo."))

    # ------------------------------
    # Create con validación
    # ------------------------------
    @api.model
    def create(self, vals):
        asset = self.env["account.asset"].browse(vals.get("asset_id"))

        # Validar asignación inicial confirmada
        assignment = self.env["asset.assignment"].search(
            [("asset_id", "=", asset.id)], order="assign_date asc", limit=1
        )
        if not assignment or assignment.state != "confirmed":
            raise UserError(
                _("El activo aún no tiene una asignación confirmada por el custodio. No se puede transferir.")
            )

        # Precargar custodio anterior si no viene
        if asset and not vals.get("custodian_from_id"):
            if asset.asset_custodian_id:
                vals["custodian_from_id"] = asset.asset_custodian_id.id

        # Validar que no se transfiera al mismo custodio
        self._check_custodians(vals)

        # Guardar admin firmante
        current_employee = self.env.user.employee_id
        if current_employee:
            vals["admin_employee_id"] = current_employee.id
            vals["signed_by_admin"] = True

        return super().create(vals)

    # ------------------------------
    # Write con validación
    # ------------------------------
    def write(self, vals):
        self._check_custodians(vals)
        return super().write(vals)

    # ------------------------------
    # Firmar transferencia
    # ------------------------------
    def action_sign_transfer(self):
        self.ensure_one()

        current_employee = self.env.user.employee_id
        if not current_employee:
            raise UserError(_("Tu usuario no está vinculado a un empleado en Odoo."))

        if self.custodian_to_id == current_employee:
            self.signed_by_to = True
        elif self.custodian_from_id == current_employee:
            self.signed_by_from = True
        else:
            raise UserError(_("Este empleado no está autorizado para firmar esta transferencia."))

        # Solo si ambos firman, actualizar custodio
        if self.signed_by_from and self.signed_by_to:
            self.asset_id.asset_custodian_id = self.custodian_to_id


class AccountAsset(models.Model):
    _inherit = "account.asset"

    transfer_ids = fields.One2many(
        "asset.transfer",
        "asset_id",
        string="Historial de Transferencias",
    )

    asset_custodian_id = fields.Many2one(
        "hr.employee",
        string="Custodio (Empleado)",
        index=True,
    )
