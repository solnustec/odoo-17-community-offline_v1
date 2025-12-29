# -*- coding: utf-8 -*-
# from odoo import http


# class PosOrderSearch(http.Controller):
#     @http.route('/pos_order_search/pos_order_search', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/pos_order_search/pos_order_search/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('pos_order_search.listing', {
#             'root': '/pos_order_search/pos_order_search',
#             'objects': http.request.env['pos_order_search.pos_order_search'].search([]),
#         })

#     @http.route('/pos_order_search/pos_order_search/objects/<model("pos_order_search.pos_order_search"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('pos_order_search.object', {
#             'object': obj
#         })

