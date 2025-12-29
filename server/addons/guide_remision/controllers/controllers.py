# -*- coding: utf-8 -*-
# from odoo import http


# class GuideRemision(http.Controller):
#     @http.route('/guide_remision/guide_remision', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/guide_remision/guide_remision/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('guide_remision.listing', {
#             'root': '/guide_remision/guide_remision',
#             'objects': http.request.env['guide_remision.guide_remision'].search([]),
#         })

#     @http.route('/guide_remision/guide_remision/objects/<model("guide_remision.guide_remision"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('guide_remision.object', {
#             'object': obj
#         })

