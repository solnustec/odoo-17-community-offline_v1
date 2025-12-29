from odoo import models, api, fields
import logging
import pprint


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_subtotal_mail = fields.Float(compute='_compute_email_values', store=False)
    discount_promotions_mail = fields.Float(compute='_compute_email_values', store=False)
    amount_delivery = fields.Float(string='Delivery Amount', compute='_compute_email_values', store=False)

    def action_despacho_send(self):
        """ Open a window to compose an email, with the despacho email template
            message loaded by default
        """
        self.ensure_one()
        template_id = self.env.ref('email_format.email_template_despacho').id

        # Calcular valores antes de enviar
        self._compute_email_values()

        ctx = {
            'default_model': 'sale.order',
            'default_res_ids': self.ids,
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'custom_layout': "mail.mail_notification_paynow",
            'force_email': True,
            'amount_delivery': self.amount_delivery,
        }

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    def action_quotation_send(self):
        """ Opens a wizard to compose an email, with relevant mail template loaded by default """
        self.ensure_one()
        self.order_line._validate_analytic_distribution()
        lang = self.env.context.get('lang')
        mail_template = self._find_mail_template()
        if mail_template and mail_template.lang:
            lang = mail_template._render_lang(self.ids)[self.id]

        discount_promotions = 0.0
        delivery_subtotal = 0.0

        for discount_product in self.order_line:
            if 'Envío' in discount_product.name:
                delivery_subtotal = discount_product.price_subtotal

            if discount_product.price_reduce_taxinc < 0:
                discount_promotions += discount_product.price_reduce_taxinc

        ctx = {
            'default_model': 'sale.order',
            'default_res_ids': self.ids,
            'default_template_id': mail_template.id if mail_template else None,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'default_email_layout_xmlid': 'mail.mail_notification_layout_with_responsible_signature',
            'proforma': self.env.context.get('proforma', False),
            'force_email': True,
            'model_description': self.with_context(lang=lang).type_name,
            'discount_promotions': discount_promotions,
            'delivery_subtotal': delivery_subtotal
        }

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    @api.depends('order_line.price_subtotal', 'order_line.is_delivery', 'order_line.price_total')
    def _compute_email_values(self):
        for order in self:
            # Calcular amount_delivery basado en líneas con is_delivery=True
            delivery_lines = order.order_line.filtered(lambda l: l.is_delivery)
            order.amount_delivery = sum(delivery_lines.mapped('price_total'))

            # Calcular delivery_subtotal_mail basado en líneas con 'Envío' en el nombre
            delivery_total = sum(
                line.price_subtotal
                for line in order.order_line
                if 'Envío' in (line.name or '')
            )

            # Calcular descuentos
            discount_total = sum(
                line.price_reduce_taxinc
                for line in order.order_line
                if line.price_reduce_taxinc < 0
            )

            order.delivery_subtotal_mail = delivery_total
            order.discount_promotions_mail = discount_total
