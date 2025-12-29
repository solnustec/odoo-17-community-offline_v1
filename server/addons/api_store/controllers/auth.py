import base64
import datetime
from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request, Response, _logger
import json
import jwt
from odoo.tools import email_normalize
from .api_security import validate_api_static_token
from .jwt import validate_jwt


class Auth(http.Controller):

    @http.route('/api/store/register', type='http', auth='public',
                methods=['POST'],
                csrf=False, cors="*")
    @validate_api_static_token
    def register(self, **kwargs):
        # try:
        # Leer datos de la solicitud
        data = json.loads(request.httprequest.data.decode('utf-8'))

        # Validación básica
        if not data.get('username'):
            return Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "El correo es requerido",
                        "data": None
                    }
                ),
                status=400,
                content_type='application/json'
            )
        if not data.get('password'):
            return Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "La contraseña es requerida",
                        "data": None
                    }
                ),
                status=400,
                content_type='application/json'
            )
        if not data.get('email'):
            return Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "El correo es requerido",
                        "data": None
                    }
                ),
                status=404,
                content_type='application/json'
            )

        is_valid = self.validate_email(data.get('email').lower())
        if not is_valid:
            return Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "Por favor ingresa un correo válido",
                        "data": None
                    }
                ),
                status=404,
                content_type='application/json'
            )
        partner_id = request.env['res.partner'].sudo().search([
            ('vat', '=', data.get('vat')), ('type', '=', 'contact')
        ], limit=1)
        # remove + from phone number
        if data.get('mobile'):
            data['mobile'] = data['mobile'].replace('+', '').replace(' ',
                                                                     '')
        # Si el partner ya existe, actualizar sus datos
        if partner_id:
            # update the partner with the new data
            partner_id.sudo().write({
                'name': data.get('name'),
                'mobile': data.get('mobile'),
                'street': data.get('street'),
                'city': data.get('city'),
                'email': data.get('email').lower(),
                'country_id': data.get("country_id", 63),
                'l10n_latam_identification_type_id': data[
                    'identification_type_id'],
                'vat': data['vat'],
                # 'partner_reference_id': partner_id.id,
                'state_id': data.get("state_id", 1413),
            })
        # 4 cedula 5 ruc 2 pasaporte
        else:
            partner_id = request.env['res.partner'].sudo().create({
                'name': data['name'],
                'email': data['email'].lower(),
                'mobile': data['mobile'],
                'street': data['street'],
                'city': data['city'],
                'country_id': data.get("country_id", 63),
                'l10n_latam_identification_type_id': data[
                    'identification_type_id'],
                'vat': data['vat'],
                'type': 'contact',
                # 'partner_reference_id': partner_id.id,
                'state_id': data.get("state_id", 1413),
            })
        # crear la direccion de facuturacion vacia para el usuario

        # partner_id.sudo().write({
        #     'parent_reference_id': partner_id.id,
        # })
        # verificar si el correo ya esta registrado
        if request.env['res.users'].sudo().search(
                [('login', '=', data.get('email').lower())]):
            return Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"Ya existe un usuario registrado con este correo {data.get('email')}, intenta restablecer la contraseña",
                        "data": None
                    }
                ),
                status=400,
                content_type='application/json'
            )
        # Crear un nuevo usuario
        user = request.env['res.users'].sudo().create({
            'name': data.get('name'),
            'login': data.get('username'),
            'password': data.get('password'),
            'groups_id': [(6, 0, [10])],
            'partner_id': partner_id.id,
            'identification_id': data.get('identification'),
        })
        # crea la direccion de facturacion del usuario

        # Generar el token
        payload = {
            'user_id': user.id,
            "partner_id": partner_id.id
        }
        JWT_SECRET_KEY = request.env[
            'ir.config_parameter'].sudo().get_param(
            'jwt_secret_key')
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')

        # Responder con éxito
        return Response(
            json.dumps(
                {
                    "status": "success",
                    "message": "Usuario registrado exitosamente",
                    "data": {
                        'token': token,
                        'user_id': user.id,
                        'partner_id': partner_id.id,
                        'email': user.email,
                    }
                }),
            status=201,
            content_type='application/json'
        )
        # except ValidationError as e:
        #     return Response(
        #         json.dumps(
        #             {
        #                 "status": "error",
        #                 'message': "Ha ocurrido un error, intente nuevamente " + str(
        #                     e),
        #                 "data": None
        #             }
        #         ),
        #         status=404,
        #         content_type='application/json'
        #     )
        # except Exception as e:
        #     return Response(
        #         json.dumps(
        #             {
        #                 "status": "error",
        #                 'message': "Ha ocurrido un error, intente nuevamente: " + str(
        #                     e),
        #                 "data": None
        #             }
        #         ),
        #         status=500,
        #         content_type='application/json'
        #     )

    def validate_email(self, email):
        """Validar formato de email usando funciones nativas de Odoo"""
        try:
            normalized_email = email_normalize(email)
            if not normalized_email:
                return False
            return normalized_email
        except Exception:
            return False

    @http.route('/api/store/auth/', type='http', auth='public',
                methods=["POST"],
                csrf=False, cors="*")
    @validate_api_static_token
    def authenticate(self, *args, **post):

        data = request.httprequest.get_json(silent=True)
        if not data or not all(k in data for k in ['login', 'password']):
            return Response(
                json.dumps(
                    {
                        "status": "error",
                        'message': 'El correo y la contraseña son requeridos',
                        "data": None
                    }
                ),
                status=400,
                content_type='application/json'
            )

        login = data['login']
        password = data['password']

        user = request.env['res.users'].sudo().search([('login', '=', login)],
                                                      limit=1)
        admin_group = request.env.ref('base.group_system')
        if user and admin_group in user.groups_id:
            return Response(
                json.dumps(
                    {
                        'status': "error",
                        'message': 'Usuario no encontrado',
                        'data': None
                    }
                ),
                status=401,
                content_type='application/json'
            )

        try:
            uuid = request.session.authenticate(request.session.db, login,
                                                password)
        except Exception as e:
            return Response(
                json.dumps(
                    {
                        "status": "error",
                        'message': 'Credenciales incorrectas',
                        "data": None
                    }
                ),
                status=401,
                content_type='application/json'
            )
        # Verificar si el usuario existe y generar el JWT

        if user and uuid:

            payload = {
                'user_id': user.id,
                "partner_id": user.partner_id.id
            }
            # test
            JWT_SECRET_KEY = request.env[
                'ir.config_parameter'].sudo().get_param(
                'jwt_secret_key')
            token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')
            base_url = request.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')
            unique_image_key = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

            avatar_base64 = None
            if user.image_256:
                avatar_base64 = user.image_256.decode('utf-8')
            data = {
                'token': token,
                'user_id': user.id,
                'email': user.login,
                'partner_id': user.partner_id.id,
                'name': user.name,
                'mobile': user.partner_id.mobile,
                'phone': user.partner_id.phone if user.partner_id.phone else user.partner_id.mobile,
                'avatar_256': f"{base_url}/web/image/res.users/{user.id}/avatar_256?unique={unique_image_key}" if user.image_1920 else None,
                'avatar_base64': avatar_base64
            }
            try:
                message_record = request.env[
                    'notification.message'].sudo().get_message_by_type(
                    'login')
                request.env['user.notification'].sudo().create({
                    'name': message_record.title,
                    'user_id': user.id,
                    'message': f"{message_record.body}",
                })
                # device = request.env['push.device'].find_by_user(user.id)
                # request.env['firebase.service'].send_push_notification(device.register_id, title=message_record.title, body=message_record.body)
                request.env['firebase.service']._send_single_push_notification(user_id=user.id,
                                                                               title=message_record.title,
                                                                               body=message_record.body)
            except Exception as e:
                pass
            return Response(
                json.dumps(
                    {
                        'status': "success",
                        "message": "Autenticación exitosa",
                        'data': data
                    }
                ),
                status=200,
                content_type='application/json'
            )

        return Response(
            json.dumps(
                {
                    'status': "error",
                    'message': 'Credenciales incorrectas',
                    'data': None
                }
            ),
            status=401,
            content_type='application/json'
        )

    @http.route('/api/store/update/profile/image/<int:userid>', type='http',
                auth='public',
                methods=['POST'], csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def update_profile_image(self, userid, **post, ):
        try:
            jwt_data = getattr(request, '_jwt_data', {})
            user_id = jwt_data.get('user_id')
            partner_id = jwt_data.get('partner_id')
            if not user_id or not partner_id:
                return Response(
                    json.dumps(
                        {"status": "error", "message": "El token proporcionado no es válido",
                         "data": None}
                    ),
                    status=403, content_type='application/json'
                )

            if int(user_id) != int(userid):
                return Response(
                    json.dumps(
                        {"status": "error",
                         "message": "El token proporcionado no pertenece al usuario", "data": None}
                    ),
                    status=403, content_type='application/json'
                )

            image_data = None
            image_string = None

            # Intentar JSON body
            data_json = request.httprequest.get_json(silent=True)
            if data_json and isinstance(data_json, dict) and data_json.get('avatar_256'):
                image_string = data_json.get('avatar_256')

            # form-data / kwargs
            elif 'avatar_256' in post:
                image_string = post.get('avatar_256')
            elif 'avatar_256' in request.params:
                image_string = request.params.get('avatar_256')

            # archivo subido (multipart/form-data)
            elif getattr(request.httprequest, 'files',
                         None) and 'avatar_256' in request.httprequest.files:
                file_storage = request.httprequest.files['avatar_256']
                file_content = file_storage.read()
                if not file_content:
                    return Response(
                        json.dumps({"status": "error", "message": "Archivo vacío", "data": None}),
                        status=400, content_type='application/json')
                image_data = base64.b64encode(file_content).decode('utf-8')

            # Procesar string recibido (data URL o base64 crudo)
            if image_string:
                if isinstance(image_string, str) and image_string.startswith('data:image/'):
                    # data:image/png;base64,.... -> obtener la parte base64
                    parts = image_string.split(',', 1)
                    if len(parts) == 2:
                        image_data = parts[1]
                elif isinstance(image_string, str) and (
                        image_string.startswith('/9j/') or image_string.startswith('iVBOR') or all(
                    c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n\r'
                    for c in image_string.strip()[:10])):
                    # base64 crudo detectado (JPEG/PNG o heurística)
                    image_data = image_string
                else:
                    return Response(json.dumps(
                        {"status": "error", "message": "Formato de imagen no válido",
                         "data": None}), status=400, content_type='application/json')

            if not image_data:
                return Response(json.dumps(
                    {"status": "error", "message": "No se encontró imagen válida en la petición",
                     "data": None}), status=400, content_type='application/json')

            user = request.env['res.users'].sudo().browse(int(user_id))
            if not user.exists():
                return Response(json.dumps(
                    {"status": "error", "message": "Usuario no encontrado", "data": None}),
                    status=404, content_type='application/json')

            # Escribir la imagen en image_1920
            user.sudo().write({'image_1920': image_data})

            unique_image_key = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
            avatar_url = f"{base_url}/web/image/res.users/{user.id}/image_1920?{unique_image_key}"

            return Response(json.dumps(
                {"status": "success", "message": "Imagen actualizada correctamente",
                 "data": {"avatar_256": avatar_url}}), status=200, content_type='application/json')

        except ValidationError as e:
            return Response(json.dumps({"status": "error", "message": str(e), "data": None}),
                            status=404, content_type='application/json')
        except Exception as e:
            return Response(json.dumps({"status": "error",
                                        "message": "Ha ocurrido un error inesperado, Intente nuevamente: " + str(
                                            e), "data": None}), status=500,
                            content_type='application/json')

    @http.route('/api/store/deactivate_user', type='json', auth='public',
                methods=['POST'], csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def deactivate_user(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            # data = request.jsonrequest

            if not data.get('user_id'):
                return http.Response(
                    json.dumps(
                        {
                            "status": "error",
                            "message": "El ID de usuario es requerido",
                            "data": None
                        }
                    ),
                    status=404,
                    mimetype='application/json'
                )
            #     raise ValidationError('User ID is required')
            jwt_data = getattr(request, '_jwt_data', {})
            user_id = jwt_data.get('user_id')
            partner_id = jwt_data.get('partner_id')
            if not user_id or not partner_id:
                return http.Response(
                    json.dumps(
                        {
                            "status": "error",
                            "message": "El token proporcionado no es válido",
                            "data": None
                        }
                    ),
                    status=403,
                    mimetype='application/json'
                )

            if int(user_id) != int(data.get('user_id')):
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

            # user = request.env['res.users'].sudo().browse(user_id)
            target_user = request.env['res.users'].sudo().browse(user_id)
            admin_group = request.env.ref('base.group_system')
            if target_user and admin_group in target_user.groups_id:
                return Response(
                    json.dumps(
                        {
                            'status': "error",
                            'message': 'Acceso denegado',
                            'data': None
                        }
                    ),
                    status=401,
                    content_type='application/json'
                )
            # user.sudo().write({'active': False})
            target_user.with_user(1).sudo().write({'active': False})
            return Response(json.dumps(
                {
                    'status': "success",
                    'message': 'Usuario eliminado exitosamente',
                    "data": None
                }
            ),
                status=200,
                content_type='application/json'
            )
        except Exception as e:
            print(e)
            return Response(
                json.dumps(
                    {
                        "status": "error",
                        'message': 'An unexpected error occurred ' + str(e),
                        "data": None
                    }
                ),
                status=500,
                content_type='application/json'
            )
