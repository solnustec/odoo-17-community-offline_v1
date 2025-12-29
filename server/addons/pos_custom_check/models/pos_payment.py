# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
import logging

_logger = logging.getLogger(__name__)


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    # CHEQUE
    check_number = fields.Char()
    check_bank_account = fields.Char(string="Número de cuenta", required=False)
    check_owner = fields.Char(string="Cliente",required=False)
    bank_id = fields.Many2one('res.bank', string="Nombre del banco",required=False)
    date = fields.Date(default=fields.Date.today,required=False)
    institution_cheque = fields.Char(string="ID Institucion",required=False)
    institution_discount = fields.Char(string="Institucion descuento",required=False)

    # TARJETAS
    number_voucher = fields.Char(string="Nro vaucher",required=False)
    type_card = fields.Many2one('credit.card', string="Tipo de tarjeta", required=False)
    number_lote = fields.Char(string="Nro lote",required=False)
    holder_card = fields.Char(string="Titular TC",required=False)
    bin_tc = fields.Char(string="BIN TC (6 dig.primeros)",required=False)
    institution_card = fields.Char(string="ID Institucion",required=False)
    selecteInstitutionCredit = fields.Char(
        string="Institución de crédito (ID)",
        help="ID de la institución seleccionada para método de pago CREDITO"
    )

    def export_as_JSON(self):
        result = super(PosPayment, self).export_as_JSON()
        result['selecteInstitutionCredit'] = self.selecteInstitutionCredit
        return result


