# -*- coding: utf-8 -*-
# from odoo import http


# class PromotionsByDay(http.Controller):
#     @http.route('/promotions_by_day/promotions_by_day', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/promotions_by_day/promotions_by_day/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('promotions_by_day.listing', {
#             'root': '/promotions_by_day/promotions_by_day',
#             'objects': http.request.env['promotions_by_day.promotions_by_day'].search([]),
#         })

#     @http.route('/promotions_by_day/promotions_by_day/objects/<model("promotions_by_day.promotions_by_day"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('promotions_by_day.object', {
#             'object': obj
#         })

