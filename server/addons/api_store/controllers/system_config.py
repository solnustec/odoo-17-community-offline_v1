import json

from odoo import http
from odoo.http import request, Response
from .api_security import validate_api_static_token
from ..utils.time_cache import APICache


class SystemConfigController(http.Controller):
    api_cache = APICache(timeout=86400, max_size=1000)

    @http.route('/api/store/configs', type='http', auth='public', csrf=False,
                methods=['GET'], cors="*")
    @validate_api_static_token
    @api_cache.cache()
    def get_system_config(self, **kwargs):
        """
        Endpoint to retrieve  ir.config.parameter.
        """
        app_configurations = request.env['ir.config_parameter'].sudo().get_param(
            'app_mobile_configurations')


        return  Response(
            json.dumps(
                {
                    'status': 'success',
                    'message': 'Configuraciones obtenidas correctamente',
                    'data': [json.loads(app_configurations)]
                }
            ),
            status=200,
            content_type='application/json'
        )
