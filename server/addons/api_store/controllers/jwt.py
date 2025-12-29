import jwt
from odoo import exceptions, http
from odoo.exceptions import AccessDenied
from odoo.http import request, Response

import json
import functools


def verify_jwt(token):
    try:
        JWT_SECRET_KEY = request.env['ir.config_parameter'].sudo().get_param(
            'jwt_secret_key')
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        # Extraer el user_id del payload
        user_id = payload.get('user_id')
        partner_id = payload.get('partner_id')
        if not user_id:
            raise exceptions.AccessDenied(
                message='Token inválido: usuario no encontrado')

        # Buscar al usuario
        user = request.env['res.users'].sudo().browse(user_id)
        partner = request.env['res.partner'].sudo().browse(partner_id)
        if not user.exists():
            raise exceptions.AccessDenied(message='Usuario no encontrado')

        return user.id, partner.id

    except jwt.ExpiredSignatureError:
        raise exceptions.AccessDenied(message='Token expirado')

    except jwt.InvalidTokenError:
        raise exceptions.AccessDenied(message='Token inválido')

    except Exception as e:
        raise exceptions.AccessDenied(message=str(e))


def validate_jwt(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = http.request.httprequest.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise AccessDenied(
                message='Token no proporcionado o formato inválido')

        token = auth_header.split(' ')[1]
        user, partner = verify_jwt(token)

        # Almacenar user y partner en un atributo personalizado de request
        request._jwt_data = {
            'user_id': user,
            'partner_id': partner
        }

        return func(*args, **kwargs)

    return wrapper


# TODO: por implementar
def validate_jwt_data(jwt_data, userid, user_id_key='user_id',
                      partner_id_key='partner_id'):
    """
    Valida user_id y partner_id desde jwt_data y verifica que user_id coincida con userid.

    :param jwt_data: Diccionario con los datos del token JWT (por ejemplo, request._jwt_data)
    :param userid: ID del usuario proporcionado en la solicitud (por ejemplo, desde la URL)
    :param user_id_key: Clave en jwt_data para user_id (por defecto: 'user_id')
    :param partner_id_key: Clave en jwt_data para partner_id (por defecto: 'partner_id')
    :return: Tupla (user_id, partner_id) si la validación es exitosa
    :raises: http.Response con error JSON si la validación falla
    """
    user_id = jwt_data.get(user_id_key)
    partner_id = jwt_data.get(partner_id_key)

    if not user_id or not partner_id:
        return http.Response(
            json.dumps(
                {
                    "status": "error",
                    "message": "El token proporcionado no es valido"
                }
            ),
            status=403,
            mimetype='application/json'
        )

    if int(user_id) != int(userid):
        return http.Response(
            json.dumps(
                {
                    "status": "error",
                    "message": "El token proporcionado no pertenece al usuario"
                }
            ),
            status=403,
            mimetype='application/json'
        )

    return user_id, partner_id
