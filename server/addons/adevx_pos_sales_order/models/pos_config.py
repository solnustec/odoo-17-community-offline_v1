from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    create_sale_order = fields.Boolean("Crear orden de venta", default=False)
    sale_order_auto_confirm = fields.Boolean("Confirmación automática", default=False)
    sale_order_auto_invoice = fields.Boolean("Auto Paid", default=False)
    sale_order_auto_delivery = fields.Boolean("Auto Delivery", default=False)
    sale_order_required_signature = fields.Boolean(
        string="SO Required Signature", help="Allow print receipt when create quotation/order")
    update_sale_order = fields.Boolean(
        string="Actualizar orden de venta",
        help="Allow you settle sale order ,\n update quantity of line \n or add new line to sale order in POS Screen")

    @api.onchange('create_sale_order', 'update_sale_order')
    def _onchange_create_update_sale_order(self):
        if not self.create_sale_order and not self.update_sale_order:
            self.sale_order_auto_confirm = False
            self.sale_order_auto_delivery = False
            self.sale_order_auto_invoice = False
            self.sale_order_required_signature = False

    @api.onchange('sale_order_auto_confirm')
    def _onchange_sale_order_auto_confirm(self):
        if not self.sale_order_auto_confirm:
            self.sale_order_auto_delivery = False
            self.sale_order_auto_invoice = False

    @api.onchange('sale_order_auto_delivery')
    def _onchange_sale_order_auto_delivery(self):
        if not self.sale_order_auto_delivery:
            self.sale_order_auto_invoice = False
        else:
            self.sale_order_auto_confirm = True

    @api.onchange('sale_order_auto_invoice')
    def _onchange_sale_order_auto_invoice(self):
        if self.sale_order_auto_invoice:
            self.sale_order_auto_confirm = True
            self.sale_order_auto_delivery = True