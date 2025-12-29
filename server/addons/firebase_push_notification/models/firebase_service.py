from firebase_admin import initialize_app, _apps, messaging
from firebase_admin import credentials
import json
from firebase_admin.exceptions import FirebaseError, InvalidArgumentError
from odoo import fields, api, models, _, exceptions
from odoo.exceptions import UserError


class FirebaseService(models.AbstractModel):
    _name = 'firebase.service'
    _description = 'Firebase Connection Helper'

    @api.model
    def get_firebase_credential(self):
        raw_json = self.env['ir.config_parameter'].sudo().get_param(
            'firebase.credentials_json')
        if not raw_json:
            raise UserError(
                _("Las credenciales de Firebase no están configuradas (firebase.credentials_json)."))

        try:
            service_info = json.loads(raw_json)
        except json.JSONDecodeError:
            raise UserError(
                _("El contenido del parámetro firebase.credentials_json no es JSON válido."))

        return credentials.Certificate(service_info)

    @api.model
    def get_firebase_app(self):
        if not _apps:
            cred = self.get_firebase_credential()
            initialize_app(cred)

        return _apps

    @api.model
    def test_connection(self):
        """Método reutilizable para probar la conexión con Firebase"""
        try:
            self.get_firebase_app()
            return True
        except Exception as e:
            raise UserError(_("Error al conectar con Firebase: %s") % str(e))

    @api.model
    def _send_single_push_notification(self, user_id, title,
                                       body, data=None):
        """ Enviar notificación a un solo dispositivo """
        self.get_firebase_app()
        device = self.env['push.device'].find_by_user(user_id)


        if device:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                token=device.register_id,
                data=data or {},
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='default',
                        channel_id='default',
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default',
                        )
                    )
                ),
            )

            response = messaging.send(message)
            return {
                'success': True,
                'message_id': response
            }
        return {
            'success': False,
            'message_id': None
        }



    @api.model
    def send_push_notification(self, registration_token, title, body,
                               data=None):
        """ Metodo reutilizable para enviar notificaciones masivas desde el cron a Firebase
            try:
                # En otro modelo, collamando a este metodo desde otro modelo:
                request.env['firebase.service'].send_push_notification(
                    registration_token="dpwk4dznS8vBY9mIGXxAUb:APA91bFJjnq57hs8WQOSBfBKiUFMkW2Xv_MdRvAhc0FL8buyOaD7gOlkgEN_B4ypxhhbwpKHH5ZEq2pGORBjkXCAUKmc3eeajqtLmMyjlo7ZAUFm_pvaE7w",
                    title="Banners",
                    body="asdasd"
                )
            except Exception as e:
                print(e)

        """

        self.get_firebase_app()

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=registration_token,
            data=data or {},
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    sound='default',
                    channel_id='default',
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                    )
                )
            ),
        )

        # messaging.send(message)

        try:
            response = messaging.send(message)
            return {
                'success': True,
                'message_id': response
            }
        except messaging.UnregisteredError:
            # Token inválido, eliminar el dispositivo
            device = self.env['push.device'].sudo().search([
                ('register_id', '=', registration_token)
            ], limit=1)
            if device:
                device.deactivate_invalid_token()

            return {
                'success': False,
                'error': 'Token no válido. Dispositivo eliminado.'
            }
        except (FirebaseError, InvalidArgumentError) as e:
            return {
                'success': False,
                'error': str(e)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error inesperado: {str(e)}'
            }



        # return {
        #     'success': True,
        #     'message_id': response
        # }

        # except messaging.UnregisteredError:
        #     # Token inválido, lo desactivamos
        #     self.env['push.notification'].sudo().search([
        #         ('register_id', '=', registration_token)
        #     ]).write({'active': False})
        #
        #     return {
        #         'success': False,
        #         'error': 'Token no válido. Se ha desactivado.'
        #     }
        # except (FirebaseError, InvalidArgumentError) as e:
        #     return {
        #         'success': False,
        #         'error': str(e)
        #     }

    def test_firebase_connection(self, device_ids):
        if not device_ids:
            raise exceptions.UserError(
                _("No se seleccionó ningún dispositivo. Por favor, seleccione al menos un dispositivo."))

            # Tomar solo el primer dispositivo
        device = self.env['push.device'].browse(device_ids[0])
        if not device.exists():
            raise exceptions.UserError(
                _("El dispositivo seleccionado no existe."))

        if not device.register_id:
            raise exceptions.UserError(
                _("El dispositivo seleccionado no tiene un ID de registro válido."))

        try:
            # Enviar notificación push al primer dispositivo
            self.send_push_notification(device.register_id, "Testing",
                                        "Firebase conectado")
        except Exception as e:
            raise exceptions.UserError(
                _("Error al enviar la notificación push: %s") % str(e))

        # Retornar acción de cliente para mostrar notificación en la interfaz
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("Conexión con Firebase exitosa 🎉"),
                'sticky': False,
                'fadeout': 'slow',
            }
        }

    @api.model
    def send_push_notification_to_user(self, user_id, title, body, data=None):
        """ Enviar notificaciones a un usuario en individual """
        device = self.env['push.device'].find_by_user(user_id)
        self.send_push_notification(device.register_id, title, body, data)
