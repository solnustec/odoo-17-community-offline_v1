from odoo import models, fields, api

class CreditNoteType(models.Model):
    _name = 'credit.note.type'
    _description = 'Tipos de Nota de Crédito'

    name = fields.Char(
        string="Nombre",
        required=True,
        help="Nombre del tipo de nota de crédito"
    )

    code = fields.Char(
        string="Código Interno",
        required=True,
        help="Identificador técnico del tipo (ej: product_return)"
    )

    keyword_ids = fields.One2many(
        "credit.note.type.keyword",
        "type_id",
        string="Palabras clave"
    )

    account_id = fields.Many2one(
        "account.account",
        string="Cuenta Contable",
        help="Cuenta contable a aplicar automáticamente"
    )

    second_account_id = fields.Many2one(
        "account.account",
        string="Segunda Cuenta Contable",
        help="Segunda cuenta contable a aplicar automáticamente"
    )
    id_database_old = fields.Char("Id base antigua")

    active = fields.Boolean(default=True)

    @api.model
    def init(self):
        default_account_product_return_iva_15 = self.env['account.account'].search([('code', '=', 52022302)]) or ""
        default_account_product_return_iva_0 = self.env['account.account'].search([('code', '=', 52022302)]) or ""
        default_account_early_payment = self.env['account.account'].search([('code', '=', 53010106)]) or ""
        default_account_discount = self.env['account.account'].search([('code', '=', 53010103)]) or ""
        default_account_sponsorship = self.env['account.account'].search([('code', '=', 53010103)]) or ""
        default_account_rebate = self.env['account.account'].search([('code', '=', 53010105)]) or ""

        default_types = [
            ("Devolución de producto", "product_return", default_account_product_return_iva_15, default_account_product_return_iva_0),
            ("Pronto pago", "early_payment", default_account_early_payment, ""),
            ("Descuento", "discount", default_account_discount, ""),
            ("Auspicio", "sponsorship", default_account_sponsorship, ""),
            ("Rebate", "rebate", default_account_rebate, ""),
            #("Devolución de producto", "product_return", "", ""),
            #("Pronto pago", "early_payment", "", ""),
            #("Descuento", "discount", "", ""),
            #("Rebate", "rebate", "", ""),
        ]

        for name, code, account, second_account in default_types:
            if not self.search([('code', '=', code)]):
                self.create({'name': name, 'code': code, 'account_id': account.id if account else "", "second_account_id": second_account.id if second_account else ""})
                #self.create({'name': name, 'code': code})