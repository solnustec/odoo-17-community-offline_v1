from .dutyPharmacy_flow import DutyPharmacy
from .getBranch import GetBranch
from .meta_api import MetaAPi
from ..utils.user_session import UserSession
from odoo.http import request


class ProductAsesorFlow:
    @staticmethod
    def product_found(numero):
        """Inicia el proceso de cotización de una receta médica."""
        user_session = UserSession(request.env)
        user_session.update_session(numero, 'start', orden='')
        UserSession(request.env).update_session(numero, state="cotizar-receta")

        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('product_found')
        mensaje2 = request.env['whatsapp_messages_user'].sudo().get_message('hello_asesor_product')

        MetaAPi.enviar_mensaje_texto(numero, mensaje)
        MetaAPi.enviar_mensaje_texto(numero, mensaje2)
