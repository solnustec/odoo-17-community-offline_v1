from odoo import models, fields

class PosOrder(models.Model):
    _inherit = 'pos.order'

    invoice_note = fields.Text(string='Nota de Factura')

    def _order_fields(self, ui_order):
        res = super()._order_fields(ui_order)
        res['invoice_note'] = ui_order.get('invoice_note', '')
        return res
