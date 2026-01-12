# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import ValidationError


class BarcodeAssignWizard(models.TransientModel):
    """Wizard para confirmar la asignación de un código de barras a un producto"""

    _name = "barcode.assign.wizard"
    _description = "Barcode Assignment Confirmation Wizard"

    barcode = fields.Char(
        string="Código de Barras",
        required=True,
        readonly=True,
        help="El código de barras que se va a registrar"
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        readonly=True,
        help="El producto al que se asignará el código de barras"
    )
    purchase_order_id = fields.Many2one(
        "purchase.order",
        string="Orden de Compra",
        readonly=True,
        help="Documento de compra origen para trazabilidad"
    )
    purchase_line_id = fields.Many2one(
        "purchase.order.line",
        string="Línea de Compra",
        readonly=True,
        help="Línea de compra origen"
    )

    def _check_barcode_exists(self, barcode):
        """Verifica si el barcode ya existe en el sistema"""
        # Verificar en barcode estándar de product.product
        product_standard = self.env["product.product"].search([
            ("barcode", "=", barcode)
        ], limit=1)
        if product_standard:
            return True, product_standard

        # Verificar en códigos múltiples
        multi_barcode = self.env["product.multiple.barcodes"].search([
            ("product_multi_barcode", "=", barcode)
        ], limit=1)
        if multi_barcode:
            return True, multi_barcode.product_id

        return False, None

    def action_confirm(self):
        """Confirma y registra el código de barras"""
        self.ensure_one()

        # Validar que el barcode no exista
        exists, existing_product = self._check_barcode_exists(self.barcode)
        if exists:
            raise ValidationError(_(
                "El código de barras '%s' ya está registrado para el producto '%s'.\n"
                "No se puede duplicar un código de barras."
            ) % (self.barcode, existing_product.display_name if existing_product else ""))

        # Validar que el producto existe
        if not self.product_id:
            raise ValidationError(_("Debe seleccionar un producto válido."))

        # Crear el registro del código de barras con trazabilidad
        vals = {
            "product_multi_barcode": self.barcode,
            "product_id": self.product_id.id,
            "product_template_id": self.product_id.product_tmpl_id.id,
        }

        new_barcode = self.env["product.multiple.barcodes"].create(vals)

        # Log de trazabilidad en el chatter del producto
        self._log_barcode_creation(new_barcode)

        # Notificación de éxito
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Código de Barras Registrado"),
                "message": _(
                    "El código '%s' ha sido asignado exitosamente al producto '%s'."
                ) % (self.barcode, self.product_id.display_name),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            }
        }

    def _log_barcode_creation(self, barcode_record):
        """Registra la creación del barcode en el chatter del producto"""
        self.ensure_one()

        # Mensaje para el producto
        purchase_info = ""
        if self.purchase_order_id:
            purchase_info = _("<br/>Documento origen: %s") % self.purchase_order_id.name

        message = _(
            "<strong>Nuevo código de barras registrado</strong><br/>"
            "Código: <code>%s</code><br/>"
            "Registrado por: %s<br/>"
            "Fecha: %s%s"
        ) % (
            self.barcode,
            self.env.user.name,
            fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            purchase_info
        )

        self.product_id.message_post(
            body=message,
            message_type="notification",
            subtype_xmlid="mail.mt_note"
        )

    def action_cancel(self):
        """Cancela la operación y cierra el wizard"""
        return {"type": "ir.actions.act_window_close"}
