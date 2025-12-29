from .api_security import validate_api_static_token
from odoo.exceptions import AccessDenied
from odoo import http
from odoo.http import request, Response
import json
import random
import string


class PasswordResetController(http.Controller):

    @http.route('/api/store/password_reset', type='http', auth='public',
                methods=['POST'], csrf=False, cors="*")
    @validate_api_static_token
    def reset_password(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        email = data.get('email')

        if not email:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'El correo es requerido',
                        'data': None
                    }
                ),
                status=400,
                content_type='application/json'
            )

        user = request.env['res.users'].sudo().search([('login', '=', email)],
                                                      limit=1)
        admin_group = request.env.ref('base.group_system')
        if user and admin_group in user.groups_id:
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
        if not user:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'Usuario no encontrado',
                        'data': None
                    }
                ),
                status=404,
                content_type='application/json'
            )

        # new_password = ''.join(
        #     random.choices(string.ascii_letters + string.digits, k=8))
        new_password = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=8))
        user.sudo().write({'password': new_password})
        # user.sudo().set_password(new_password)

        try:
            request.env['user.notification'].sudo().create({
                'name': 'Cambio de contraseña',
                'user_id': user.id,
                'message': f"Tu contraseña ha sido cambiada exitosamente. ",
            })
        except Exception as e:
            pass

        # Enviar correo de recuperación de contraseña
        # template = request.env.ref('auth_signup.mail_template_user_signup_password')
        template = request.env.ref(
            'auth_signup.mail_template_user_signup_password_app')
        # email_values = {
        #     'email_to': email,
        #     'body_html': template.sudo().body_html.replace('${password}', new_password)
        # }
        # template.sudo().send_mail(user.id, force_send=True, email_values=email_values)
        # template = request.env.ref(
        #     'auth_signup.mail_template_user_signup_password_app')
        if template:
            email_values = {
                'email_to': email,
                'body_html': template.sudo().body_html.replace('password', new_password)
            }
            template.sudo().send_mail(user.id, force_send=True, email_values=email_values)
            # template.sudo().body_html = template.sudo().body_html.replace(
            #     '${password}',
            #     new_password)
            # template.sudo().send_mail(user.id, force_send=True,
            #                           email_values={'email_to': email})

            return Response(
                json.dumps(
                    {
                        'status': 'success',
                        'message': 'Contraseña cambiada exitosamente',
                        'data': None
                    }
                ),
                status=200,
                content_type='application/json'
            )
        else:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'Error interno del servidor', 'data': None
                    }
                ),
                status=500,
                content_type='application/json'
            )

    @http.route('/api/store/change_password', type='http', auth='public',
                methods=['POST'], csrf=False, cors="*")
    @validate_api_static_token
    def change_password(self, **kwargs):
        try:
            # Parsear datos del request
            data = json.loads(request.httprequest.data.decode('utf-8'))
            email = data.get('email')
            old_password = data.get('old_password')
            new_password = data.get('new_password')

            # Validar datos requeridos
            if not email or not old_password or not new_password:
                return Response(
                    json.dumps(
                        {
                            'status': 'error',
                            'message': 'Correo, Contraseña anterior, y nueva contraseña son requeridos',
                            'data': None
                        }
                    ),
                    status=400,
                    content_type='application/json'
                )
            user_agent_env = request.httprequest.environ.copy()
            # Validar si el usuario existe y esta ctivo
            user = request.env['res.users'].sudo().search([
                ('login', '=', email),
                ('active', '=', True)
            ], limit=1)
            if not user:
                return Response(
                    json.dumps(
                        {
                            'status': 'error',
                            'message': 'Cuenta no encontrada, intente de nuevo',
                            'data': None
                        }),
                    status=404,
                    content_type='application/json'
                )

            # Validar contraseña anterior iniciando sesion
            try:
                request.env['res.users'].sudo()._login(
                    request.env.cr.dbname,
                    user.login,
                    old_password,
                    user_agent_env
                )
            except AccessDenied:
                return Response(
                    json.dumps({
                        'status': 'error',
                        'message': 'Contraseña anterior incorrecta',
                        'data': None
                    }),
                    status=401,
                    content_type='application/json'
                )

            # Actualizar la contraseña
            user.sudo().write({'password': new_password})
            # Respuesta de éxito
            return Response(
                json.dumps(
                    {
                        'status': 'success',
                        'message': 'Contraseña actualizada, inicie sesión nuevamente',
                        'data': None
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
                        'message': 'Hubo un error inesperado' + str(e),
                        'data': None
                    }
                ),
                status=500,
                content_type='application/json'
            )
