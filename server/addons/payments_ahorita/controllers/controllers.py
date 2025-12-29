# -*- coding: utf-8 -*-
# from odoo import http


# class PaymentsAhorita(http.Controller):
#     @http.route('/payments_ahorita/payments_ahorita', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/payments_ahorita/payments_ahorita/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('payments_ahorita.listing', {
#             'root': '/payments_ahorita/payments_ahorita',
#             'objects': http.request.env['payments_ahorita.payments_ahorita'].search([]),
#         })

#     @http.route('/payments_ahorita/payments_ahorita/objects/<model("payments_ahorita.payments_ahorita"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('payments_ahorita.object', {
#             'object': obj
#         })

