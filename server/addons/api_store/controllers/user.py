import base64
import datetime

from .api_security import validate_api_static_token
from odoo import http
from odoo.http import request, Response

import json

from .jwt import validate_jwt


class User(http.Controller):
    @http.route('/api/store/user/info/<int:userid>', type='http',
                auth='public',
                methods=['GET'],
                csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def get_user_info(self, userid):
        jwt_data = getattr(request, '_jwt_data', {})
        user_id = jwt_data.get('user_id')
        partner_id = jwt_data.get('partner_id')
        if not user_id or not partner_id:
            return http.Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "El token proporcionado no es valido",
                        "data": None
                    }
                ),
                status=403,
                mimetype='application/json'
            )
        if user_id != userid:
            return http.Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "El token proporcionado no pertenece al usuario",
                        "data": None
                    }
                ),
                status=403,
                mimetype='application/json'
            )
        try:
            user = request.env['res.users'].sudo().search(
                [('id', '=', user_id)],
                limit=1)
            base_url = request.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')
            unique_image_key = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            avatar_base64 = None
            if user.image_256:
                avatar_base64 = user.image_256.decode('utf-8')
            return Response({
                json.dumps(
                    {
                        "status": "success",
                        "message": "Información del usuario",
                        "data": {
                            "name": user.name,
                            "email": user.email,
                            "city": user.city,
                            "mobile": user.mobile,
                            "vat": user.vat,
                            # 'is_oauth_user': bool(user.oauth_provider_id),
                            # 'oauth_provider': user.oauth_provider_id.name if user.oauth_provider_id else False,
                            "avatar_256": f"{base_url}/web/image/res.users/{user.id}/image_256?{unique_image_key}",
                            "avatar_base64": avatar_base64,
                        }
                    }
                ),
            }, status=200,
                content_type='application/json')
        except Exception as e:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        "message": str(e),
                        "data": None
                    }),
                status=400,
                content_type='application/json'
            )

    @http.route('/api/store/user/info/update', type='http', methods=['POST',],
                auth='public', csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def update_user_info(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        jwt_data = getattr(request, '_jwt_data', {})
        user_id = jwt_data.get('user_id')
        partner_id = jwt_data.get('partner_id')
        if not user_id or not partner_id:
            return http.Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "El token proporcionado no es valido",
                        "data": None
                    }
                ),
                status=403,
                mimetype='application/json'
            )
        try:
            if user_id != data.get('user_id'):
                return http.Response(
                    json.dumps(
                        {
                            "status": "error",
                            "message": "El token proporcionado no pertenece al usuario",
                            "data": None
                        }
                    ),
                    status=403,
                    mimetype='application/json'
                )
            user = request.env['res.users'].sudo().search(
                [('id', '=', user_id)],
                limit=1)
            update_fields = {}
            allowed_fields = ['name', 'email', 'mobile']
            for field in allowed_fields:
                if field in kwargs:
                    update_fields[field] = data.get(field)
            if update_fields:
                user.write(update_fields)
            return Response({
                json.dumps(
                    {
                        "status": "success",
                        "message": "Información del usuario actualizada correctamente",
                        "data": None
                    }
                ),
            }, status=200,
                content_type='application/json')
        except Exception as e:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        "message": str(e),
                        "data": None
                    }),
                status=400,
                content_type='application/json'
            )
