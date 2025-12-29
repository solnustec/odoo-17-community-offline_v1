import time

from .api_security import validate_api_static_token
from odoo import http
from odoo.http import request, Response
import json

from ..utils.time_cache import APICache


class Country(http.Controller):
    api_cache = APICache(timeout=86400, max_size=1000)

    @http.route('/api/store/countries', type='http', auth='public',
                methods=['GET'],
                csrf=False, cors="*")
    @validate_api_static_token
    @api_cache.cache()
    def get_countries(self):
        time_start = time.time()
        try:
            # Obtener los paises
            countries = request.env['res.country'].sudo().search([])
            country_data = [{
                'id': country.id,
                "name": country.name
            } for country in countries]
            time_end = time.time()

            return Response(
                json.dumps(
                    {
                        'status': 'success',
                        'message': 'Paises obtenidos exitosamente',
                        'data': country_data
                    }
                ),
                status=200,
                content_type='application/json'
            )
        except Exception as e:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        "message": 'Hubo un error al obtener los paises:' + str(
                            e),
                        'data': None
                    }
                ),
                status=400,
                content_type='application/json'
            )

    @http.route('/api/store/state/<int:country_id>', type='http',
                auth='public',
                methods=['GET'],
                csrf=False, cors="*")
    @validate_api_static_token
    @api_cache.cache()
    def get_states(self, country_id):
        time_start = time.time()
        try:
            # Obtener los cantones por pais
            country_id = int(country_id)
            country = request.env['res.country'].sudo().browse(country_id)
            states = request.env['res.country.state'].sudo().search(
                [('country_id', '=', country.id)])
            state_list = [{
                'id': state.id,
                'name': state.name,
                'code': state.code,
                'latitude': state.latitude,
                'longitude': state.longitude
            } for state in states]
            time_end = time.time()
            print("Tiempo de respuesta get_states:", time_end - time_start)
            return Response(
                json.dumps(
                    {
                        'status': 'success',
                        'message': 'Estados obtenidos exitosamente',
                        'data': state_list
                    }),
                status=200,
                content_type='application/json'
            )

        except Exception as e:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        "message": 'Hubo un error al obtener las provincias:' + str(
                            e),
                        'data': None
                    }),
                status=500,
                content_type='application/json'
            )

