# -*- coding: utf-8 -*-
import logging
import requests

_logger = logging.getLogger(__name__)
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PosInvoiceWizard(models.TransientModel):
    _name = 'pos.invoice.wizard'
    _description = 'Wizard para crear facturas'

    order_ids = fields.Many2many('pos.order', string="Ordenes")
    order_count = fields.Integer(string="Número de Ordenes",
                                 compute='_compute_order_count')
    consolidated = fields.Boolean(string="Factura Consolidada?", default=True,
                                  help="Marque esta casilla si desea crear una factura consolidada. Desmarque esta casilla para crear facturas individuales.")

    @api.depends('order_ids')
    def _compute_order_count(self):
        for wizard in self:
            wizard.order_count = len(wizard.order_ids)

    @api.model
    def default_get(self, fields_list):
        res = super(PosInvoiceWizard, self).default_get(fields_list)
        active_ids = self.env.context.get('active_ids')
        if active_ids:
            res.update({'order_ids': [(6, 0, active_ids)]})
        return res

    def action_confirm(self):
        if self.consolidated:
            action = self.order_ids.action_create_single_invoice()
        else:
            for order in self.order_ids:
                order.action_create_invoice()
            action = {'type': 'ir.actions.client', 'tag': 'reload'}
        return action


class PosOrderServerAction(models.Model):
    _inherit = 'ir.actions.server'

    def _register_hook(self):
        action = self.env.ref('seu_modulo.action_create_single_invoice',
                              raise_if_not_found=False)
        if not action:
            self.env['ir.actions.server'].create({
                'name': "Crear Factura Consolidada",
                'state': "code",
                'model_id': self.env.ref('point_of_sale.model_pos_order').id,
                'code': "action = records.action_create_single_invoice(); action and action or None",
            })


class PosOrder(models.Model):
    _inherit = 'pos.order'

    is_delivery_order = fields.Boolean(string="Es una orden de entrega?",
                                       readonly=True)
    invoice_id = fields.Many2one('account.move', string="Fatura")

    @api.model
    def create(self, vals):
        if 'to_invoice' in vals:
            vals['is_delivery_order'] = not vals['to_invoice']
        else:
            to_invoice_default = False
            if callable(self._fields['to_invoice'].default):
                to_invoice_default = self._fields['to_invoice'].default(self)
            vals['is_delivery_order'] = not to_invoice_default
        return super(PosOrder, self).create(vals)

    def action_pos_order_invoice(self):
        if self.to_invoice:
            if len(self.company_id) > 1:
                raise UserError(_("You cannot invoice orders belonging to different companies."))
            self.write({'to_invoice': True})
            if self.company_id.anglo_saxon_accounting and self.session_id.update_stock_at_closing and self.session_id.state != 'closed':
                self._create_order_picking()
            return self._generate_pos_order_invoice()
        raise UserError(_("Es una orden de Entrega, no se puede facturar."))

    def action_create_single_invoice(self):

        orders = self.filtered(
            lambda o: not o.invoice_id and o.state in ['paid', 'done'])

        ineligible_orders = self.filtered(
            lambda o: o.invoice_id or o.state not in ['paid', 'done'])

        if len(ineligible_orders) == len(self):
            raise UserError(
                "Todos los pedidos seleccionados ya han sido facturados o tienen un estado no válido.")

        if not orders:
            raise UserError("No hay ningún pedido válido para facturación.")

        partner = orders.mapped('partner_id')
        if len(partner) > 1:
            raise UserError(
                "Todos los pedidos deben pertenecer al mismo cliente.")
        invoice_vals = {
            'partner_id': partner.id,
            'invoice_origin': ', '.join(orders.mapped('name')),
            'move_type': 'out_invoice',
            'invoice_line_ids': [],
        }
        invoice = self.env['account.move'].create(invoice_vals)

        for order in orders:
            for line in order.lines:
                self.env['account.move.line'].create({
                    'move_id': invoice.id,
                    'name': line.product_id.name,
                    'quantity': line.qty,
                    'price_unit': line.price_unit,
                    'tax_ids': [(6, 0, line.tax_ids.ids)],
                    'product_id': line.product_id.id,
                })

            order.invoice_id = invoice.id
            order.state = 'draft'
            order.to_invoice = True
            order.account_move = invoice.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
            'target': 'current',
        }

    def action_create_invoice(self):
        self.ensure_one()

        if self.invoice_id:
            raise UserError(_("Este pedido ya tiene factura."))

        if self.state not in ['paid', 'done']:
            raise UserError(
                _("El pedido debe estar en estado “pagado” o “completado” para ser facturado."))

        invoice_vals = {
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,
            'move_type': 'out_invoice',
            'invoice_line_ids': [],
        }

        invoice = self.env['account.move'].create(invoice_vals)

        for line in self.lines:
            self.env['account.move.line'].create({
                'move_id': invoice.id,
                'name': line.product_id.name,
                'quantity': line.qty,
                'price_unit': line.price_unit,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
                'product_id': line.product_id.id,
            })

        self.invoice_id = invoice.id
        self.state = 'draft'
        self.to_invoice = True
        self.account_move = invoice.id

        return invoice
