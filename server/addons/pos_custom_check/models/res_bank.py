from odoo import models, fields

class ResBank(models.Model):
    _inherit = 'res.bank'

    codigo_banco = fields.Char(
        string="Código Banco"
    )
    enable_delete_payment = fields.Boolean(default=False, string="Habilitar Eliminar de Método de Pago")
