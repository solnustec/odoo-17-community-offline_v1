# Copyright 2009-2018 Noviat
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountAssetProfile(models.Model):
    _name = "account.asset.profile"
    _inherit = "analytic.mixin"
    _check_company_auto = True
    _description = "Perfil de activo"
    _order = "name"

    name = fields.Char(size=64, required=True, index=True)
    note = fields.Text()
    account_asset_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        string="Cuenta de activo",
        check_company=True,
        required=True,
    )
    account_depreciation_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        string="Cuenta de depreciación",
        check_company=True,
        required=True,
    )
    account_expense_depreciation_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        string="Cuenta de gasto por depreciación",
        check_company=True,
        required=True,
    )
    account_plus_value_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
        string="Cuenta de plusvalía",
    )
    account_min_value_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
        string="Cuenta de minusvalía",
    )
    account_residual_value_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
        string="Cuenta de valor residual",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        string="Diario",
        check_company=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self._default_company_id(),
    )
    group_ids = fields.Many2many(
        comodel_name="account.asset.group",
        relation="account_asset_profile_group_rel",
        column1="profile_id",
        column2="group_id",
        check_company=True,
        string="Grupos de activos",
    )
    method = fields.Selection(
        selection=lambda self: self._selection_method(),
        string="Método de cálculo",
        required=True,
        help="Elija el método que desea utilizar para calcular las líneas de depreciación.\n"
        "  * Lineal: se calcula sobre la base de: "
        "Base de depreciación / Número de depreciaciones. "
        "Base de depreciación = Valor de compra - Valor residual.\n"
        "  * Lineal-Límite: lineal hasta el valor residual. "
        "Base de amortización = valor de compra.\n"
        "  * Degresiva: calculada sobre la base de: "
        "Valor residual * factor degresivo.\n"
        "  * Degresiva-lineal (solo para método temporal = año): "
        "La amortización decreciente se convierte en lineal cuando la amortización lineal anual "
        "supera la amortización decreciente anual.\n"
        "   * Decrescente-Límite: Decrescente hasta el valor residual. "
        "La base de amortización es igual al valor del activo.",
        default="linear",
    )
    method_number = fields.Integer(
        string="Número de años",
        help="Cantidad de años para depreciar el activo",
        default=5,
    )
    method_period = fields.Selection(
        selection=lambda self: self._selection_method_period(),
        string="Duración del período",
        required=True,
        default="year",
        help="Duración del período para los asientos de depreciación",
    )
    method_progress_factor = fields.Float(string="Factor decreciente", default=0.3)
    method_time = fields.Selection(
        selection=lambda self: self._selection_method_time(),
        string="Método de tiempo",
        required=True,
        default="year",
        help="Seleccione el método para calcular las fechas y el número de líneas.\n"
             "  * Número de años: Indicar los años.\n"
             "  * Número de depreciaciones: Fija la cantidad de líneas y el tiempo entre ellas.",
    )
    days_calc = fields.Boolean(
        string="Calcular por días",
        default=False,
        help="Usar número de días para calcular la depreciación",
    )
    use_leap_years = fields.Boolean(
        default=False,
        help="Si no se establece, el sistema distribuirá uniformemente el importe para "
        "amortizar a lo largo de los años, en función del número de años. "
        "Por lo tanto, el importe anual será la "
        "base de amortización / número de años.\n "
        "Si se establece, el sistema tendrá en cuenta si el año actual "
        "es bisiesto. El importe a amortizar por año se "
        "calcula como base de amortización / (fecha de finalización de la amortización - "
        "fecha de inicio + 1) * días del año actual.",
    )
    prorata = fields.Boolean(
        string="Prorata Temporis",
        compute="_compute_prorrata",
        readonly=False,
        store=True,
        help="Indica que la primera entrada de amortización para este activo "
        "debe realizarse a partir de la fecha de inicio de la amortización en lugar de "
        "el primer día del año fiscal.",
    )
    open_asset = fields.Boolean(
        string="Saltar estado borrador",
        help="Actívelo para confirmar automáticamente los activos de este perfil "
        "cuando se creen desde facturas.",
    )
    asset_product_item = fields.Boolean(
        string="Crear un activo por unidad de producto",
        help="De forma predeterminada, durante la validación de una factura, se crea un activo "
        "por cada línea de la factura, siempre y cuando se cree un asiento contable "
        "por cada línea de la factura. "
        "Con esta configuración, se creará un asiento contable por cada "
        "artículo del producto. Por lo tanto, habrá un activo por cada artículo del producto.",
    )
    active = fields.Boolean(default=True)
    allow_reversal = fields.Boolean(
        "Permitir reversión de asientos",
        help="Si se activa, al pulsar el botón Eliminar/Anular movimiento en una "
        "línea de amortización contabilizada, se mostrará la opción de anular el "
        "asiento contable, en lugar de eliminarlo.",
    )

    @api.model
    def _default_company_id(self):
        return self.env.company

    @api.model
    def _selection_method(self):
        return [
            ("linear", _("Lineal")),
            ("linear-limit", _("Lineal hasta valor residual")),
            ("degressive", _("Decreciente")),
            ("degr-linear", _("Decreciente-Lineal")),
            ("degr-limit", _("Decreciente hasta valor residual")),
        ]

    @api.model
    def _selection_method_period(self):
        return [("month", _("Mes")), ("quarter", _("Trimestre")), ("year", _("Año"))]

    @api.model
    def _selection_method_time(self):
        return [
            ("year", _("Número de años o fecha final")),
            ("number", _("Número de depreciaciones")),
        ]

    @api.constrains("method", "method_time")
    def _check_method(self):
        if any(a.method == "degr-linear" and a.method_time != "year" for a in self):
            raise UserError(
                _("La opción «Degresivo-Lineal» solo es compatible con el método temporal = Año.")
            )

    @api.depends("method_time")
    def _compute_prorrata(self):
        for profile in self:
            if profile.method_time != "year":
                profile.prorata = True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("method_time") != "year" and not vals.get("prorata"):
                vals["prorata"] = True
        profile_ids = super().create(vals_list)
        account_dict = {}
        for profile_id in profile_ids.filtered(
            lambda x: not x.account_asset_id.asset_profile_id
        ):
            account_dict.setdefault(profile_id.account_asset_id, []).append(
                profile_id.id
            )
        for account, profile_list in account_dict.items():
            account.write({"asset_profile_id": profile_list[-1]})
        return profile_ids

    def write(self, vals):
        if vals.get("method_time"):
            if vals["method_time"] != "year" and not vals.get("prorata"):
                vals["prorata"] = True
        res = super().write(vals)
        # account. must be improved.
        account = self.env["account.account"].browse(vals.get("account_asset_id"))
        if self and account and not account.asset_profile_id:
            account.write({"asset_profile_id": self[-1].id})
        return res
