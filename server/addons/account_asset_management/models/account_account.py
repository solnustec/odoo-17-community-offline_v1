# Copyright 2009-2017 Noviat
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountAccount(models.Model):
    _inherit = "account.account"

    asset_profile_id = fields.Many2one(
        comodel_name="account.asset.profile",
        string="Perfil del Activo",
        check_company=True,
        help="Perfil del activo predeterminado al crear líneas de factura con esta cuenta.",
    )

    @api.constrains("asset_profile_id")
    def _check_asset_profile(self):
        for account in self:
            if (
                account.asset_profile_id
                and account.asset_profile_id.account_asset_id != account
            ):
                raise ValidationError(
                    _(
                        "La cuenta de activo definida en el perfil de activo "
                        "debe ser igual a la cuenta."
                    )
                )
