# Standard library imports
from datetime import date, timedelta
from typing import Dict, List

# Third-party imports
from odoo import models, fields, api, _
from odoo.exceptions import (
    UserError,
    ValidationError,
)


class SanitaryRegistry(models.Model):
    _name = "sanitary.registry"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Registro Sanitario para productos"
    _rec_name = "sanitary_registry"
    _order = (
        "sequence asc, id asc"  # Order by ascending sequence, then id for stability
    )

    sanitary_registry = fields.Char(string="Registro Sanitario", required=True)
    product_id = fields.Many2one(
        "product.template", string="Product", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(string="Sequence", default=10)
    expiration_date = fields.Date(string="Fecha de Expiración", required=True)
    alert_expiration = fields.Boolean(
        string="Alerta: Próximo a expirar",
        compute="_compute_alert_expiration",
        store=True,
    )
    # Field to attach documents (supporting sanitary registry)
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "sanitary_registry_attachment_rel",
        "sanitary_registry_id",
        "attachment_id",
        string="Adjuntos",
    )
    has_attachments = fields.Boolean(
        compute="_compute_has_attachments", string="Adjuntos"
    )

    # Field to display the alert message
    alert_message = fields.Char(
        string="Mensaje de Alerta", compute="_compute_alert_message", store=True
    )

    def _get_registry_status(self):
        today = fields.Date.today()
        if not self.expiration_date:
            return "sin_registro"
        days_left = (self.expiration_date - today).days
        if days_left < 0:
            return "vencido"
        elif days_left <= 30:
            return "proximo"
        return "vigente"

    @api.depends("expiration_date")
    def _compute_alert_expiration(self):
        threshold_days = 30  # Number of days to alert before expiration
        today = fields.Date.today()
        for rec in self:
            if rec.expiration_date:
                days_left = (rec.expiration_date - today).days
                # Alert if expiration date is within the next 30 days
                rec.alert_expiration = 0 < days_left <= threshold_days
            else:
                rec.alert_expiration = False

    @api.depends("expiration_date")
    def _compute_alert_message(self):
        message_map = {
            "vigente": "Registro Sanitario Vigente",
            "proximo": "Registro Sanitario próximo a expirar",
            "vencido": "Registro Sanitario Expirado",
            "sin_registro": "Sin Registro Sanitario",
        }
        for rec in self:
            estado = rec._get_registry_status()
            rec.alert_message = message_map.get(estado, "Sin Registro Sanitario")

    def create_expiration_alert_activities(self):
        warning_type = self.env.ref("mail.mail_activity_data_warning")
        threshold_days = 30
        today = fields.Date.today()
        threshold_date = fields.Date.today() + timedelta(days=30)
        recs = self.search(
            [
                ("expiration_date", "<=", threshold_date),
                ("expiration_date", ">=", today),
            ]
        )

        # Prefetch all relevant mail.activity records
        activity_domain = [
            ("res_model", "=", self._name),
            ("res_id", "in", recs.ids),
            ("activity_type_id", "=", warning_type.id),
        ]
        existing_activities = self.env["mail.activity"].search(activity_domain)
        activity_map = {activity.res_id: activity for activity in existing_activities}

        for rec in recs:
            if rec.expiration_date:
                days_left = (rec.expiration_date - today).days
                if 0 <= days_left <= threshold_days:
                    if rec.id not in activity_map:
                        self.env["mail.activity"].create(
                            {
                                "res_model_id": self.env["ir.model"]._get(rec._name).id,
                                "res_id": rec.id,
                                "activity_type_id": warning_type.id,
                                "summary": f"Registro Sanitario {rec.sanitary_registry} esta próximo a expirar",
                                "note": "Por Favor validar la fecha de expiración del Registro Sanitario.",
                                "user_id": self.env.user.id,
                                "date_deadline": rec.expiration_date,
                            }
                        )

    @api.depends("attachment_ids")
    def _compute_has_attachments(self):
        for rec in self:
            rec.has_attachments = bool(rec.attachment_ids)

    @api.constrains("product_id", "sanitary_registry")
    def _check_unique_registry_per_product(self):
        for rec in self:
            if not rec.product_id or not rec.sanitary_registry:
                continue

            # Comparar sin distinguir mayúsculas/minúsculas
            duplicates = self.search(
                [
                    ("product_id", "=", rec.product_id.id),
                    ("sanitary_registry", "=ilike", rec.sanitary_registry.strip()),
                    ("id", "!=", rec.id),
                ]
            )
            if duplicates:
                raise ValidationError(
                    _("El registro sanitario '%s' ya está asignado a este producto.")
                    % rec.sanitary_registry
                )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    EXPIRED_REGISTRY_ERROR = _(
        "El(los) producto(s) siguiente(s) fue(ron) reactivado(s) pero su registro "
        "sanitario está vencido y fue eliminado:\n\n%s\n\n"
        "Por favor, actualice el registro sanitario si corresponde."
    )

    sanitary_registry_ids = fields.One2many(
        "sanitary.registry",
        "product_id",
        string="Registro Sanitario",
        order="sequence asc, id asc",
    )

    alert_message = fields.Char(
        string="Alert Message", compute="_compute_alert_message", store=True
    )
    alert_message_html = fields.Html(
        string="Alert Message HTML",
        compute="_compute_alert_message_html",
        sanitize=True,
    )
    # Fields for  kanban and list views
    sanitary_registry_status = fields.Selection(
        selection=[
            ("vigente", "Registro Sanitario vigente"),
            ("proximo", "Registro Sanitario próximo a expirar"),
            ("vencido", "Registro Sanitario expirado"),
            ("sin_registro", "Sin Registro Sanitario"),
        ],
        string="Estado del Registro Sanitario",
        compute="_compute_sanitary_registry_status",
        store=True,
    )

    sanitary_registry_expiration_date = fields.Date(
        string="Fecha de Expiración del Registro",
        compute="_compute_sanitary_registry_expiration_date",
        store=True,
    )

    sanitary_registry_alert_expiration = fields.Boolean(
        string="Alerta: Próximo a Expirar",
        compute="_compute_sanitary_registry_alert_expiration",
        store=True,
    )

    sanitary_registry_status_icon = fields.Char(
        string="Estado del Registro (Ícono)",
        compute="_compute_sanitary_registry_status_icon",
        store=False,
    )

    sanitary_registry_expired = fields.Boolean(compute="_compute_registry_expired")

    @api.depends("sanitary_registry_expiration_date")
    def _compute_registry_expired(self):
        today = fields.Date.today()
        for rec in self:
            rec.sanitary_registry_expired = bool(
                rec.sanitary_registry_expiration_date
                and rec.sanitary_registry_expiration_date < today
            )

    @api.depends(
        "sanitary_registry_ids",
        "sanitary_registry_ids.expiration_date",
        "sanitary_registry_ids.sequence",
    )
    def _compute_sanitary_registry_expiration_date(self):
        for rec in self:
            if rec.sanitary_registry_ids:
                ordered_regs = rec.sanitary_registry_ids.sorted(
                    key=lambda r: (r.sequence, r.id)
                )
                rec.sanitary_registry_expiration_date = ordered_regs[0].expiration_date
            else:
                rec.sanitary_registry_expiration_date = False

    @api.depends(
        "sanitary_registry_ids",
        "sanitary_registry_ids.expiration_date",
        "sanitary_registry_ids.sequence",
    )
    def _compute_sanitary_registry_alert_expiration(self):
        for rec in self:
            if rec.sanitary_registry_ids:
                ordered_regs = rec.sanitary_registry_ids.sorted(
                    key=lambda r: (r.sequence, r.id)
                )
                rec.sanitary_registry_alert_expiration = ordered_regs[
                    0
                ].alert_expiration
            else:
                rec.sanitary_registry_alert_expiration = False

    @api.depends("sanitary_registry_status")
    def _compute_sanitary_registry_status_icon(self):
        icon_map = {
            "vigente": "fa fa-check-circle",
            "proximo": "fa fa-clock",
            "vencido": "fa fa-times-circle",
            "sin_registro": "fa fa-ban",
        }
        for rec in self:
            rec.sanitary_registry_status_icon = icon_map.get(
                rec.sanitary_registry_status, ""
            )

    def _get_sanitary_registry_status(self):
        today = fields.Date.today()
        if not self.sanitary_registry_ids:
            return "sin_registro"
        ordered_regs = self.sanitary_registry_ids.sorted(
            key=lambda r: (r.sequence, r.id)
        )
        first = ordered_regs[0]
        expiration = fields.Date.to_date(first.expiration_date)
        if not expiration:
            return "sin_registro"
        days_left = (expiration - today).days
        if days_left < 0:
            return "vencido"
        elif 0 <= days_left <= 30:
            return "proximo"
        else:
            return "vigente"

    def _remove_expired_registries(self):
        """Remove expired sanitary registries and return affected product names."""
        products_with_removed_registries = []
        today = fields.Date.today()

        for product in self:
            had_registries = bool(product.sanitary_registry_ids)
            expired_registries = product.sanitary_registry_ids.filtered(
                lambda r: r.expiration_date and r.expiration_date < today
            )
            expired_registries.unlink()

            if had_registries and not product.sanitary_registry_ids:
                products_with_removed_registries.append(product.name)

        return products_with_removed_registries

    @api.model
    def write(self, vals):
        affected_products = []
        for p in self:
            if "active" in vals and not p.active and vals["active"]:
                affected_products = self._remove_expired_registries()

        result = super().write(vals)

        if affected_products:
            raise UserError(self.EXPIRED_REGISTRY_ERROR % "\n".join(affected_products))

        return result

    @api.depends("alert_message")
    def _compute_alert_message_html(self):
        for rec in self:

            class_map = {
                "Registro Sanitario Vigente": "alert-success",
                "Registro Sanitario próximo a expirar": "alert-warning",
                "Registro Sanitario Expirado": "alert-danger",
                "Sin Registro Sanitario": "alert-info",
            }
            css_class = class_map.get(rec.alert_message.strip(), "alert-info")

            # Composición del HTML final
            if rec.alert_message:
                generated_html = (
                    f'<div class="alert {css_class}">{rec.alert_message}</div>'
                )
                rec.alert_message_html = generated_html
            else:
                rec.alert_message_html = ""

    @api.depends(
        "sanitary_registry_ids",
        "sanitary_registry_ids.expiration_date",
        "sanitary_registry_ids.sequence",
    )
    def _compute_alert_message(self):
        status_to_message = {
            "vigente": "Registro Sanitario Vigente",
            "proximo": "Registro Sanitario proximo a expirar",
            "vencido": "Registro Sanitario Expirado",
            "sin_registro": "Sin Registro Sanitario",
        }

        for rec in self:
            status = rec._get_sanitary_registry_status()
            rec.alert_message = status_to_message.get(
                status, "Sin información del registro sanitario"
            )

    @api.depends(
        "sanitary_registry_ids",
        "sanitary_registry_ids.expiration_date",
        "sanitary_registry_ids.sequence",
    )
    def _compute_sanitary_registry_status(self):
        for rec in self:
            rec.sanitary_registry_status = rec._get_sanitary_registry_status()
