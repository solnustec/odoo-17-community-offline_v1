# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class AssetAssignment(models.Model):
    _name = "asset.assignment"
    _description = "Asignaciones iniciales de activos"
    _order = "assign_date desc"

    asset_id = fields.Many2one(
        "account.asset",
        string="Activo",
        required=True,
        ondelete="cascade",
        index=True,
    )

    custodian_id = fields.Many2one(
        "hr.employee",
        string="Custodio",
        required=True,
        index=True,
        help="Empleado responsable inicial de este activo.",
    )

    assign_date = fields.Date(
        string="Fecha de Asignación",
        required=True,
        default=fields.Date.context_today,
    )

    note = fields.Text(string="Observaciones")

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    signed_by_custodian = fields.Boolean(
        string="Firmado por Custodio",
        default=False,
        readonly=True,
    )

    state = fields.Selection(
        [
            ("pending", "Pendiente de Firma"),
            ("confirmed", "Confirmado"),
        ],
        string="Estado",
        default="pending",
    )

    # =============================
    # Acción: firmar asignación
    # =============================
    def action_sign_assignment(self):
        for rec in self:
            rec.signed_by_custodian = True
            rec.state = "confirmed"
