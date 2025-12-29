# -*- coding: utf-8 -*-
# from odoo import http


# class PosInvoiceNote(http.Controller):
#     @http.route('/pos_invoice_note/pos_invoice_note', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/pos_invoice_note/pos_invoice_note/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('pos_invoice_note.listing', {
#             'root': '/pos_invoice_note/pos_invoice_note',
#             'objects': http.request.env['pos_invoice_note.pos_invoice_note'].search([]),
#         })

#     @http.route('/pos_invoice_note/pos_invoice_note/objects/<model("pos_invoice_note.pos_invoice_note"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('pos_invoice_note.object', {
#             'object': obj
#         })

