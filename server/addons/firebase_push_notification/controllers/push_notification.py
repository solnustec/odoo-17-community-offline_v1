import json

from odoo import http
from odoo.http import request, Response


class PushNotification(http.Controller):
    @http.route('/firebase/create', type='http', auth="public",
                csrf=False)
    def save_firebase_device_token(self, **post):

        try:
            data = json.loads(request.httprequest.data)
            required_fields = ['register_id', 'platform', 'device_name']
            for field in required_fields:
                if field not in data:
                    return Response(
                        json.dumps(
                            {
                                'status': 'error',
                                "message": "Error Faltan campos requeridos",
                                'data': None
                            }),
                        status=400
                    )
            if data.get('user_id') =="":
                #reigstrar dispositivo sin usuario
                existing = request.env['push.device'].sudo().search([
                    ('register_id', '=', data['register_id'])
                ], limit=1)
                if not existing:
                    request.env['push.device'].sudo().create({
                        'register_id': data['register_id'],
                        'platform': data['platform'],
                        'name': data['device_name'],
                        'active': True
                    })
                    return Response(
                        json.dumps({
                            'status': 'success',
                            "message": "Token de usuario actualizado",
                            'data': None
                        }),
                        status=200
                    )
            # si viene con user_id
            else:
            # buscar si el usuario ya tiene un dispositivo registrado

                existing = request.env['push.device'].sudo().search([
                    ('user_id', '=', data['user_id'])
                ], limit=1)
                if existing and existing.register_id != data['register_id']:
                    existing.write({
                        'platform': data['platform'],
                        'name': data['device_name'],
                        'user_id': data['user_id'],
                        'register_id': data['register_id'],
                        'active': True
                    })
                    return Response(
                        json.dumps({
                            'status': 'success',
                            "message": "Token de usuario actualizado",
                            'data': None
                        }),
                        status=200)
                if not existing:
                    request.env['push.device'].sudo().create({
                        'register_id': data['register_id'],
                        'platform': data['platform'],
                        'name': data['device_name'],
                        'user_id': data['user_id'],
                        'active': True
                    })
                    #buscar si existe otro dispositivo con el mismo register_id y eliminarlo
                    existing_register = request.env['push.device'].sudo().search([
                        ('register_id', '=', data['register_id']),
                        ('user_id', '=', False)
                    ], limit=1)
                    if existing_register:
                        existing_register.unlink()
                    return Response(
                        json.dumps({
                            'status': 'success',
                            "message": "Token de usuario actualizado",
                            'data': None
                        }),
                        status=200
                    )
                else:
                    return Response(
                        json.dumps({
                            'status': 'success',
                            "message": "Token de usuario actualizado",
                            'data': None
                        }),
                        status=200
                    )
        except Exception as e:
            return Response(
                json.dumps({'error': str(e)}), status=500
            )
    #delete device token
    @http.route('/firebase/delete', type='http', auth='public',
                methods=['POST'],
                csrf=False, cors="*")
    def delete_device_token(self, **kwargs):
        data = json.loads(request.httprequest.data)
        user_id = data.get('user_id')

        if not user_id:
            return Response(
                json.dumps({'error': 'user_id es requerido'}),
                status=400
            )

        device = request.env['push.device'].sudo().search([
            ('user_id', '=', user_id)
        ], limit=1)

        if not device:
            return Response(
                json.dumps({
                    'error': 'No se encontró un dispositivo para el usuario'}),
                status=404)
        device.unlink()

        return Response(
            json.dumps({'message': 'Dispositivo eliminado'}), status=200)
    @http.route('/firebase/update', type='http', auth='public',
                methods=['POST'],
                csrf=False, cors="*")
    def update_device_token(self, **kwargs):
        data = json.loads(request.httprequest.data)
        user_id = data.get('user_id')
        register_id = data.get('register_id')

        if not user_id or not register_id:
            return Response(
                json.dumps({'error': 'user_id y register_id son requeridos'}),
                status=400
            )

        device = request.env['push.device'].sudo().search([
            ('user_id', '=', user_id)
        ], limit=1)

        if not device:
            return Response(
                json.dumps({
                    'error': 'No se encontró un dispositivo para el usuario'}),
                status=404)
        device.write({'register_id': register_id})

        return Response(
            json.dumps({'message': 'Dispositivo actualizado'}), status=200)
