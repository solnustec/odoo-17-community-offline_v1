from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    payment_partial_amount = fields.Float(string='POS Partial Payment Amount')
    payment_partial_method_id = fields.Many2one(comodel_name='pos.payment.method', ondelete='cascade', string='POS Payment Method')

    @api.model
    def create_from_pos_ui(self, values, auto_confirm, auto_delivery, auto_invoice):
        sale = self.create(values)
        # sale.order_line._compute_tax_id()
        sale._auto_confirm_from_pos_ui(auto_confirm, auto_delivery, auto_invoice)
        return {'name': sale.name, 'id': sale.id}

    def write_from_pos_ui(self, values, auto_confirm, auto_delivery, auto_invoice):
        self.order_line.unlink()
        self.write(values)
        self._auto_confirm_from_pos_ui(auto_confirm, auto_delivery, auto_invoice)
        return {'name': self.name, 'id': self.id}

    def _auto_confirm_from_pos_ui(self, auto_confirm, auto_delivery, auto_invoice):
        if auto_confirm:
            # self.action_confirm()
            if auto_delivery:
                for picking in self.picking_ids:
                    picking.action_assign()
                    picking.button_validate()
                if auto_invoice:
                    so_context = {
                        'active_model': 'sale.order',
                        'active_ids': [self.id],
                        'active_id': self.id,
                    }
                    payment = self.env['sale.advance.payment.inv'].with_context(so_context).create({
                        'advance_payment_method': 'fixed',
                        'fixed_amount': self.payment_partial_amount,
                    })
                    payment.create_invoices()

    @api.model
    def get_pos_by_employee(self, employee_id):
        pos_config = self.env['pos.config'].sudo().search([
            ('basic_employee_ids', 'in', [employee_id])
        ], limit=1)
        if pos_config:
            warehouse = pos_config.picking_type_id.warehouse_id
            if warehouse:
                data = {
                    "id": warehouse.id,
                    "name": warehouse.name,
                    "external_id": warehouse.external_id.lstrip("0"),
                }
                return data
        return None
