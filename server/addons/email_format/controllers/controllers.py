# -*- coding: utf-8 -*-
# from odoo import http


# class EmailFormat(http.Controller):
#     @http.route('/email_format/email_format', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/email_format/email_format/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('email_format.listing', {
#             'root': '/email_format/email_format',
#             'objects': http.request.env['email_format.email_format'].search([]),
#         })

#     @http.route('/email_format/email_format/objects/<model("email_format.email_format"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('email_format.object', {
#             'object': obj
#         })

