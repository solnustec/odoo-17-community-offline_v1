import json
import logging
import time

import requests

from ..controllers.jwt import jwt
from odoo import http, _
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class OAuthApiController(http.Controller):
    """Controller for API OAuth authentication for mobile apps"""

    @http.route('/api/store/oauth/providers', type='http', auth='none',
                csrf=False)
    def list_providers(self):
        """Return list of available OAuth providers"""
        providers = request.env['auth.oauth.provider'].sudo().search_read(
            [('enabled', '=', True)],
            ['id', 'name', 'auth_endpoint', 'scope', 'client_id', 'css_class']
        )
        if providers:
            return Response(json.dumps({
                'status': 'success',
                'message': 'Lista de proveedores de OAuth obtenida exitosamente',
                'data': providers
            }), status=200, content_type='application/json')
        return Response(json.dumps({
            'status': 'error',
            'message': 'No se encontraron proveedores de OAuth disponibles',
            'data': None
        }))

    @http.route('/api/store/oauth/authenticate', type='http', auth='none',
                csrf=False, methods=['POST'])
    def authenticate(self, **kw):
        """
        API endpoint for authenticating with an OAuth provider token
        Receives a provider ID and token, validates with the provider,
        and returns session information
        """
        data = json.loads(request.httprequest.data.decode('utf-8'))
        provider_id = data.get('provider_id')
        access_token = data.get('access_token')
        id_token = data.get('id_token')  # For OpenID Connect like Google

        if not provider_id or not (access_token or id_token):
            return Response(json.dumps({
                'status': 'error',
                'message': 'Proveedor de OAuth y token requeridos',
                'data': None
            }), status=400, content_type='application/json')

        try:
            # Get provider
            provider = request.env['auth.oauth.provider'].sudo().browse(
                int(provider_id))
            if not provider.exists() or not provider.enabled:
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'Proveedor de OAuth no encontrado o deshabilitado',
                    'data': None
                }), status=400, content_type='application/json')

            # For Google, we prefer id_token if available
            token_to_use = id_token if id_token and 'google' in provider.name.lower() else access_token

            # Validate the token
            validation_endpoint = provider.validation_endpoint

            if 'google' in provider.name.lower() and id_token:
                # For Google, we use the tokeninfo endpoint with id_token
                validation_endpoint = "https://oauth2.googleapis.com/tokeninfo"
                validation_data = {'id_token': id_token}
            else:
                # For other providers, use access_token
                validation_data = {'access_token': access_token}

            # Call validation endpoint
            try:
                _logger.info("Validating OAuth token with provider: %s",
                             provider.name)
                resp = requests.get(validation_endpoint,
                                    params=validation_data, timeout=10)

                if resp.status_code != 200:
                    _logger.error("OAuth validation error: %s %s",
                                  resp.status_code, resp.text)
                    return Response(json.dumps({
                        'status': 'error',
                        'message': 'Error al validar el token',
                        'data': None
                    }), status=400, content_type='application/json')

                validation_response = resp.json()

                # Ensure token is valid for our app
                if 'google' in provider.name.lower() and id_token:
                    # Check audience for Google
                    audience = validation_response.get('aud')
                    if audience != provider.client_id:
                        return Response(json.dumps({
                            'status': 'error',
                            'message': 'Invalid audience in token',
                            'data': None
                        }), status=400, content_type='application/json')
                    if not validation_response.get('email_verified', False):
                        return Response(json.dumps({
                            'status': 'error',
                            'message': 'Correo electrónico no verificado',
                            'data': None
                        }), status=400, content_type='application/json')
                    exp = validation_response.get('exp')
                    if exp and int(exp) < int(time.time()):
                        return Response(json.dumps({
                            'status': 'error',
                            'message': 'Token expirado',
                            'data': None
                        }), status=400, content_type='application/json')

                # For Google ID tokens
                oauth_uid = validation_response.get(
                    'sub') or validation_response.get('user_id')
                if not oauth_uid:
                    return Response(json.dumps({
                        'status': 'error',
                        'message': 'Invalid user ID in token',
                        'data': None
                    }), status=400, content_type='application/json')
                # Extract email and other user info
                email = validation_response.get('email')
                name = validation_response.get('name', email)

                user = request.env['res.users'].sudo().search([
                    ('oauth_provider_id', '=', provider.id),
                    ('oauth_uid', '=', oauth_uid),
                ])

                if not user:
                    company_id = request.env['res.company'].browse(1)
                    partner = request.env['res.partner'].sudo().search(
                        [('email', '=', email)], limit=1)
                    if not partner.exists():
                        partner = request.env[
                            'res.partner'].sudo().with_context(
                            allowed_company_ids=[company_id.id]
                        ).create({
                            'name': name,
                            'email': email,
                            'country_id': 63,
                            'company_id': company_id.id
                        })
                    user = request.env['res.users'].sudo().with_context(
                        allowed_company_ids=[company_id.id],
                        mail_notrack=True).create({
                        'name': name,
                        'login': email,
                        'email': email,
                        'groups_id': [(6, 0, [10])],
                        'oauth_provider_id': provider.id,
                        'oauth_uid': oauth_uid,
                        'oauth_access_token': access_token,
                        'company_id': company_id.id,
                        'partner_id': partner.id,
                        'company_ids': [(6, 0, [company_id.id])]
                    })

                if access_token:
                    user.sudo().write({'oauth_access_token': access_token})
                payload = {
                    'user_id': user.id,
                    "partner_id": user.partner_id.id
                }
                JWT_SECRET_KEY = request.env[
                    'ir.config_parameter'].sudo().get_param(
                    'jwt_secret_key')
                token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')

                return Response(json.dumps({
                    'status': 'success',
                    'message': 'Autenticación exitosa',
                    'data': {
                        'user_id': user.id,
                        'partner_id': user.partner_id.id,
                        'name': user.name,
                        'email': user.email,
                        'token': token,
                        'access_token': access_token
                    }
                }), status=200, content_type='application/json')

            except requests.exceptions.RequestException as e:
                _logger.exception("Error validating OAuth token")
                return Response(json.dumps({
                    'status': 'error',
                    'message': f'Failed to validate token: {str(e)}',
                    'data': None
                }), status=400, content_type='application/json')

        except Exception as e:
            _logger.exception("OAuth API authentication error")
            return Response(json.dumps({
                'status': 'error',
                'message': f'Failed to authenticate: {str(e)}',
                'data': None
            }), status=400, content_type='application/json')

    @http.route('/api/store/oauth/revoke', type='http', auth='public', csrf=False)
    def revoke_token(self):
        """Revoke OAuth token and invalidate session"""
        user = request.env.user

        # Revoke the token if this is an OAuth user
        if user.oauth_provider_id and user.oauth_access_token:
            provider = user.oauth_provider_id

            # For Google, attempt to revoke
            if 'google' in provider.name.lower():
                try:
                    # Google token revocation endpoint
                    requests.post(
                        'https://oauth2.googleapis.com/revoke',
                        params={'token': user.oauth_access_token},
                        headers={
                            'content-type': 'application/x-www-form-urlencoded'},
                        timeout=10
                    )
                except Exception as e:
                    _logger.warning("Failed to revoke Google token: %s",
                                    str(e))

            # Clear the token in Odoo
            user.sudo().write({'oauth_access_token': False})

        # Clear session
        request.session.logout()

        return {'success': True}


    #
    # def authenticate(self, **kw):
    #     """
    #     API endpoint for authenticating with an OAuth provider token for a mobile app.
    #     Receives a provider ID, access_token, and id_token, validates with the provider,
    #     and returns a JWT for authentication.
    #     """
    #     # Parse request data
    #     try:
    #         data = json.loads(request.httprequest.data.decode('utf-8'))
    #     except json.JSONDecodeError:
    #         return Response(json.dumps({
    #             'status': 'error',
    #             'message': 'Formato JSON inválido',
    #             'data': None
    #         }), status=400, content_type='application/json')
    #
    #     provider_id = data.get('provider_id')
    #     access_token = data.get('access_token')
    #     id_token = data.get('id_token')  # For Google OpenID Connect
    #
    #     # Validate input
    #     if not provider_id or not (access_token or id_token):
    #         return Response(json.dumps({
    #             'status': 'error',
    #             'message': 'Proveedor de OAuth y token requeridos',
    #             'data': None
    #         }), status=400, content_type='application/json')
    #
    #     try:
    #         # Get provider
    #         provider = request.env['auth.oauth.provider'].sudo().browse(
    #             int(provider_id))
    #         if not provider.exists() or not provider.enabled:
    #             return Response(json.dumps({
    #                 'status': 'error',
    #                 'message': 'Proveedor de OAuth no encontrado o deshabilitado',
    #                 'data': None
    #             }), status=400, content_type='application/json')
    #
    #         # For Google, prefer id_token
    #         token_to_use = id_token if id_token and 'google' in provider.name.lower() else access_token
    #
    #         # Validate the token
    #         validation_endpoint = provider.validation_endpoint
    #         validation_data = {}
    #
    #         if 'google' in provider.name.lower() and id_token:
    #             validation_endpoint = "https://oauth2.googleapis.com/tokeninfo"
    #             validation_data = {'id_token': id_token}
    #         else:
    #             validation_data = {'access_token': access_token}
    #
    #         # Call validation endpoint
    #         _logger.info("Validando token OAuth con proveedor: %s",
    #                      provider.name)
    #         try:
    #             resp = requests.get(validation_endpoint,
    #                                 params=validation_data, timeout=10)
    #             if resp.status_code != 200:
    #                 _logger.error("Error de validación OAuth: %s %s",
    #                               resp.status_code, resp.text)
    #                 return Response(json.dumps({
    #                     'status': 'error',
    #                     'message': 'Error al validar el token',
    #                     'data': None
    #                 }), status=400, content_type='application/json')
    #
    #             validation_response = resp.json()
    #
    #             # Validate Google-specific fields
    #             if 'google' in provider.name.lower() and id_token:
    #                 # Check audience
    #                 audience = validation_response.get('aud')
    #                 if audience != provider.client_id:
    #                     return Response(json.dumps({
    #                         'status': 'error',
    #                         'message': 'Audiencia inválida en el token',
    #                         'data': None
    #                     }), status=400, content_type='application/json')
    #
    #                 # Check email verification
    #                 if not validation_response.get('email_verified', False):
    #                     return Response(json.dumps({
    #                         'status': 'error',
    #                         'message': 'Correo electrónico no verificado',
    #                         'data': None
    #                     }), status=400, content_type='application/json')
    #
    #                 # Check token expiration
    #                 exp = validation_response.get('exp')
    #                 if exp and int(exp) < int(time.time()):
    #                     return Response(json.dumps({
    #                         'status': 'error',
    #                         'message': 'Token expirado',
    #                         'data': None
    #                     }), status=400, content_type='application/json')
    #
    #             # Extract user info
    #             oauth_uid = validation_response.get(
    #                 'sub') or validation_response.get('user_id')
    #             if not oauth_uid:
    #                 return Response(json.dumps({
    #                     'status': 'error',
    #                     'message': 'ID de usuario inválido en el token',
    #                     'data': None
    #                 }), status=400, content_type='application/json')
    #
    #             email = validation_response.get('email')
    #             name = validation_response.get('name', email or oauth_uid)
    #
    #             if not email:
    #                 return Response(json.dumps({
    #                     'status': 'error',
    #                     'message': 'Correo electrónico no proporcionado por el proveedor',
    #                     'data': None
    #                 }), status=400, content_type='application/json')
    #
    #             # Search or create user
    #             user = request.env['res.users'].sudo().search([
    #                 ('oauth_provider_id', '=', provider.id),
    #                 ('oauth_uid', '=', oauth_uid)
    #             ], limit=1)
    #
    #             company_id = request.env['res.company'].browse(1)
    #             if not company_id.exists():
    #                 return Response(json.dumps({
    #                     'status': 'error',
    #                     'message': 'Compañía no encontrada',
    #                     'data': None
    #                 }), status=400, content_type='application/json')
    #
    #             if not user:
    #                 # Search or create partner
    #                 partner = request.env['res.partner'].sudo().search(
    #                     [('email', '=', email)], limit=1)
    #                 if not partner:
    #                     partner = request.env[
    #                         'res.partner'].sudo().with_context(
    #                         allowed_company_ids=[company_id.id]
    #                     ).create({
    #                         'name': name,
    #                         'email': email,
    #                         'country_id': 63,
    #                         'company_id': company_id.id
    #                     })
    #
    #                 # Create user
    #                 user = request.env['res.users'].sudo().with_context(
    #                     allowed_company_ids=[company_id.id],
    #                     mail_notrack=True
    #                 ).create({
    #                     'name': name,
    #                     'login': email,
    #                     'email': email,
    #                     'groups_id': [(6, 0, [10])],
    #                     'oauth_provider_id': provider.id,
    #                     'oauth_uid': oauth_uid,
    #                     'oauth_access_token': access_token,
    #                     'company_id': company_id.id,
    #                     'partner_id': partner.id,
    #                     'company_ids': [(6, 0, [company_id.id])]
    #                 })
    #
    #             # Update access token if provided
    #             if access_token:
    #                 user.sudo().write({'oauth_access_token': access_token})
    #
    #             # Generate JWT
    #             JWT_SECRET_KEY = request.env[
    #                 'ir.config_parameter'].sudo().get_param('jwt_secret_key')
    #             if not JWT_SECRET_KEY:
    #                 return Response(json.dumps({
    #                     'status': 'error',
    #                     'message': 'Clave secreta JWT no configurada',
    #                     'data': None
    #                 }), status=500, content_type='application/json')
    #
    #             payload = {
    #                 'user_id': user.id,
    #                 'partner_id': user.partner_id.id,
    #                 'exp': int(time.time()) + 3600  # Token expira en 1 hora
    #             }
    #             token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')
    #
    #             return Response(json.dumps({
    #                 'status': 'success',
    #                 'message': 'Autenticación exitosa',
    #                 'data': {
    #                     'user_id': user.id,
    #                     'partner_id': user.partner_id.id,
    #                     'name': user.name,
    #                     'email': user.email,
    #                     'token': token,
    #                     'access_token': access_token
    #                 }
    #             }), status=200, content_type='application/json')
    #
    #         except requests.exceptions.RequestException as e:
    #             _logger.exception("Error validando token OAuth")
    #             return Response(json.dumps({
    #                 'status': 'error',
    #                 'message': f'Error al validar el token: {str(e)}',
    #                 'data': None
    #             }), status=400, content_type='application/json')
    #
    #     except Exception as e:
    #         _logger.exception("Error en autenticación OAuth API")
    #         return Response(json.dumps({
    #             'status': 'error',
    #             'message': f'Error al autenticar: {str(e)}',
    #             'data': None
    #         }), status=500, content_type='application/json')