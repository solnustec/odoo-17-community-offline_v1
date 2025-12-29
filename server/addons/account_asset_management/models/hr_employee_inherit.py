from odoo import models, fields


class HREmployee(models.Model):
    _inherit = "hr.employee"

    # Asignaciones iniciales donde este empleado fue custodio
    asset_assignment_ids = fields.One2many(
        "asset.assignment",
        "custodian_id",
        string="Asignaciones Iniciales",
    )

    # Transferencias donde fue custodio anterior
    asset_transfer_from_ids = fields.One2many(
        "asset.transfer",
        "custodian_from_id",
        string="Transferencias Entregadas",
    )

    # Transferencias donde fue custodio nuevo
    asset_transfer_to_ids = fields.One2many(
        "asset.transfer",
        "custodian_to_id",
        string="Transferencias Recibidas",
    )
