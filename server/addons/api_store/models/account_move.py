import json
from datetime import datetime, timedelta

import pytz

from odoo import models, api
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        #
        res = super().action_post()
        self.generate_json_visual_fact()
        return res

    @api.model
    def get_total_discount(self):
        """Devuelve el total del descuento (monetario) de esta factura."""
        self.ensure_one()
        total = 0.0
        for line in self.invoice_line_ids:
            if line.discount > 0:
                qty = float(getattr(line, 'quantity', getattr(line, 'product_uom_qty', 0.0)) or 0.0)
                price = float(getattr(line, 'price_unit', 0.0) or 0.0)
                disc_pct = float(getattr(line, 'discount', 0.0) or 0.0) / 100.0
                total += price * qty * disc_pct
        return self.currency_id.round(total) if self.currency_id else total

    def get_total_products_with_vat(self):
        """Retorna el total (monetario) de líneas que tienen IVA (cualquier tax.amount != 0)."""
        self.ensure_one()
        total = 0.0
        for line in self.invoice_line_ids:
            qty = float(getattr(line, 'quantity', getattr(line, 'product_uom_qty', 0.0)) or 0.0)
            price = float(getattr(line, 'price_unit', 0.0) or 0.0)
            disc_pct = float(getattr(line, 'discount', 0.0) or 0.0) / 100.0
            subtotal = price * qty * (1 - disc_pct)
            taxes = line.tax_ids or self.env['account.tax']
            has_vat = any((float(t.amount or 0.0) != 0.0) for t in taxes) if taxes else False
            if has_vat:
                total += subtotal
        return self.currency_id.round(total) if self.currency_id else total

    def get_total_products_without_vat(self):
        """Retorna el total (monetario) de líneas sin IVA (sin taxes o todos con amount == 0)."""
        self.ensure_one()
        total = 0.0
        for line in self.invoice_line_ids:
            qty = float(getattr(line, 'quantity', getattr(line, 'product_uom_qty', 0.0)) or 0.0)
            price = float(getattr(line, 'price_unit', 0.0) or 0.0)
            disc_pct = float(getattr(line, 'discount', 0.0) or 0.0) / 100.0
            subtotal = price * qty * (1 - disc_pct)
            taxes = line.tax_ids or self.env['account.tax']
            has_vat = any((float(t.amount or 0.0) != 0.0) for t in taxes) if taxes else False
            if not has_vat:
                total += subtotal
        return self.currency_id.round(total) if self.currency_id else total

    @api.model
    def generate_json_visual_fact(self):
        order_id = self.env['sale.order'].search([('invoice_ids', 'in', self.ids)], limit=1)
        if not order_id.is_order_app:
            return None
        payment_transaction = self.env['payment.transaction'].sudo().search(
            [('sale_order_ids', 'in', order_id.id), ('state', '=', 'done')], limit=1,
            order='id desc')
        if not payment_transaction:
            return UserError("No se encontró ningun pago aprobado para la orden.")
        self.sudo().write({'invoice_user_id': self.env.user.id})
        cfp ={}
        cliente_info = {
            "id": int(order_id.partner_id.id_database_old),
            "ruc": order_id.partner_id.vat,
            "name": order_id.partner_id.name.upper(),
            "comercio": order_id.partner_id.name.upper(),
            "address": order_id.partner_id.street if order_id.partner_id.street else "",
            "phone": order_id.partner_id.phone if order_id.partner_id.phone else "",
            "email": order_id.partner_id.email if order_id.partner_id.email else "",
            "city": order_id.partner_id.city if order_id.partner_id.city else "",
            "fechanac": "20191122",
        }
        institution_discount = self.env[
            'institution.client'].sudo().get_institution_discount_by_partner(
            order_id.partner_id.id)

        if payment_transaction.payment_method_id.code == 'deuna':
            id_inst = institution_discount.get("institution_id") if institution_discount else -1
            cfp = {
                "cambio": 0.0,
                "idinst": int(id_inst),
                "efectivo": 0.0,
                "efectivo_nc": 0.0,
                "anticipo": 0.0,
                "alcance_nc": 0.0,
                "nro_ret": "",
                "val_ch": self.amount_total,
                "nro_ch": payment_transaction.payment_transaction_id,
                "idbank_ch": 45,
                "cta_ch": payment_transaction.payment_transaction_id,
                "fecha_ch": self.invoice_date.strftime('%Y%m%d'),
                "titular_ch": order_id.partner_id.name.upper(),
                "nOportunidad": 1,
                "lPacifico": 0
            }
        else:
            nuvei_transaction = self.env['nuvei.transaction'].sudo().search(
                [('ltp_id', '=', payment_transaction.payment_transaction_id)], limit=1)

            if nuvei_transaction:
                card_data = nuvei_transaction.get_card_from_raw()
                card_code = self._get_card_code(card_data.get('type', ''))
                cfp = {
                    "cambio": 0,
                    "idinst": institution_discount.get(
                        "institution_id") if institution_discount else -1,
                    "efectivo": 0.0,
                    "efectivo_nc": 0.0,
                    "anticipo": 0.0,
                    "alcance_nc": 0.0,
                    "nro_ret": "",
                    "val_tc": self.amount_total,
                    "voucher_tc": nuvei_transaction.transaction_id,
                    "idbank_tc": card_code,  # desde de la documentacion
                    "lote_tc": card_data.get('number'),
                    "titular_tc": card_data.get('holder_name'),
                    "bin_tc": card_data.get('bin'),
                    "nOportunidad": 1,
                    "lPacifico": 0
                }

        produc_lines = []

        for line in self.invoice_line_ids:
            if line.product_id.product_tmpl_id.id_database_old != '-999':

                if line.product_id.product_tmpl_id.sale_uom_ecommerce:
                    uom = line.product_id.product_tmpl_id.uom_po_id.factor_inv
                    prod_dict = [
                        int(line.product_id.id_database_old),
                        line.quantity * uom,
                        round(line.price_unit, 2),
                        int(line.tax_ids.amount) if line.tax_ids else 0,
                        round(line.price_unit * line.quantity * (line.discount / 100), 2),
                        3 if line.price_unit == 0 else 0,
                        round(line.discount, 2)
                    ]
                else:
                    prod_dict = [
                        int(line.product_id.id_database_old),
                        line.quantity,
                        round(line.price_unit, 2),
                        int(line.tax_ids.amount) if line.tax_ids else 0,
                        round(line.price_unit * line.quantity * (line.discount / 100), 2),
                        3 if line.price_unit == 0 else 0,
                        round(line.discount, 2)
                    ]

                produc_lines.append(prod_dict)

        productos_info_cdet = {
            "fields": [
                "iditem",
                "cantidad",
                "precio",
                "piva",
                "descuento",
                "promocion",
                "pdesc"
            ],
            "data": produc_lines
        }

        zona_horaria_ecuador = pytz.timezone('America/Guayaquil')
        fecha_hora_ecuador = datetime.now(zona_horaria_ecuador)
        l_sync_date = fecha_hora_ecuador + timedelta(minutes=3)
        formato_fecha_hora = fecha_hora_ecuador.strftime(
            '%Y-%m-%d %H:%M:%S')
        fecha_hora_lsync = l_sync_date.strftime(
            '%Y-%m-%d %H:%M:%S')
        total_discount_value = self.get_total_discount()
        factura = {
            "idcustomer": order_id.partner_id.id_database_old,
            "iduser": self.invoice_user_id.employee_id.id_employeed_old if self.invoice_user_id.employee_id.id_employeed_old else 1,
            "t_init": formato_fecha_hora,
            "subtotal": round(self.amount_untaxed, 2),
            "iva": self.amount_tax,
            "total": self.amount_total,
            "descuento": total_discount_value,
            "nota": ".",
            "idbodega": order_id.warehouse_id.external_id if order_id.warehouse_id.external_id else 1,
            "formapago": 9,
            "l_sync": 0,
            "l_close": 1,
            "l_auth": 0,
            "l_void": 0,
            "l_file": 0,
            "nprint": 1,
            "serie": "002100",
            "ccust": cliente_info,
            "cfp": cfp,
            "cdet": productos_info_cdet,

            "t_close": formato_fecha_hora,
            "t_sync": fecha_hora_lsync,
            "piva": 15,
            "claveacceso": self.l10n_ec_authorization_number if self.l10n_ec_authorization_number else "",
            "l_cust": 1,
            "is_fe": 1,
            "subtx": self.get_total_products_with_vat(),
            "subt0": self.get_total_products_without_vat(),
            "tipo": 1,
            "is_chatboot": False,
            "digital_media": "AppMovil",
            "cupon": False

        }
        json_storage_model = self.env['json.storage']
        json_storage_model.sudo().create({
            'json_data': json.dumps([{"factura": factura}],
                                    indent=4),
            'employee': f"{self.invoice_user_id.employee_id.name}",
            'pos_order_id': "",
            'id_point_of_sale': "",
            'client_invoice': order_id.partner_id.vat,
            'pos_order': "",
            'id_database_old_invoice_client': order_id.partner_id.id_database_old,
            'invoice_id': self.id,
        })

    @staticmethod
    def _get_card_code(type):
        card_types = {
            'vi': 11,
            'mc': 12,
            'ax': 14,
            'dc': 32,
            'di': 13,
            'ms': 16,
        }
        return card_types.get(type.lower(), 99)
