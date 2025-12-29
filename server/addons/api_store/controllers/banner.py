import base64

from .api_security import validate_api_static_token
from odoo import http
from odoo.http import request, Response
import json

from ..utils.time_cache import APICache


class BannerController(http.Controller):
    api_cache = APICache(timeout=86400, max_size=1000)

    @http.route('/api/store/banners', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    @validate_api_static_token
    @api_cache.cache()
    def get_active_banners(self):
        try:
            banners = request.env['api_store.banner'].sudo().search(
                [('enabled', '=', True)])
            base_url = request.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')
            banner_list = []

            for banner in banners:
                # Usar la ruta pública que crearemos
                image_url = f"{base_url}{banner.s3_image_url}"
                # image_url = f"http://192.168.0.165:8069/api/banner/image/{banner.id}"
                banner_list.append({
                    'id': banner.id,
                    'name': banner.name,
                    'url': banner.url,
                    'image_url': image_url,  # Esta será la URL pública
                })
            return Response(
                json.dumps(
                    {
                        'status': 'success',
                        'message': 'Banners obtenidos correctamente',
                        'data': banner_list
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
                        "message": "Hubo un error al obtener los banners " + str(
                            e),
                        'data': None
                    }
                ),
                status=500,
                content_type='application/json'
            )

    @http.route('/api/banner/image/<int:banner_id>',
                type='http', auth='public', methods=['GET'])
    @validate_api_static_token
    def get_banner_image(self, banner_id, **kwargs):
        banner = request.env['api_store.banner'].sudo().search([
            ('id', '=', banner_id),
            ('enabled', '=', True)
        ], limit=1)

        if not banner or not banner.image:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'Banner no encontrado',
                        'data': None
                    }
                ),
                status=404,
                content_type='application/json'
            )

        image_data = base64.b64decode(banner.image)

        headers = [
            ('Content-Type', 'image/png'),
            ('Content-Length', len(image_data)),
            ('Cache-Control', 'no-store, max-age=0'),
            ('Pragma', 'no-cache')
        ]

        return request.make_response(image_data, headers)
