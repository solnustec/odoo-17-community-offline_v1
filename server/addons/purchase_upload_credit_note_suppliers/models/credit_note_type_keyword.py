from odoo import models, fields, api

class CreditNoteTypeKeyword(models.Model):
    _name = "credit.note.type.keyword"
    _description = "Palabras clave para detectar tipo de nota de crédito"

    type_id = fields.Many2one(
        "credit.note.type",
        ondelete="cascade",
        required=True,
        string = "Tipo de nota de credito",
        help = "Tipo de nota de credito de acuerdo al motivo",
    )

    keyword = fields.Char(
        required=True,
        string="Palabra clave",
        help="Palabra clave que identifica a este tipo de nota de credito"
    )

    def _create_keywords(self, credit_note_type, keywords):
        for keyword in keywords:
            if not self.search([('keyword', '=', keyword)]):
                self.create({
                    'type_id': credit_note_type.id,
                    'keyword': keyword,
                })

    @api.model
    def init(self):
        # Buscar tipos de notas de credito
        product_return_type = self.env['credit.note.type'].search([('code', '=', 'product_return')]) or ""
        early_payment_type = self.env['credit.note.type'].search([('code', '=', 'early_payment')]) or ""
        discount_type = self.env['credit.note.type'].search([('code', '=', 'discount')]) or ""
        sponsorship_type = self.env['credit.note.type'].search([('code', '=', 'sponsorship')]) or ""
        rebate_type = self.env['credit.note.type'].search([('code', '=', 'rebate')]) or ""

        # Lista de palabras clave por cada tipo de nota de credito
        default_product_return_keywords = ["mal estado", "faltante", "devolucion", "a vencer", "fecha corta", "actualizacion de fecha", "expirado"]
        default_early_payment_keywords = ["pronto pago", "pp"]
        default_discount_keywords = ["descuento"]
        default_sponsorship_keywords = ["auspicio"]
        default_rebate_keywords = ["bonificacion", "rebate"]

        # Crear palabras clave
        if product_return_type:
            self._create_keywords(product_return_type, default_product_return_keywords)
        if early_payment_type:
            self._create_keywords(early_payment_type, default_early_payment_keywords)
        if discount_type:
            self._create_keywords(discount_type, default_discount_keywords)
        if sponsorship_type:
            self._create_keywords(sponsorship_type, default_sponsorship_keywords)
        if rebate_type:
            self._create_keywords(rebate_type, default_rebate_keywords)