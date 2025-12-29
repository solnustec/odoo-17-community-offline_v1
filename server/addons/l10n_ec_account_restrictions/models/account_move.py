# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.constrains('move_type', 'partner_id')
    def _check_liquidation_purchase_id_type(self):
        """
        verifica que al momento de generar una liquidacion en compras
        sea solo con cedula y que no este vacio el campo de cedula del partner
        """
        for move in self:
            is_liquidation = False
            if move.move_type == 'in_invoice' and move.l10n_latam_document_type_id:
                if move.l10n_latam_document_type_id.code == '03':
                    is_liquidation = True

            if is_liquidation and move.partner_id:
                vat = move.partner_id.vat if move.partner_id.vat else ''
                is_ruc = False
                if re.match(r'^\d{13}$', vat):
                    is_ruc = True
                if is_ruc:
                    raise ValidationError(_(
                        "No se puede generar una liquidación de compra para el proveedor '%s' "
                        "porque tiene RUC. Las liquidaciones de compra solo están permitidas "
                        "para proveedores con cédula.") %
                                          move.partner_id.name
                                          )
                if not vat or vat.strip() == '':
                    raise ValidationError(_(
                        "No se puede generar una liquidación de compra para el proveedor '%s' "
                        "porque no tiene ninguna identificación. El proveedor debe tener un número de "
                        "cédula  configurado.") %
                                          move.partner_id.name
                                          )

    @api.onchange('invoice_line_ids', 'currency_id')
    def _onchange_set_payment_method(self):
        """
        Si el monto total supera los 500, establece una forma de pago predeterminada.
        """
        for move in self:
            # out_invoice para las facturas de ventas
            if move.move_type == 'in_invoice':
                total = sum(line.price_total for line in move.invoice_line_ids)
                if total > 500:
                    sri_payment_method = self.env[
                        'l10n_ec.sri.payment'].search(
                        [('code', '=', '20')], limit=1).id
                    move.l10n_ec_sri_payment_id = sri_payment_method
                else:
                    sri_payment_method = self.env[
                        'l10n_ec.sri.payment'].search(
                        [('code', '=', '01')], limit=1).id
                    move.l10n_ec_sri_payment_id = sri_payment_method
