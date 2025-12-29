import functools
import json

from odoo import  exceptions
from odoo.http import request, Response

class ApiSecurityMiddleware:
    @classmethod
    def validate_static_token(cls):
        # Obtener el token estático configurado en los parámetros del sistema
        static_api_token = request.env['ir.config_parameter'].sudo().get_param(
            'api_mobile_static_token')
        request_token = request.httprequest.headers.get('X-API-Token')
        if not static_api_token or not request_token or request_token != static_api_token:
            raise exceptions.AccessDenied(message='Token de API inválido')

        return True

#decorador para validar el token estático
def validate_api_static_token(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            ApiSecurityMiddleware.validate_static_token()
            return func(*args, **kwargs)
        except exceptions.AccessDenied as e:
            return Response(
                json.dumps({
                    'status': 'error',
                    'code': 401,
                    'message': "Acceso no Autorizado"
                }),
                status=401,
                content_type='application/json'
            )
    return wrapper