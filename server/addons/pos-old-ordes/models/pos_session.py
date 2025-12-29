from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta,time
import logging

_logger = logging.getLogger(__name__)


class PosSessionChecker(models.Model):
    _inherit = 'pos.session'

    @api.model
    def get_payment_methods_by_user_pos(self, user_id):
        """Retorna los métodos de pago asociados al POS del usuario dado."""
        user = self.env['res.users'].browse(user_id).exists()
        if not user:
            raise UserError(_("Usuario no encontrado."))

        # Buscar configuración POS del usuario
        pos_config = self.env['pos.config'].search([
            ('session_ids.user_id', '=', user.id)
        ], limit=1)

        if not pos_config:
            raise UserError(_("No se encontró una configuración POS asociada al usuario."))

        payment_methods = pos_config.payment_method_ids

        return [
            {
                'id': method.id,
                'name': method.name,
                'type': method.type,
                'journal_id': method.journal_id.id,
            }
            for method in payment_methods
        ]

    @api.model
    def search_cliente_id_old(self, identification):
        _logger.info('searchClienteIdOld %s', identification)
        partner = self.env['res.partner'].search([('vat', '=', identification)], limit=1)
        if partner:
            return {
                'id': partner.id,
                'name': partner.name,
                'email': partner.email,
                'id_database_old': partner.id_database_old,
            }
        else:
            return False

    @api.model
    def check_session_by_user_and_date_and_create_order(self, data):
        user_id = data.get("user_id")
        selected_date_str = data.get("selected_date")
        partner_id = data.get("partner_id")
        order_lines = data.get("lines", [])
        amount_total = data.get("amount_total", 0.0)
        amount_paid = data.get("amount_paid", 0.0)
        amount_tax = data.get("amount_tax", 0.0)
        payment_method_id = data.get("payment_method_id")
        payment_method_api = data.get("payment_method")
        key_order = data.get("key_order")
        date_invoices = data.get("date")


        if not (user_id and selected_date_str and partner_id
                and order_lines and payment_method_id and key_order):
            raise UserError(_("Faltan datos requeridos para crear la orden."))

        try:
            base_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
            selected_date = datetime.combine(base_date, datetime.min.time()) + timedelta(hours=12)
        except ValueError:
            raise UserError(_("El formato de la fecha debe ser YYYY-MM-DD"))

        start = datetime.combine(base_date, time.min)  # 00:00:00
        end = datetime.combine(base_date, time.max)  # 23:59:59.999999
        session = self.env['pos.session'].search([
            ('user_id', '=', user_id),
            ('start_at', '>=', start),
            ('start_at', '<=', end),
        ], limit=1)

        user = self.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            raise UserError(_('Usuario con ID %s no encontrado') % user_id)


        if not session:
            pos_config = (self.env['pos.config']
                          .search([('session_ids.user_id', '=', user_id)], limit=1)
                          or self.env['pos.config'].search([], limit=1))
            if not pos_config:
                raise UserError(_('No se encontró una configuración de POS.'))
            if not pos_config.sequence_id:
                seq = self.env['ir.sequence'].create({
                    'name': f'POS Order {pos_config.name}',
                    'padding': 4,
                    'prefix': f'{pos_config.name}/',
                    'code': 'pos.order',
                    'company_id': pos_config.company_id.id,
                })
                pos_config.sequence_id = seq
            session = self.env['pos.session'].sudo().create({
                'user_id': user_id,
                'config_id': pos_config.id,
                'start_at': selected_date,
                'stop_at': selected_date,
                'state': 'closed',
            })

        pm = self.env['pos.payment.method'].browse(payment_method_id)
        if not pm.exists() or pm not in session.config_id.payment_method_ids:
            raise UserError(_('El método de pago seleccionado no es válido para este POS.'))

        line_items = []
        for line in order_lines:
            if not all(k in line for k in ('product_id', 'qty', 'price_unit')):
                continue
            prod = self.env['product.product'].sudo().browse(line['product_id'])
            if not prod.exists():
                raise UserError(_('Producto con ID %s no existe.') % line['product_id'])

            qty = float(line['qty'])
            price = float(line['price_unit'])
            discount = float(line.get('discount', 0.0))
            subtotal = qty * price * (1 - discount / 100.0)

            tax_cmds = line.get('tax_ids', [])

            line_items.append((0, 0, {
                'product_id': prod.id,
                'qty': qty,
                'price_unit': price,
                'discount': discount,
                'price_subtotal': subtotal,
                'price_subtotal_incl': subtotal,
                'full_product_name': prod.get_product_multiline_description_sale() or prod.name,
                'tax_ids': tax_cmds,
                'tax_ids_after_fiscal_position': tax_cmds,
            }))
        last_seq = (self.env['pos.order']
                    .sudo().search([('session_id', '=', session.id)],
                                   order='sequence_number desc', limit=1)
                    .sequence_number) or 0
        next_seq = last_seq + 1
        comp_seq = str(session.id).zfill(5)
        conf_seq = str(session.config_id.id).zfill(3)
        ord_seq = str(next_seq).zfill(4)
        pos_reference = f"Orden {comp_seq}-{conf_seq}-{ord_seq}"
        name = f"{session.config_id.name}/{ord_seq}"

        order = self.env['pos.order'].sudo().create({
            'session_id': session.id,
            'partner_id': partner_id,
            'amount_total': amount_total,
            'amount_paid': amount_paid,
            'amount_tax': amount_tax,
            'amount_return': 0.0,
            'to_invoice': True,
            'date_order': selected_date,
            'create_date': selected_date,
            'state': 'paid',
            'user_id': user_id,
            'pricelist_id': session.config_id.pricelist_id.id,
            'fiscal_position_id': session.config_id.default_fiscal_position_id.id or False,
            'company_id': session.config_id.company_id.id,
            'currency_id': session.config_id.currency_id.id,
            'name': name,
            'pos_reference': pos_reference,
            'sequence_number': next_seq,
            'lines': line_items,
            'key_order': key_order,
            'date_invoices': date_invoices,
        })

        self.env.cr.flush()
        self.env.cr.execute(
            "UPDATE pos_order SET create_date = %s WHERE id = %s",
            (selected_date, order.id)
        )
        order.invalidate_recordset()

        available_pm = session.config_id.payment_method_ids
        if payment_method_api == 11:
            # Crédito
            credit_methods = available_pm.filtered(
                lambda p: 'CREDITO' in (p.name or '').upper()
            )
            if not credit_methods:
                raise UserError(_('No hay ningún método cuyo nombre contenga "Crédito".'))
            chosen_pm = credit_methods[0]
        else:
            # Anticipo, filtrando por el campo code_payment_method

            anticipo_methods = available_pm.filtered(
                lambda p: (p.code_payment_method or '').upper() == 'CTACLIENTE'
            )
            if not anticipo_methods:
                raise UserError(_('No hay ningún método cuyo código sea "CTACLIENTE".'))
            chosen_pm = anticipo_methods[0]


        self.env['pos.payment'].create({
            'pos_order_id': order.id,
            'amount': amount_paid,
            'payment_method_id': chosen_pm.id,
            'payment_date': selected_date,
        })

        try:
            order.action_pos_order_invoice()
            invoice = order.invoice_id
        except Exception as e:
            _logger.error("No se pudo facturar la order %s: %s", order.id, e)
            raise UserError(_("Ocurrió un error al generar la factura: %s") % e)

        return {
            'order_id': order.id,
            'order_name': order.name,
            'pos_reference': order.pos_reference,
            'invoice_id': invoice and invoice.id,
            'session_id': session.id,
            'session_state': session.state,
        }
