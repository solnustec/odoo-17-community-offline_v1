import logging
import json
import base64
import phonenumbers
import datetime
import time
import hmac
import hashlib
import werkzeug.datastructures
import werkzeug.exceptions
import werkzeug.local
import werkzeug.routing
import werkzeug.security
import werkzeug.wrappers
import werkzeug.wsgi
import pytz
import re
import requests

import requests
import re
from urllib.parse import urlparse, parse_qs

from ..templates.appmovil_flow import AsesorMovilFlow
from ..templates.branch_flow import BranchFlow
from ..templates.buyProduct_flow import BuyProductFlow
from ..templates.conversation_flow import ConversationFlow
from ..templates.dutyPharmacy_flow import DutyPharmacy
from ..templates.invoice_flow import InvoiceFlow
from ..templates.meta_api import MetaAPi
from odoo.http import Response, request
from ..templates.politicas_terminos_flow import PoliticasTerminosFlow
from ..utils.user_session import UserSession
from odoo import http

_logger = logging.getLogger(__name__)


def _response_inherit(self, result=None, error=None):
    response = ''
    if error is not None:
        response = error
        status = error.pop('http_status', 200)
    if result is not None:
        response = result

    return request.make_json_response(response)


def make_json_response_inherit(self, data, headers=None, cookies=None,
                               status=200):
    """ Helper for JSON responses, it json-serializes ``data`` and
    sets the Content-Type header accordingly if none is provided.

    :param data: the data that will be json-serialized into the response body
    :param int status: http status code
    :param List[(str, str)] headers: HTTP headers to set on the response
    :param collections.abc.Mapping cookies: cookies to set on the client
    :rtype: :class:`~odoo.http.Response`
    """
    data = ''

    headers = werkzeug.datastructures.Headers(headers)
    headers['Content-Length'] = len(data)
    if 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json; charset=utf-8'

    return self.make_response(data, headers.to_wsgi_list(), cookies, status)


def make_response(self, data, headers=None, cookies=None, status=200):
    """ Helper for non-HTML responses, or HTML responses with custom
    response headers or cookies.

    While handlers can just return the HTML markup of a page they want to
    send as a string if non-HTML data is returned they need to create a
    complete response object, or the returned data will not be correctly
    interpreted by the clients.

    :param str data: response body
    :param int status: http status code
    :param headers: HTTP headers to set on the response
    :type headers: ``[(name, value)]``
    :param collections.abc.Mapping cookies: cookies to set on the client
    :returns: a response object.
    :rtype: :class:`~odoo.http.Response`
    """
    response = Response(data, status=status, headers=headers)
    if cookies:
        for k, v in cookies.items():
            response.set_cookie(k, v)
    return response


def _json_response_inherit(self, result=None, error=None):
    response = ''
    if error is not None:
        response = error
    if result is not None:
        response = result
    mime = 'application/json'
    body = ''
    return Response(
        body, status=error and error.pop('http_status', 200) or 200,
        headers=[('Content-Type', mime), ('Content-Length', len(body))]
    )


class WhatsappBase(http.Controller):

    def create_res_partner_against_whatsapp(self, chat_id, sender_name,
                                            country_code, mobile):
        # Creation of partner
        partner_dict = {}
        res_country_id = request.env['res.country'].sudo().search(
            [('phone_code', '=', country_code)], limit=1)
        if res_country_id:
            partner_dict['country_id'] = res_country_id.id
        partner_dict.update(
            {'name': sender_name, 'mobile': str(country_code) + str(mobile),
             'chatId': chat_id})
        res_partner_id = request.env['res.partner.chatbot'].sudo().create(partner_dict)
        return res_partner_id.id

    def create_message_dict(self, whatsapp_message_dict, message_dict):
        message_content = whatsapp_message_dict.get('body')
        if isinstance(message_content, dict):
            message_content = message_content.get('body', message_content.get('text', ''))
        elif isinstance(message_content, str):
            try:
                content_dict = json.loads(message_content)
                if isinstance(content_dict, dict):
                    message_content = content_dict.get('body', content_dict.get('text', message_content))
            except:
                pass

        message_dict.update({
            'name': message_content,
            'message_body': message_content,
            'message_id': whatsapp_message_dict.get('id'),
            'to': whatsapp_message_dict.get('chatName') if whatsapp_message_dict.get('fromMe') else 'To Me',
            'chatId': whatsapp_message_dict.get('chatId'),
            'type': whatsapp_message_dict.get('type'),
            'senderName': whatsapp_message_dict.get('senderName'),
            'chatName': whatsapp_message_dict.get('chatName'),
            'author': whatsapp_message_dict.get('author'),
            'time': self.convert_epoch_to_unix_timestamp(int(whatsapp_message_dict.get('time'))),
            'state': 'received',
        })

        if whatsapp_message_dict.get('type') == 'image':
            image_data = base64.b64encode(requests.get(
                whatsapp_message_dict.get('body').strip()).content).replace(
                b'\n', b'')
            message_dict.update({
                'message_body': whatsapp_message_dict.get('caption', ''),
            })
            image_data = base64.b64encode(requests.get(
                whatsapp_message_dict.get('body').strip()).content).replace(
                b'\n', b'')
            message_dict.update(
                {'message_body': whatsapp_message_dict.get('caption')})

        if whatsapp_message_dict.get(
                'type') == 'chat' or whatsapp_message_dict.get(
            'type') == 'video' or whatsapp_message_dict.get(
            'type') == 'audio':
            message_dict.update(
                {'message_body': whatsapp_message_dict.get('body')})

        if whatsapp_message_dict['type'] == 'document':
            message_dict.update(
                {'message_body': whatsapp_message_dict.get('caption')})

        return message_dict

    def convert_epoch_to_unix_timestamp(self, msg_time):
        # convert webhook whatsapp time to local timezone
        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)

        formatted_time = time.strftime('%Y-%m-%d %H:%M:%S',
                                       time.localtime(msg_time))
        date_time_obj = datetime.datetime.strptime(formatted_time,
                                                   '%Y-%m-%d %H:%M:%S')
        return date_time_obj

    def sanitized_country_mobile_from_chat_id(self, whatsapp_id):
        if '@' in whatsapp_id:
            mobile_country_code = phonenumbers.parse(
                '+' + (whatsapp_id.split('@'))[0], None)
        else:
            mobile_country_code = phonenumbers.parse('+' + whatsapp_id, None)
        country_code = mobile_country_code.country_code
        res_country_id = request.env['res.country'].sudo().search(
            [('phone_code', '=', country_code)], limit=1)
        return country_code, mobile_country_code.national_number

    def sanitized_country_mobile_from_meta_chat_id(self, whatsapp_id):
        mobile_country_code = phonenumbers.parse('+' + whatsapp_id, None)
        country_code = mobile_country_code.country_code
        number = '+' + str(country_code)
        return number, mobile_country_code.national_number

    def create_res_partner_against_meta_whatsapp(self, number, sender_name,
                                                 country_code, mobile):
        # Creation of partner
        partner_dict = {}
        res_country_id = request.env['res.country'].sudo().search(
            [('phone_code', '=', country_code)], limit=1)
        if res_country_id:
            partner_dict['country_id'] = res_country_id.id
        partner_dict.update(
            {'name': sender_name, 'mobile': str(country_code) + str(mobile),
             'chatId': str(number)})
        res_partner_id = request.env['res.partner.chatbot'].sudo().create(partner_dict)
        return res_partner_id

    def meta_create_message_dict(self, whatsapp_message_dict, message_dict, data, whatsapp_instance_id):
        whatsapp_message_obj = request.env['whatsapp.messages']
        whatsapp_messages_id = whatsapp_message_obj.sudo().search(
            [('chatId', '=', whatsapp_message_dict.get('from')), ], limit=1)

        message_text = ''
        message_type = whatsapp_message_dict.get('type', '')
        if message_type == 'text':
            message_text = whatsapp_message_dict.get('text', {}).get('body', '')
        elif message_type == 'interactive':
            interactive = whatsapp_message_dict.get('interactive', {})
            if interactive.get('type') == 'list_reply':
                message_text = interactive.get('list_reply', {}).get('title', '')
            elif interactive.get('type') == 'button_reply':
                message_text = interactive.get('button_reply', {}).get('title', '')
        elif message_type == 'location':
            location = whatsapp_message_dict.get('location', {})
            latitude = location.get('latitude')
            longitude = location.get('longitude')
            message_text = f"Ubicación: Latitud {latitude}, Longitud {longitude}"

        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)
        message_dict.update({
            'name': message_text,
            'message_body': message_text,
            'message_id': whatsapp_message_dict.get('id'),
            'to': whatsapp_message_dict.get('chatName') if whatsapp_message_dict.get('fromMe') else 'To Me',
            'chatId': whatsapp_message_dict.get('from'),
            'type': message_type,
            'senderName': whatsapp_message_dict.get('from'),
            'chatName': whatsapp_message_dict.get('from'),
            'author': whatsapp_message_dict.get('from'),
            'time': now_local.strftime('%Y-%m-%d %H:%M:%S'),
            'state': 'received',
        })

        try:
            contact = data.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('contacts', [{}])[0]
            if contact and contact.get('profile', {}).get('name'):
                message_dict['senderName'] = contact['profile']['name']
        except Exception:
            pass
        if message_type == 'image':
            try:
                media_id = data['entry'][0]['changes'][0]['value']['messages'][0]['image']['id']
                url = f"https://graph.facebook.com/v22.0/{media_id}"
                headers = {"Authorization": f"Bearer {whatsapp_instance_id.whatsapp_meta_api_token}"}

                image = requests.get(url.strip(), headers=headers).json()
                image_data = base64.b64encode(requests.get(image["url"], headers=headers).content)

                if whatsapp_messages_id:
                    message_attachment_dict = {
                        'name': 'Imagen',
                        'datas': image_data,
                        'type': 'binary',
                        'res_model': 'whatsapp.messages',
                        'res_id': whatsapp_messages_id.id,
                        'mimetype': 'image/jpeg',
                    }
                    attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                    message_dict['attachment_id'] = attachment_id.id
                    base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                    message_dict.update({
                        'message_body': whatsapp_message_dict.get('image', {}).get('caption', 'Imagen'),
                        'image_url': base_url + attachment_id.image_src
                    })
            except Exception as e:
                print(f"Error al procesar imagen: {str(e)}")

        elif message_type == 'audio':
            try:
                media_id = data['entry'][0]['changes'][0]['value']['messages'][0]['audio']['id']
                url = f"https://graph.facebook.com/v22.0/{media_id}"
                headers = {"Authorization": f"Bearer {whatsapp_instance_id.whatsapp_meta_api_token}"}

                audio = requests.get(url.strip(), headers=headers).json()
                audio_data = base64.b64encode(requests.get(audio["url"], headers=headers).content)
                if whatsapp_messages_id:
                    message_attachment_dict = {
                        'name': 'Audio',
                        'datas': audio_data,
                        'type': 'binary',
                        'res_model': 'whatsapp.messages',
                        'res_id': whatsapp_messages_id.id,
                        'mimetype': 'audio/mpeg'
                    }
                    attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                    message_dict['attachment_id'] = attachment_id.id
                    base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                    message_dict.update({
                        'message_body': 'Audio de WhatsApp',
                        'audio_url': base_url + attachment_id.local_url
                    })
            except Exception as e:
                print(f"Error al procesar audio: {str(e)}")
        elif message_type == 'video':
            try:
                video_data = whatsapp_message_dict.get('video', {})
                video_id = video_data.get('id')
                if video_id:
                    video_url = f"https://graph.facebook.com/v22.0/{video_id}"
                    headers = {"Authorization": f"Bearer {whatsapp_instance_id.whatsapp_meta_api_token}"}
                    video_response = requests.get(video_url, headers=headers)
                    if video_response.status_code == 200:
                        video_info = video_response.json()
                        video_content = requests.get(video_info["url"], headers=headers).content
                        video_base64 = base64.b64encode(video_content).decode('utf-8')

                        if whatsapp_messages_id:
                            message_attachment_dict = {
                                'name': 'Video de WhatsApp',
                                'datas': video_base64,
                                'type': 'binary',
                                'res_model': 'whatsapp.messages',
                                'res_id': whatsapp_messages_id.id,
                                'mimetype': 'video/mp4'
                            }
                            attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                            message_dict['attachment_id'] = attachment_id.id
                            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                            message_dict.update({
                                'message_body': 'Video de WhatsApp',
                                'video_url': base_url + attachment_id.local_url
                            })
                    else:
                        _logger.error("Error al obtener el video: %s", video_response.text)
            except Exception as e:
                _logger.error("Error al procesar video: %s", str(e))

        elif message_type == 'document':
            try:
                document_data = whatsapp_message_dict.get('document', {})
                document_id = document_data.get('id')
                if document_id:
                    document_url = f"https://graph.facebook.com/v22.0/{document_id}"
                    headers = {"Authorization": f"Bearer {whatsapp_instance_id.whatsapp_meta_api_token}"}
                    document_response = requests.get(document_url, headers=headers)
                    if document_response.status_code == 200:
                        document_info = document_response.json()
                        document_content = requests.get(document_info["url"], headers=headers).content
                        document_base64 = base64.b64encode(document_content).decode('utf-8')
                        filename = document_data.get('filename', 'Documento')
                        mime_type = document_data.get('mime_type', 'application/pdf')
                        if whatsapp_messages_id:
                            message_attachment_dict = {
                                'name': filename,
                                'datas': document_base64,
                                'type': 'binary',
                                'res_model': 'whatsapp.messages',
                                'res_id': whatsapp_messages_id.id,
                                'mimetype': mime_type
                            }
                            attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                            message_dict['attachment_id'] = attachment_id.id
                            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                            message_dict.update({
                                'message_body': f'Documento: {filename}',
                                'document_url': base_url + attachment_id.local_url
                            })
                    else:
                        _logger.error("Error al obtener el documento: %s", document_response.text)
            except Exception as e:
                _logger.error("Error al procesar documento: %s", str(e))

        elif message_type == 'sticker':
            try:
                sticker_data = data['entry'][0]['changes'][0]['value']['messages'][0]['sticker']
                sticker_id = sticker_data['id']
                is_animated = sticker_data.get('animated', False)
                url = f"https://graph.facebook.com/v22.0/{sticker_id}"
                headers = {"Authorization": f"Bearer {whatsapp_instance_id.whatsapp_meta_api_token}"}
                sticker_response = requests.get(url.strip(), headers=headers)
                if sticker_response.status_code != 200:
                    print(f"Error al obtener información del sticker: {sticker_response.text}")
                    return message_dict

                sticker_info = sticker_response.json()

                if 'url' in sticker_info:
                    sticker_url = sticker_info['url']
                elif 'link' in sticker_info:
                    sticker_url = sticker_info['link']
                elif 'image' in sticker_info:
                    sticker_url = sticker_info['image']
                else:
                    sticker_url = f"https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid={sticker_id}"
                    print(f"No se encontró URL para el sticker, usando URL alternativa: {sticker_url}")

                sticker_content_response = requests.get(sticker_url, headers=headers)
                if sticker_content_response.status_code != 200:
                    print(f"Error al descargar el sticker: {sticker_content_response.text}")
                    return message_dict

                sticker_data = base64.b64encode(sticker_content_response.content)

                if whatsapp_messages_id:
                    message_attachment_dict = {
                        'name': 'Sticker',
                        'datas': sticker_data,
                        'type': 'binary',
                        'res_model': 'whatsapp.messages',
                        'res_id': whatsapp_messages_id.id,
                        'mimetype': 'image/webp',
                    }
                    attachment_id = request.env['ir.attachment'].sudo().create(message_attachment_dict)
                    message_dict['attachment_id'] = attachment_id.id
                    base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                    message_dict.update({
                        'message_body': 'Sticker de WhatsApp',
                        'sticker_url': base_url + attachment_id.image_src,
                        'animated': is_animated
                    })
            except Exception as e:
                print(f"Error al procesar sticker: {str(e)}")

        elif message_type == 'location':
            try:
                location = whatsapp_message_dict.get('location', {})
                latitude = location.get('latitude')
                longitude = location.get('longitude')
                if latitude and longitude:
                    message_dict.update({
                        'message_body': f"Ubicación: Latitud {latitude}, Longitud {longitude}",
                        'location_latitude': latitude,
                        'location_longitude': longitude
                    })
            except Exception as e:
                print(f"Error al procesar ubicación: {str(e)}")

        return message_dict

    def _handle_session(self, whatsapp_message_dict):
        number = whatsapp_message_dict.get('from')

        if not number:
            return {"error": "El número de WhatsApp es requerido."}, 400

        user_session = UserSession(request.env)
        session = user_session.get_session(number)

        if not session:
            session = user_session.create_session(number, 'start', '')

        return {"session_id": session.id}, 200

    def _validate_meta_signature(self, payload):
        """
        Valida la firma X-Hub-Signature-256 enviada por Meta.

        Meta firma todos los webhooks con el App Secret usando HMAC-SHA256.
        Esto asegura que el mensaje realmente proviene de Meta.

        Retorna True si la firma es válida o si la validación está deshabilitada.
        """
        signature_header = request.httprequest.headers.get('X-Hub-Signature-256', '')

        if not signature_header.startswith('sha256='):
            _logger.debug("No se encontró firma X-Hub-Signature-256 válida")
            # Verificar si se permite sin firma (modo desarrollo)
            allow_unsigned = request.env['ir.config_parameter'].sudo().get_param(
                'whatsapp.webhook.allow_unsigned', 'True'  # Por defecto True para compatibilidad
            )
            if allow_unsigned.lower() == 'true':
                _logger.warning("Webhook de Meta recibido sin validación de firma (modo desarrollo)")
                return True
            return False

        signature = signature_header[7:]  # Quitar 'sha256='

        # Obtener el App Secret de Meta
        app_secret = request.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.meta.app_secret', ''
        )

        if not app_secret:
            return True  # Permitir mientras no esté configurado

        # Calcular firma esperada
        if isinstance(payload, str):
            payload = payload.encode('utf-8')

        expected_signature = hmac.new(
            app_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        is_valid = hmac.compare_digest(signature, expected_signature)

        if not is_valid:
            _logger.warning("Firma de webhook Meta inválida - posible mensaje falso")

        return is_valid

    @http.route('/whatsapp_meta/response/message', type='http', auth='public',
                methods=['GET', 'POST'], website=True, csrf=False)
    def whatsapp_meta_webhook(self):
        if request.httprequest.method == 'GET':
            whatsapp_instance = request.env['whatsapp.instance'].get_whatsapp_instance()
            verify_token = whatsapp_instance.whatsapp_meta_webhook_token
            if 'hub.mode' in request.httprequest.args and 'hub.verify_token' in request.httprequest.args:
                mode = request.httprequest.args.get('hub.mode')
                token = request.httprequest.args.get('hub.verify_token')
                if mode == 'subscribe' and token == verify_token:
                    challenge = request.httprequest.args.get('hub.challenge')
                    whatsapp_instance.sudo().configure_meta_webhook()
                    return http.Response(challenge, status=200)
                else:
                    return http.Response('ERROR', status=403)

        # Validar firma HMAC de Meta para mensajes POST
        raw_payload = request.httprequest.data
        if not self._validate_meta_signature(raw_payload):
            _logger.warning("Webhook rechazado - firma inválida desde IP: %s",
                          request.httprequest.remote_addr)
            return http.Response('Invalid signature', status=403)

        data = json.loads(raw_payload)
        if 'entry' in data and data['entry'] and 'changes' in data['entry'][0]:
            changes = data['entry'][0]['changes'][0]['value']
            if 'statuses' in changes:
                return http.Response('OK', status=200)

        if data.get('entry') and data['entry'][0].get('changes') and \
                data['entry'][0]['changes'][0].get('value', {}).get('messages'):

            whatsapp_message_obj = request.env['whatsapp.messages']
            messages = data['entry'][0]['changes'][0]['value']['messages']

            for whatsapp_message_dict in messages:
                message_id = whatsapp_message_dict.get('id')
                existing_message = whatsapp_message_obj.sudo().search([
                    ('message_id', '=', message_id)
                ], limit=1)

                if existing_message:
                    continue

                try:
                    session_result = self._handle_session(whatsapp_message_dict)
                    if 'error' in session_result:
                        continue
                    message_dict = self._prepare_message_dict(whatsapp_message_dict, data)
                    if message_dict:
                        new_message = whatsapp_message_obj.sudo().create(message_dict)
                        self._handle_chatbot(whatsapp_message_dict)

                except Exception as e:
                    print(f"Error procesando message: {str(e)}")
                    continue

        return http.Response('OK', status=200)

    def _prepare_message_dict(self, whatsapp_message_dict, data):
        """Prepara el diccionario del mensaje para su creación"""
        try:
            message_dict = {}
            whatsapp_instance_id = request.env['whatsapp.instance'].sudo().search(
                [('status', '!=', 'disable'), ('provider', '=', 'meta'),
                 ('default_instance', '=', True)], limit=1)
            if whatsapp_message_dict.get('context'):
                whatsapp_messages_id = request.env['whatsapp.messages'].sudo().search(
                    [('message_id', '=', whatsapp_message_dict.get('id'))])

                if whatsapp_messages_id and whatsapp_messages_id.partner_id:
                    message_dict.update({
                        'partner_id': whatsapp_messages_id.partner_id.id,
                        'model': whatsapp_messages_id.model,
                        'res_id': whatsapp_messages_id.res_id,
                    })
            else:
                res_partner_obj = request.env['res.partner.chatbot']
                res_partner_id = res_partner_obj.sudo().search(
                    [('chatId', '=', whatsapp_message_dict.get('from'))], limit=1)

                if not res_partner_id:
                    country_with_mobile = self.sanitized_country_mobile_from_meta_chat_id(
                        whatsapp_message_dict.get('from'))
                    res_partner_id = self.create_res_partner_against_meta_whatsapp(
                        whatsapp_message_dict.get('from'),
                        data['entry'][0]['changes'][0]['value']['contacts'][0]['profile']['name'],
                        country_with_mobile[0], country_with_mobile[1])

                message_dict.update({
                    'partner_id': res_partner_id.id,
                    'model': 'res.partner.chatbot',
                    'res_id': res_partner_id.id,
                })
            if whatsapp_instance_id:
                message_dict.update({
                    'whatsapp_instance_id': whatsapp_instance_id.id,
                    'whatsapp_message_provider': whatsapp_instance_id.provider
                })

            return self.meta_create_message_dict(whatsapp_message_dict, message_dict, data, whatsapp_instance_id)

        except Exception as e:
            print(f"Error preparando mensaje: {str(e)}")
            return None

    def resolve_short_url(self, short_url,number):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(short_url, allow_redirects=True, headers=headers, timeout=8)
            final_url = response.url
            return final_url
        except Exception as e:
            print(f"[ERROR] No se pudo resolver la URL corta: {e}")
            InvoiceFlow.solicitar_ubicacion_envio(number)
            return None

    def extract_coordinates_from_apple_maps_url(self, text,number):
        try:
            if text.lower().startswith("ubicación marcada "):
                url = text[len("ubicación marcada "):].strip()
            else:
                url = text.strip()

            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            coords_str = query_params.get('coordinate')
            if coords_str:
                coords = coords_str[0].split(',')
                if len(coords) == 2:
                    lat = float(coords[0])
                    lng = float(coords[1])
                    return lat, lng
        except Exception as e:
            print(f"[ERROR] Error extrayendo coordenadas Apple Maps: {e}")
            InvoiceFlow.solicitar_ubicacion_envio(number)
        return None, None

    def extract_coordinates_from_google_maps_url(self, url,number):
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        q_values = query_params.get('q')

        if q_values:
            coords = q_values[0].split(',')
            if len(coords) == 2:
                try:
                    lat = float(coords[0])
                    lng = float(coords[1])
                    return lat, lng
                except ValueError:
                    print("[ERROR] Error al convertir coordenadas a float")
                    InvoiceFlow.solicitar_ubicacion_envio(number)
                    return None, None
        print("[WARN] No se encontraron coordenadas en la URL")
        InvoiceFlow.solicitar_ubicacion_envio(number)
        return None, None

    def _handle_chatbot(self, message):
        number = message.get('from')
        mensaje_texto = (message.get("text", {}).get("body") or "").strip().lower()
        user_session = UserSession(request.env)
        session = user_session.get_session(number)
        Chatbot = request.env['whatsapp.chatbot'].sudo()

        # Fecha/hora local
        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)
        hora_local_str = now_local.strftime('%Y-%m-%d %H:%M:%S')

        chatbot_session = Chatbot.search([('number', '=', number)], limit=1)
        privacy_ok = bool(chatbot_session and chatbot_session.privacy_polic)
        chatbot_session.write({'last_activity': hora_local_str,})

        if "location" in message:
            latitude = message["location"].get("latitude")
            longitude = message["location"].get("longitude")

            if latitude and longitude:
                message['location_latitude'] = latitude
                message['location_longitude'] = longitude
            else:
                print("No se encontraron coordenadas en el mensaje de ubicación.")

        if not privacy_ok:
            if "interactive" in message:
                interactive = message["interactive"]
                body = (
                        interactive.get("button_reply", {}).get("id")
                        or interactive.get("list_reply", {}).get("id")
                )
                if body in {"acepta_condiciones", "rechaza_condiciones"}:
                    ConversationFlow.manejar_respuesta_interactiva(number, body)
                    return

            if not session or session.state != "manejar_politicas":
                user_session.update_session(number, state="manejar_politicas")

            PoliticasTerminosFlow.politicas(number, message)
            return

        palabras_salida = r"^(salir|adios|chao|bye|hasta luego)$"
        if mensaje_texto and re.match(palabras_salida, mensaje_texto.strip(), re.IGNORECASE):
            user_session.update_session(number, 'exit')
            try:
                UserSession(request.env).update_session(number, state="manejar_salida")
                MetaAPi.enviar_mensaje_con_botones_salida(number)
                return
            except Exception as e:
                print(f"Error al enviar mensaje de salida para {number}: {str(e)}")
                print(f"Error al enviar mensaje de salida: {str(e)}")
            return

        # === Procesar ubicación (location payload bruto) ===
        if "location" in message:
            latitude = message["location"].get("latitude")
            longitude = message["location"].get("longitude")

            estado_actual = user_session.get_session(number)

            if estado_actual.state == "farmacia-turno":
                DutyPharmacy.handle_duty_pharmacy(number, latitude, longitude)
                return
            elif estado_actual.state == "sucursal-cercana":
                BranchFlow.handle_location_input(number, latitude, longitude)
                return
            elif estado_actual.state == "solicitar_ubicacion_envio":
                InvoiceFlow.manejar_direccion_domicilio_ubi(number, latitude, longitude)
                return

        if session.state == "solicitar_ubicacion_envio":
            if "maps.apple.com" in mensaje_texto and "coordinate=" in mensaje_texto:
                lat, lng = self.extract_coordinates_from_apple_maps_url(mensaje_texto, number)
                if lat and lng:
                    InvoiceFlow.manejar_direccion_domicilio_ubi(number, lat, lng)
                else:
                    InvoiceFlow.manejar_direccion_domicilio_texto(number, mensaje_texto)
                return

            if "maps.app.goo.gl" in mensaje_texto:
                url_final = self.resolve_short_url(mensaje_texto, number)
                if url_final:
                    lat, lng = self.extract_coordinates_from_google_maps_url(url_final, number)
                    if lat and lng:
                        InvoiceFlow.manejar_direccion_domicilio_ubi(number, lat, lng)
                    else:
                        InvoiceFlow.manejar_direccion_domicilio_texto(number, mensaje_texto)
                else:
                    InvoiceFlow.manejar_direccion_domicilio_texto(number, mensaje_texto)
                return

        if "interactive" in message:
            interactive = message["interactive"]
            body = (
                    interactive.get("button_reply", {}).get("id")
                    or interactive.get("list_reply", {}).get("id")
            )

            estados = {
                "acepta_condiciones": ConversationFlow.manejar_respuesta_interactiva,
                "rechaza_condiciones": ConversationFlow.manejar_respuesta_interactiva,
                "farmacia-turno": ConversationFlow.manejar_respuesta_interactiva,
                "sucursal-cercana": ConversationFlow.manejar_respuesta_interactiva,
                "trabaja-con-nosotros": ConversationFlow.manejar_respuesta_interactiva,
                "regresar_menu": ConversationFlow.manejar_respuesta_interactiva,
                "cancelar_compra": ConversationFlow.manejar_respuesta_interactiva,
                "finalizar": ConversationFlow.manejar_respuesta_interactiva,
                "salir_conversacion": ConversationFlow.manejar_respuesta_interactiva,
                "recibir_email": ConversationFlow.manejar_respuesta_interactiva,
                "manejar_datos_factura": ConversationFlow.manejar_respuesta_interactiva,
                "cotizar-receta": ConversationFlow.manejar_respuesta_interactiva,
                "cotizar-receta-movil": ConversationFlow.manejar_respuesta_interactiva,
                "promociones": ConversationFlow.manejar_respuesta_interactiva,
                "ir_a_pagar": ConversationFlow.manejar_respuesta_interactiva,
                "editar_orden": ConversationFlow.manejar_respuesta_interactiva,
                "envio_domicilio": ConversationFlow.manejar_respuesta_interactiva,
                "eliminar_producto": ConversationFlow.manejar_respuesta_interactiva,
                "envio_local": ConversationFlow.manejar_respuesta_interactiva,
                "confirmar_datos": ConversationFlow.manejar_respuesta_interactiva,
                "pago_tarjeta": ConversationFlow.manejar_respuesta_interactiva,
                "pago_efectivo": ConversationFlow.manejar_respuesta_interactiva,
                "pago_transferencia": ConversationFlow.manejar_respuesta_interactiva,
                "pago_codigo": ConversationFlow.manejar_respuesta_interactiva,
                "pago_codigo_deuna": ConversationFlow.manejar_respuesta_interactiva,
                "regresar_paso": ConversationFlow.manejar_respuesta_interactiva,
                "confirmar_compra": ConversationFlow.manejar_respuesta_interactiva,
                "cuxibamba-loja": ConversationFlow.manejar_respuesta_interactiva,
                "cuxibamba-riobamba": ConversationFlow.manejar_respuesta_interactiva,
                "cuxibamba-ambato": ConversationFlow.manejar_respuesta_interactiva,
                "buscar_producto": ConversationFlow.manejar_respuesta_interactiva,
                "solicitar_cedula_ruc": ConversationFlow.manejar_respuesta_interactiva,
                "menu_secundario": ConversationFlow.manejar_respuesta_interactiva,
                "continuar_compra": ConversationFlow.manejar_respuesta_interactiva,
                "tipo_envio": ConversationFlow.manejar_respuesta_interactiva,
                "tipo_pago": ConversationFlow.manejar_respuesta_interactiva,
                "confirmar_datos_factura": ConversationFlow.manejar_respuesta_interactiva,
                "confirmar_orden_factura": ConversationFlow.manejar_respuesta_interactiva,
                "manejar_local_ciudad": ConversationFlow.manejar_respuesta_interactiva,
                "confirmar_nombre": InvoiceFlow.manejar_confirmacion_nombre,
                "modificar_nombre": InvoiceFlow.manejar_confirmacion_nombre,

                # "continuar_compra": ConversationFlow.manejar_respuesta_interactiva,

                # "manejar_orden": ConversationFlow.manejar_respuesta_interactiva,
            }

            if body in estados:
                user_session.update_session(number, body)
                estados[body](number, body)
                return

        # === Adjuntos ===
        if "image" in message:
            InvoiceFlow.handle_pay_method(number, message)
            return

        if "document" in message:
            InvoiceFlow.handle_pay_method(number, message)
            return

        # === Dispatch por estado de sesión ===
        dispatch = {
            "manejar_politicas": PoliticasTerminosFlow.politicas,
            "salir_politicas": PoliticasTerminosFlow.politicas,
            "promociones": BuyProductFlow.start_flow,
            "buscar_producto": BuyProductFlow.process_product_search,
            "seleccionar_producto": BuyProductFlow.process_product_selection,
            "ingresar_cantidad": BuyProductFlow.process_quantity_input,
            "solicitar_cedula_ruc": InvoiceFlow.manejar_cedula_ruc,
            "solicitar_nombres": InvoiceFlow.manejar_nombre,
            "solicitar_email": InvoiceFlow.manejar_email,
            "recibir_email": InvoiceFlow.recibir_email,
            "envio_domicilio": ConversationFlow.manejar_respuesta_interactiva,
            "envio_local": ConversationFlow.manejar_respuesta_interactiva,
            "manejar_local_ciudad": ConversationFlow.manejar_respuesta_interactiva,
            "solicitar_direccion": InvoiceFlow.manejar_direccion,
            "confirmar_datos": InvoiceFlow.manejar_orden,
            "manejar_datos_factura": InvoiceFlow.manejar_cedula_ruc,
            "solicitar_nombres_tarjeta": InvoiceFlow.manejar_nombre_tarjeta,
            "sucursal-cercana": BranchFlow.solicitar_ubicacion,
            "farmacia-turno": DutyPharmacy.farmacia_turno,
            "manejar_salida": MetaAPi.enviar_mensaje_con_botones_salida,
            "cotizar-receta-movil": AsesorMovilFlow.procesar_cotizacion_movil,
            "solicitar_ubicacion_envio": InvoiceFlow.manejar_direccion_domicilio_texto,
            "eliminar_producto_seleccionado": InvoiceFlow.manejar_eliminacion_producto,
            "menu_secundario": MetaAPi.enviar_mensaje_con_botones,
            "editar_orden": MetaAPi.edit_order,
            "continuar_compra": BuyProductFlow.start_flow,
            "tipo_envio": MetaAPi.botones_tipo_envio,
            "tipo_pago": InvoiceFlow.manejar_pago,
            "confirmar_datos_factura": MetaAPi.confirmar_datos_factura,
            "confirmar_orden_factura": MetaAPi.botones_confirmar_compra,

        }

        if session.state in dispatch:
            func = dispatch[session.state]
            return func(number, mensaje_texto)

        # Casos especiales sin acción
        if session.state in ("cotizar-receta", "confirmar_pago"):
            return

        # === Saludo / menú principal al recibir texto libre (con privacy_ok) ===
        if mensaje_texto:
            try:
                # Refresca sesión y chatbot
                user_session.update_session(number, 'start', orden='')
                chatbot_session.write({
                    'state': 'start',
                    'orden': '',
                    'last_activity': hora_local_str,
                })
                mensaje_hello = request.env['whatsapp_messages_user'].sudo().get_message('message_hello')
                MetaAPi.enviar_mensaje_texto(number, mensaje_hello)
                mensaje_envio = request.env['whatsapp_messages_user'].sudo().get_message('tiempo_envio')
                MetaAPi.enviar_mensaje_texto(number, mensaje_envio)
                user_session.update_session(number, state="menu_principal")
                MetaAPi.enviar_mensaje_lista(number, message)
            except Exception as e:
                _logger.error(f"Error en el flujo de saludo para {number}: {str(e)}")
                print(f"Error en el flujo de saludo: {str(e)}")
                return

        return {"status": "success", "session_id": session.id if session else None}

