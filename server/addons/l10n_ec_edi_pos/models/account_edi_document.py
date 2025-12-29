from odoo import models, api


# class AccountEdiDocument(models.Model):
#     _inherit = 'account.edi.document'
#
#     # TODO remover el  vals['edi_state'] = 'sent' para evitar que las facturas del odoo se envien al sri
#     @api.model_create_multi
#     def create(self, vals_list):
#         for vals in vals_list:
#             vals['state'] = 'sent'
#         documents = super(AccountEdiDocument, self).create(vals_list)
#         return documents
