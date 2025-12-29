from odoo import models, fields, api
from odoo.exceptions import UserError


class TransferVerifier(models.Model):
    _name = "stock.transfer.verifier"
    _description = "Verificador de Transferencias"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    picking_id = fields.Many2one("stock.picking", string="Transferencia", required=True)
    line_ids = fields.One2many("stock.transfer.verifier.line", "verifier_id", string="Verificaciones")
    barcode_input = fields.Char(string="Escanear código de barras")
    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        default=lambda self: self.env.user,
        readonly=True
    )
    log_ids = fields.One2many("stock.transfer.verifier.log", "verifier_id", string="Historial", readonly=True)

    # ---------- HELPERS ----------
    def _log_action(self, tipo_accion, action, product=False, qty=0.0):
        """ Helper para registrar logs de acciones """
        if self.id and not isinstance(self.id, models.NewId):
            self.env["stock.transfer.verifier.log"].create({
                "verifier_id": self.id,
                "user_id": self.env.user.id,
                "tipo_accion": tipo_accion,
                "action": action,
                "product_id": product.id if product else False,
                "qty": qty,
            })

    # ---------- MÉTODOS PRINCIPALES ----------
    def action_scan_barcode(self):
        self.ensure_one()
        code = (self.barcode_input or "").strip()
        if not code:
            return

        product = self.env['product.product'].search([('default_code', '=', code)], limit=1)
        if not product:
            raise UserError(f"El código {code} no corresponde a ningún producto.")

        allowed_products = self.picking_id.move_ids_without_package.mapped("product_id")
        if product not in allowed_products:
            raise UserError(f"El producto {product.display_name} no pertenece a la transferencia.")

        line = self.line_ids.filtered(lambda l: l.product_id == product)
        if line:
            line.qty_entered += 1
        else:
            vals = {"product_id": product.id, "qty_entered": 1}
            if not self.id or isinstance(self.id, models.NewId):
                self.line_ids = [(0, 0, vals)]
            else:
                vals["verifier_id"] = self.id
                self.env['stock.transfer.verifier.line'].create(vals)

        # Log del escaneo
        self._log_action("scan", f"📦 Escaneo de {product.display_name}", product, 1)
        self.barcode_input = False

    def action_validate_transfer(self):
        """Valida que lo ingresado coincida con la transferencia"""
        self.ensure_one()

        picking_products = {
            move.product_id.id: move.quantity
            for move in self.picking_id.move_ids_without_package
        }

        for product_id, qty_expected in picking_products.items():
            line = self.line_ids.filtered(lambda l: l.product_id.id == product_id)
            if not line:
                prod_name = self.env['product.product'].browse(product_id).display_name
                raise UserError(f"Falta el producto {prod_name}")
            if line.qty_entered != qty_expected:
                raise UserError(
                    f"Cantidad incorrecta para {line.product_id.display_name}. "
                    f"Esperado: {qty_expected}, Ingresado: {line.qty_entered}"
                )

        extra_lines = self.line_ids.filtered(lambda l: l.product_id.id not in picking_products)
        if extra_lines:
            raise UserError(
                f"El producto {extra_lines[0].product_id.display_name} no está en la transferencia."
            )

        # Log de validación
        self._log_action("validate", "✅ Se validó la transferencia")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Éxito',
                'message': '✅ Transferencia verificada correctamente',
                'type': 'success',
                'sticky': False,
            }
        }

    @api.onchange("barcode_input")
    def _onchange_barcode_input(self):
        if self.barcode_input:
            self.action_scan_barcode()


class TransferVerifierLine(models.Model):
    _name = "stock.transfer.verifier.line"
    _description = "Línea de verificación de Transferencia"

    verifier_id = fields.Many2one("stock.transfer.verifier", required=True)
    product_id = fields.Many2one(
        "product.product", string="Producto",
        domain="[('id', 'in', allowed_product_ids)]"
    )
    qty_entered = fields.Float(string="Cantidad ingresada", default=0)
    qty_expected = fields.Float(string="Cantidad esperada", compute="_compute_expected_qty", store=False)
    result = fields.Selection(
        [('ok', '✅ Correcto'), ('fail', '❌ Incorrecto')],
        string="Resultado", compute="_compute_result", store=False
    )
    allowed_product_ids = fields.Many2many("product.product", compute="_compute_allowed_products")

    # ---------- COMPUTES ----------
    @api.depends("verifier_id.picking_id")
    def _compute_allowed_products(self):
        for line in self:
            line.allowed_product_ids = line.verifier_id.picking_id.move_ids_without_package.mapped("product_id")

    @api.depends("product_id", "verifier_id.picking_id.move_ids_without_package.quantity")
    def _compute_expected_qty(self):
        for line in self:
            moves = line.verifier_id.picking_id.move_ids_without_package.filtered(
                lambda m: m.product_id == line.product_id
            )
            line.qty_expected = sum(moves.mapped("quantity")) if moves else 0.0

    @api.depends("qty_entered", "qty_expected")
    def _compute_result(self):
        for line in self:
            line.result = (
                'ok' if line.qty_expected and line.qty_entered == line.qty_expected else 'fail'
            ) if line.qty_entered is not None else False

    # ---------- OVERRIDES ----------
    def _log_line_action(self, tipo_accion, action):
        self.env["stock.transfer.verifier.log"].create({
            "verifier_id": self.verifier_id.id,
            "user_id": self.env.user.id,
            "tipo_accion": tipo_accion,
            "action": action,
            "product_id": self.product_id.id,
            "qty": self.qty_entered,
        })

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._log_line_action("create_line", f"➕ Se creó la línea para {record.product_id.display_name}")
        return record

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            rec._log_line_action("update_line", f"✏️ Se modificó la línea de {rec.product_id.display_name}")
        return res

    def unlink(self):
        for rec in self:
            rec._log_line_action("delete_line", f"❌ Se eliminó la línea de {rec.product_id.display_name}")
        return super().unlink()


class TransferVerifierLog(models.Model):
    _name = "stock.transfer.verifier.log"
    _description = "Historial de Verificación de Transferencias"
    _order = "create_date desc"

    verifier_id = fields.Many2one("stock.transfer.verifier", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", string="Usuario", default=lambda self: self.env.user)

    tipo_accion = fields.Selection([
        ("scan", "Escaneo"),
        ("create_line", "Creación"),
        ("update_line", "Modificación"),
        ("delete_line", "Eliminación"),
        ("validate", "Validación de transferencia"),
    ], string="Tipo de Acción", required=True)

    action = fields.Char(string="Descripción")
    product_id = fields.Many2one("product.product", string="Producto")
    qty = fields.Float(string="Cantidad")
    create_date = fields.Datetime(string="Fecha", readonly=True)
