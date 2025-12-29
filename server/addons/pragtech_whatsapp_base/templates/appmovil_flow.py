from .meta_api import MetaAPi
from ..controller.chatbot_appmovil import SimulateMessageController
from ..utils.user_session import UserSession
from odoo.http import request


class AsesorMovilFlow:

    @staticmethod
    def procesar_cotizacion_movil(numero):
        """Inicia el proceso de cotización de una receta médica."""
        user_session = UserSession(request.env)
        user_session.update_session(numero, 'start', orden='')
        UserSession(request.env).update_session(numero, state="cotizar-receta")

        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('hello_asesor_movil')
        MetaAPi.enviar_mensaje_texto(numero, mensaje)

        return

