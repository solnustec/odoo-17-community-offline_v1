from .meta_api import MetaAPi
from ..utils.user_session import UserSession
from odoo.http import request


class WorkPlace_Flow:

    @staticmethod
    def plaza_trabajo(number):
        # Obtener mensaje personalizado para trabajo
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('workplace_hello')


        MetaAPi.enviar_mensaje_texto(number, mensaje)
        UserSession(request.env).update_session(number, state="manejar_salida")
        MetaAPi.enviar_mensaje_con_botones_salida(number)
