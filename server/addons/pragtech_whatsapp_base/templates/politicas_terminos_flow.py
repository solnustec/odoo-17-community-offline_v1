from .meta_api import MetaAPi
from ..utils.user_session import UserSession
from odoo.http import request


class PoliticasTerminosFlow:

    @staticmethod
    def politicas(number, mensaje:None):
        mensaje_hello = request.env['whatsapp_messages_user'].sudo().get_message('message_hello')
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('hello_politicas')

        MetaAPi.enviar_mensaje_texto(number, mensaje_hello)
        MetaAPi.enviar_mensaje_texto(number, mensaje)
        UserSession(request.env).update_session(number, state="manejar_politicas")
        MetaAPi.confirmar_politicas(number)
