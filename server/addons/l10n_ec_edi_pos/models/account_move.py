from odoo import models, api
from odoo.addons.l10n_ec.models.res_partner import PartnerIdTypeEc

def verify_final_consumer(vat):
    return vat == '9' * 13  # final consumer is identified with 9999999999999


IN_RUC = '01'
IN_CEDULA = '02'
IN_PASSPORT = '03'
OUT_RUC = '04'
OUT_CEDULA = '05'
OUT_PASSPORT = '06'
FINAL_CONSUMER = '07'
FOREIGN = '08'


def extended_get_ats_code_for_partner(cls, partner, move_type):
    """
    Returns ID code for move and partner based on subset of Table 2 of SRI's ATS specification
    """
    partner_id_type = partner._l10n_ec_get_identification_type()
    if partner.vat and verify_final_consumer(partner.vat):
        return cls.FINAL_CONSUMER
    elif move_type.startswith('in_'):
        if partner_id_type == 'ruc':  # includes final consumer
            return cls.IN_RUC
        elif partner_id_type == 'cedula':
            return cls.IN_CEDULA
        elif partner_id_type in ['foreign', 'passport', 'ec_passport']:
            return cls.IN_PASSPORT
    elif move_type.startswith('out_'):
        if partner_id_type == 'ruc':  # includes final consumer
            return cls.OUT_RUC
        elif partner_id_type == 'cedula':
            return cls.OUT_CEDULA
        elif partner_id_type in ['foreign', 'passport', 'ec_passport']:
            return cls.OUT_PASSPORT


# Reemplazar el método original
PartnerIdTypeEc.get_ats_code_for_partner = classmethod(extended_get_ats_code_for_partner)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _l10n_ec_get_payment_data(self):
        # EXTENDS l10n_ec_edi
        # If an invoice is created from a pos order, then the payment is collected at the moment of sale.
        if self.pos_order_ids:
            pagos_raw = []
            for payment in self.pos_order_ids.payment_ids:
                pagos_raw.append({
                    'payment_code': payment.payment_method_id.l10n_ec_sri_payment_id.code,
                    'payment_name': payment.payment_method_id.l10n_ec_sri_payment_id.display_name,
                    'payment_total': abs(payment.amount),
                })
        else:
            pagos_raw = super()._l10n_ec_get_payment_data()

        total_factura = round(abs(self.amount_total_signed), 2)

        pagos_pos = [p for p in pagos_raw if p.get('payment_total', 0) > 0]
        if not pagos_pos or total_factura <= 0:
            return []

        grouped = {}
        for p in pagos_pos:
            code = str(p.get('payment_code') or '')
            name = p.get('payment_name') or ''
            amt = float(p.get('payment_total', 0))
            if amt <= 0:
                continue
            if code not in grouped:
                grouped[code] = {
                    'payment_code': code,
                    'payment_name': name,
                    'payment_total': 0.0,
                }
            grouped[code]['payment_total'] += amt

        pagos = list(grouped.values())
        for p in pagos:
            p['payment_total'] = round(p['payment_total'], 2)

        suma = round(sum(p['payment_total'] for p in pagos), 2)
        if abs(suma - total_factura) < 0.005:
            return pagos

        if suma > total_factura:
            exceso = round(suma - total_factura, 2)
            for p in pagos:
                if exceso <= 0:
                    break
                recorte = min(p['payment_total'], exceso)
                p['payment_total'] = round(p['payment_total'] - recorte, 2)
                exceso = round(exceso - recorte, 2)

        suma2 = round(sum(p['payment_total'] for p in pagos), 2)
        defecto = round(total_factura - suma2, 2)
        if abs(defecto) >= 0.01 and pagos:
            pagos[-1]['payment_total'] = round(pagos[-1]['payment_total'] + defecto, 2)

        pagos = [p for p in pagos if p['payment_total'] > 0]
        for p in pagos:
            p['payment_total'] = round(p['payment_total'], 2)

        return pagos

    def _l10n_ec_get_formas_de_pago(self):
        # EXTENDS l10n_ec_edi
        self.ensure_one()
        if self.l10n_ec_sri_payment_id.code == 'mpm' and (pos_order := self.pos_order_ids):
            return [payment.payment_method_id.l10n_ec_sri_payment_id.code for payment in pos_order.payment_ids]
        else:
            return super()._l10n_ec_get_formas_de_pago()
