from odoo import models, fields

class CreditCard(models.Model):
    _name = 'credit.card'
    _description = 'Registro de Tarjetas de Crédito'

    name_card = fields.Char(string='TARJETA', required=True)
    code_card = fields.Char(string='COD TARJETA', required=True)