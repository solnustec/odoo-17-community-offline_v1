import json

from odoo import http
from odoo.http import request, Response
from .api_security import validate_api_static_token


class Auth(http.Controller):

    @http.route('/api/store/paymentez', type='http', auth='public',
                methods=['GET'],
                csrf=False, cors="*")
    @validate_api_static_token
    def get_payment_credentials(self):
        try:
            app_code = request.env['ir.config_parameter'].sudo().get_param(
                'paymentez_app_code')
            app_key = request.env['ir.config_parameter'].sudo().get_param(
                'paymentez_app_key')
            app_url = request.env['ir.config_parameter'].sudo().get_param(
                'paymentez_app_url')
            if not app_code or not app_key or not app_url:
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'Error interno del servidor, no se pudieron obtener las credenciales de Paymentez',
                    'data': None
                }), status=404, content_type='application/json')
            return Response(json.dumps(
                {
                    'status': 'success',
                    'message': 'Credenciales obtenidas exitosamente',
                    'data': {
                        'app_code': app_code,
                        'app_secret': app_key,
                        'app_url': app_url
                    }
                }
            ), status=200, content_type='application/json')
        except Exception as e:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'Ha ocurrido un error en la solicitud' + str(e),
                    'data': None
                }
            ), status=500, content_type='application/json')
