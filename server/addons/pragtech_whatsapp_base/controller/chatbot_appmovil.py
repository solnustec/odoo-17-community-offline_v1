import datetime
import hmac
import hashlib
from odoo import http
from odoo.http import request, Response
import json
import logging
from datetime import datetime
import pytz

from ..utils.user_session import UserSession
from ..templates.conversation_flow import ConversationFlow
from ..templates.meta_api import MetaAPi

_logger = logging.getLogger(__name__)


class SimulateMessageController(http.Controller):

    def _validate_api_token(self):
        """Valida el token API para el simulador."""
        # Obtener token del header
        auth_header = request.httprequest.headers.get('X-API-Token', '')
        if not auth_header:
            auth_header = request.httprequest.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                auth_header = auth_header[7:]

        # Obtener token configurado
        configured_token = request.env['ir.config_parameter'].sudo().get_param(
            'chatbot.simulator.api_token', ''
        )

        # Si no hay token configurado, permitir solo en modo debug
        if not configured_token:
            debug_mode = request.env['ir.config_parameter'].sudo().get_param(
                'chatbot.simulator.allow_without_token', 'False'
            )
            if debug_mode.lower() == 'true':
                _logger.warning("Simulador de chatbot usado sin token de API (modo debug)")
                return True
            return False

        return hmac.compare_digest(auth_header, configured_token)

    @http.route('/simulate/message', type='json', auth='public', csrf=False)
    def simulate_message(self, **kwargs):
        # Validar token de API
        if not self._validate_api_token():
            _logger.warning("Intento de acceso no autorizado al simulador de chatbot")
            return {'status': 'error', 'message': 'Token de API inválido o no proporcionado'}
        try:
            data = json.loads(request.httprequest.data or '{}')
        except Exception:
            return {'status': 'error', 'message': 'JSON inválido'}

        number    = data.get('number')
        privacy_polic = data.get('privacy_polic')
        message   = data.get('message') or ''
        state     = data.get('state')
        file_b64  = data.get('file')
        file_type = (data.get('file_type') or '').lower()
        filename  = data.get('filename')
        mime_type = data.get('mime_type')
        caption   = data.get('caption') or ''

        if not number or (not message and not file_b64):
            return {'status': 'error', 'message': 'Se requiere "number" y al menos "message" o "file".'}

        if privacy_polic is not None and privacy_polic:
            user_session = UserSession(request.env)
            user_session.update_session(number, 'start', orden='')

            chatbot = request.env['whatsapp.chatbot'].sudo().search([('number', '=', number)], limit=1)
            if chatbot:
                chatbot.sudo().write({'privacy_polic': True})

            user_session.update_session(number, state="acepta_politicas")

            return self.continuar_conflujo(number, state, message, file_b64, file_type, filename, mime_type, caption)

        elif privacy_polic is not None and not privacy_polic:
            return {'status': 'error', 'message': 'Debe aceptar la política de privacidad para continuar.'}

        return self.continuar_conflujo(number, state, message, file_b64, file_type, filename, mime_type, caption)

    def continuar_conflujo(self, number, state, message, file_b64, file_type, filename, mime_type, caption):
        user_session = UserSession(request.env)
        session = user_session.get_session(number)
        if not session:
            session = user_session.create_session(number, state, '')
        else:
            user_session.update_session(number, state)

        if state:
            try:
                ConversationFlow.manejar_respuesta_interactiva(number, state)
            except Exception as e:
                _logger.error("Error en ConversationFlow: %s", e)

        if message:
            self._create_message_from_user(number, message)

        if file_b64:
            if file_type and file_type != 'image':
                return {'status': 'error', 'message': 'Solo se admite file_type="image".'}
            self._create_image_message(number, file_b64, filename, mime_type, caption)

            try:
                MetaAPi.enviar_imagen(number, file_b64, caption=caption)
            except Exception as e:
                _logger.error("Error reenviando imagen a WhatsApp: %s", e)

        return {'status': 'success', 'message': 'OK'}

    def _ensure_partner_chatbot(self, number):
        PartnerChat = request.env['res.partner.chatbot'].sudo()
        partner = PartnerChat.search([('chatId', '=', number)], limit=1)
        if not partner:
            partner = PartnerChat.create({'name': number, 'chatId': number})
        return partner

    def _instance_meta(self):
        return request.env['whatsapp.instance'].sudo().search(
            [('status', '!=', 'disable'), ('provider', '=', 'meta'), ('default_instance', '=', True)],
            limit=1
        )

    def _now_str_ec(self):
        tz = pytz.timezone('America/Guayaquil')
        return datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(tz).strftime('%Y-%m-%d %H:%M:%S')

    def _sanitize_b64(self, b64s: str) -> str:
        if not b64s:
            return ''
        # quita cabecera data:...;base64,
        if b64s.startswith('data:'):
            b64s = b64s.split(',', 1)[1]
        # corrige padding
        pad = len(b64s) % 4
        if pad:
            b64s += '=' * (4 - pad)
        return b64s

    @staticmethod
    def _create_message_from_bot(number, text):
        inst = request.env['whatsapp.instance'].sudo().search(
            [('status', '!=', 'disable'), ('provider', '=', 'meta'), ('default_instance', '=', True)],
            limit=1
        )
        partner = request.env['res.partner.chatbot'].sudo().search([('chatId', '=', number)], limit=1)
        if not partner:
            partner = request.env['res.partner.chatbot'].create({'name': number, 'chatId': number})

        Messages = request.env['whatsapp.messages'].sudo()

        # El mensaje es enviado por el bot
        from_me = True

        vals = {
            'partner_id': partner.id,
            'model': 'res.partner.chatbot',
            'res_id': partner.id,
            'whatsapp_instance_id': inst.id if inst else False,
            'whatsapp_message_provider': (inst.provider if inst else 'meta'),

            'chatId': number,
            'author': number,
            'senderName': 'Bot',
            'chatName': number,

            'type': 'text',
            'name': text,
            'message_body': text,
            'state': 'received',
            'fromMe': from_me,
            'time': datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(pytz.timezone('America/Guayaquil')).strftime('%Y-%m-%d %H:%M:%S'),
        }
        return Messages.create(vals)

    def _create_message_from_user(self, number, text):
        inst = self._instance_meta()
        partner = self._ensure_partner_chatbot(number)
        Messages = request.env['whatsapp.messages'].sudo()

        from_me = False

        vals = {
            'partner_id': partner.id,
            'model': 'res.partner.chatbot',
            'res_id': partner.id,
            'whatsapp_instance_id': inst.id if inst else False,
            'whatsapp_message_provider': (inst.provider if inst else 'meta'),

            'chatId': number,
            'author': number,
            'senderName': number,
            'chatName': number,

            'type': 'text',
            'name': text,
            'message_body': text,
            'state': 'received',
            'fromMe': from_me,
            'time': self._now_str_ec(),
        }
        return Messages.create(vals)

    def _create_image_message(self, number, file_b64, filename=None, mime_type=None, caption=''):
        inst    = self._instance_meta()
        partner = self._ensure_partner_chatbot(number)
        Messages = request.env['whatsapp.messages'].sudo()

        body_label = caption or 'Imagen'
        msg = Messages.create({
            'partner_id': partner.id,
            'model': 'res.partner.chatbot',
            'res_id': partner.id,
            'whatsapp_instance_id': inst.id if inst else False,
            'whatsapp_message_provider': (inst.provider if inst else 'meta'),

            'chatId': number,
            'author': number,
            'senderName': number,
            'chatName': number,

            'type': 'image',
            'name': body_label,
            'message_body': body_label,
            'state': 'received',
            'fromMe': False,
            'time': self._now_str_ec(),
        })

        b64 = self._sanitize_b64(file_b64)

        if not mime_type:
            mime_type = 'image/png' if b64[:5] == 'iVBOR' else 'image/jpeg'
        if not filename:
            filename = 'image.png' if mime_type == 'image/png' else 'image.jpg'

        att = request.env['ir.attachment'].sudo().create({
            'name': filename,
            'datas': b64,
            'type': 'binary',
            'res_model': 'whatsapp.messages',
            'res_id': msg.id,
            'mimetype': mime_type,
        })

        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        msg.sudo().write({
            'attachment_id': att.id,
            'image_url': base_url + (att.image_src or att.local_url),
        })
        return msg






