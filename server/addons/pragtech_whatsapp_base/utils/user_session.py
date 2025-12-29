import logging
from odoo import models, fields, api
from ..templates.meta_api import _logger
import pytz
import datetime

# Configurar Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserSession:
    def __init__(self, env):
        self.env = env

    def current_session(self, number):
        """Obtiene la sesión de un usuario por su número de WhatsApp."""
        session = self.env['whatsapp.chatbot'].sudo().search([('number', '=', number)], limit=1)
        if session:
            try:
                session.write({'last_activity': fields.Datetime.now()})
            except Exception as e:
                _logger.error("Error al actualizar last_activity para el número %s: %s", number, e)
                session.write({'needs_update': True})
        return session

    def create_session(self, number, state, orden=None):
        """Crea/actualiza la sesión con hora local como string"""
        try:
            session = self.env['whatsapp.chatbot'].sudo().search([('number', '=', number)], limit=1)

            if not session:
                # Obtener hora local de Guayaquil
                user_tz = pytz.timezone('America/Guayaquil')
                now_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
                now_local = now_utc.astimezone(user_tz)
                hora_local_str = now_local.strftime('%Y-%m-%d %H:%M:%S')

                session = self.env['whatsapp.chatbot'].sudo().create({
                    'number': number,
                    'state': state,
                    'orden': orden,
                    'last_activity': hora_local_str
                })

            return session
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    def get_session(self, number):
        """Obtiene la sesión de un usuario por su número de WhatsApp."""
        return self.current_session(number)

    def update_session(self, number, state=None, orden=None):
        """Actualiza el estado y/o el carrito de compras de un usuario."""
        session = self.get_session(number)
        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)
        hora_local_str = now_local.strftime('%Y-%m-%d %H:%M:%S')
        if session:
            vals = {
                'last_activity':hora_local_str
            }
            if state is not None:
                vals['state'] = state
            if orden is not None:
                vals['orden'] = orden
            session.sudo().write(vals)
            return True
        return False

    def update_last_message_id(self, number, message_id):
        """Actualiza el ID del último message procesado para un usuario."""
        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)
        hora_local_str = now_local.strftime('%Y-%m-%d %H:%M:%S')
        session = self.get_session(number)
        if session:
            vals = {
                'last_message_id': message_id,
                'last_activity': hora_local_str
            }
            session.sudo().write(vals)
            return True
        return False

