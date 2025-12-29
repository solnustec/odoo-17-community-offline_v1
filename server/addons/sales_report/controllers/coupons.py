import json

from odoo import http
from odoo.http import route, request, Response


class CouponsController(http.Controller):

    @route('/api/promotions/coupons', type='http', auth='public', cors="*",
           methods=['POST'], csrf=False)
    def product_promotion_coupons(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        for coupon in data:
            product_id = coupon.get('product_id')
            coupon = coupon.get('coupon')

            if not product_id:
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'El ID del producto es requerido'
                }), status=400, mimetype='application/json')

            Product = request.env['product.product']
            product_id = Product.sudo().search(
                [('id_database_old', '=', product_id)])
            product_id.write({'coupon_info': coupon})
        return Response(
            json.dumps({'status': 'success', 'message': 'Cupón actualizado'}),
            status=200,
            mimetype='application/json'
        )
