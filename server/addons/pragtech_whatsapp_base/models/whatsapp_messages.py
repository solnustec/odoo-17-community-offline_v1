import base64
import logging
import json
import pytz
from odoo.http import request
from .res_partner import _fold
from odoo import api, fields, models
from datetime import datetime
from ..templates.meta_api import MetaAPi

_logger = logging.getLogger(__name__)


class WhatsappMessages(models.Model):
    _name = 'whatsapp.messages'
    _description = "Whatsapp Messages"
    _order = 'time desc'

    name = fields.Char('Name', readonly=True, help='Whatsapp message')
    message_body = fields.Text('Message', readonly=True,
                               help='If whatsapp message have caption (for image,video,document) else add message body')
    message_id = fields.Text('Message Id', readonly=True,
                             help='Whatsapp Message id')
    fromMe = fields.Boolean('Form Me', readonly=True,
                            help="If message is sent then from me true else false")
    to = fields.Char('To', readonly=True,
                     help='If message is sending from current instance then to contains To Me else add sender number')
    chatId = fields.Char('Chat ID', readonly=True,
                         help="It contains number & @.us")
    type = fields.Char('Type', readonly=True,
                       help='Type of message is text,image,document,etc.')
    msg_image = fields.Binary('Image', readonly=True,
                              help="If type of message is image then add message")
    location_longitude = fields.Float('Longitude', readonly=True,
                                      help="If type of message is location then add longitude")
    location_latitude = fields.Float('Latitude', readonly=True, )
    senderName = fields.Char('Sender Name', readonly=True,
                             help='If message is coming then it contains name sender '
                                  'else if message is sending from odoo then name/mobile of sender which has current instance attached')
    chatName = fields.Char('Chat Name', readonly=True,
                           help='Mobile number with country on which message is sending/receiving')
    author = fields.Char('Author', readonly=True,
                         help='From which number message is sending or receiving same as chatId')
    time = fields.Datetime('Date and time', readonly=True,
                           help='Time on which message is sent or receive')
    formatted_time = fields.Char(string="Formatted Time",
                                 compute="_compute_formatted_time", store=True)
    animated = fields.Boolean("Animated Sticker", default=False)

    partner_id = fields.Many2one('res.partner.chatbot', 'Partner Chatbot', readonly=True,
                                 help="If message is sending or receiving from partner then added partner id")
    state = fields.Selection([('sent', 'Sent'), ('received', 'Received')],
                             readonly=True,
                             help="It is based on message is sent or receive")
    attachment_id = fields.Many2one('ir.attachment', 'Attachment ',
                                    readonly=True,
                                    help="If message have an attachment then add attachment")
    attachment_data = fields.Binary(related='attachment_id.datas',
                                    string='Attachment',
                                    help="Download attachment")
    whatsapp_instance_id = fields.Many2one('whatsapp.instance',
                                           string='Whatsapp Instance',
                                           ondelete='restrict',
                                           help='Whatsapp Instance on which message is sent or received')
    whatsapp_message_provider = fields.Selection(
        [('whatsapp_chat_api', '1msg'), ('meta', 'Meta')],
        string="Whatsapp Service Provider",
        default='whatsapp_chat_api',
        help='Whatsapp provider on which message is sent or received')
    model = fields.Char('Related Document Model', index=True)
    res_id = fields.Many2oneReference('Related Document ID', index=True,
                                      model_field='model')
    is_read = fields.Boolean("Is Read", default=False)
    image_url = fields.Char("Image URL")
    audio_url = fields.Char("Audio URL")
    video_url = fields.Char("Video URL")
    document_url = fields.Char("Document URL")
    sticker_url = fields.Char("Sticker URL")
    location_url = fields.Char("Location URL")

    # Añade este campo si es necesario, o elimina su uso si no lo es
    direction = fields.Selection(
        [('inbound', 'Recibido'), ('outbound', 'Enviado')],
        string='Dirección',
        help='Dirección del mensaje'
    )

    sendername_fold = fields.Char(index=True, store=True, compute='_c_fold')
    chatname_fold = fields.Char(index=True, store=True, compute='_c_fold')
    message_body_fold = fields.Char(index=True, store=True, compute='_c_fold')
    chatid_fold = fields.Char(index=True, store=True, compute='_c_fold')
    chatid_digits = fields.Char(index=True, store=True, compute='_c_digits')
    message_count = fields.Integer(string="Conteo")
    hour = fields.Integer(compute="_compute_hour", store=True, index=True)
    message_hour = fields.Integer(
        string='Hora del Día',
        compute='_compute_message_hour',
        store=True
    )

    message_weekday = fields.Selection(
        [
            ('0', 'Lunes'),
            ('1', 'Martes'),
            ('2', 'Miércoles'),
            ('3', 'Jueves'),
            ('4', 'Viernes'),
            ('5', 'Sábado'),
            ('6', 'Domingo'),
        ],
        string='Día de la Semana',
        compute='_compute_message_weekday',
        store=True
    )

    @api.depends('time')
    def _compute_message_hour(self):
        for rec in self:
            if rec.time:
                rec.message_hour = rec.time.hour
            else:
                rec.message_hour = False

    @api.depends('time')
    def _compute_message_weekday(self):
        for rec in self:
            if rec.time:
                rec.message_weekday = str(rec.time.weekday())
            else:
                rec.message_weekday = False

    @api.depends('time')
    def _compute_hour(self):
        for rec in self:
            if rec.time:
                rec.hour = rec.time.hour
            else:
                rec.hour = False


    @api.depends('senderName', 'chatName', 'message_body', 'chatId')
    def _c_fold(self):
        for r in self:
            r.sendername_fold = _fold(r.senderName)
            r.chatname_fold = _fold(r.chatName)
            r.message_body_fold = _fold(r.message_body)
            r.chatid_fold = _fold(r.chatId)

    @api.depends('chatId')
    def _c_digits(self):
        import re
        for r in self:
            r.chatid_digits = re.sub(r'\D', '', r.chatId or '')

    def _send_message_to_bus(self, record):
        """Envia un mensaje al bus cuando un chat es creado o actualizado"""
        bus_channel = (self.env.cr.dbname, "whatsapp_notifications")
        message = {
            "id": record.id,
            "type": record.type,
            "timestamp": str(record.time),
        }
        self.env['bus.bus']._sendone(bus_channel, 'notification', message)

    @api.model
    def mark_messages_as_read(self, chatId):
        messages = self.search(
            [('chatId', '=', chatId), ('is_read', '=', False)]
        )
        if messages:
            messages.write({'is_read': True})
            self._send_message_to_bus(messages[0])
        return True

    @api.model
    def send_whatsapp_message(self, **args):
        if not args.get('message_body') and not args.get('attachment_data'):
            return {"error": True, "message": "No hay mensaje ni archivo para enviar"}

        whatsapp_instance = self.env['whatsapp.instance'].search([
            ('status', '!=', 'disable'),
            ('provider', '=', 'meta'),
            ('default_instance', '=', True)
        ], limit=1)

        chat_id = args.get('chatId')
        message_body = args.get('message_body', '')
        message_type = args.get('type', 'text')
        attachment_data = args.get('attachment_data')
        filename = args.get('filename') or 'archivo'
        mime_type = args.get('mime_type') or 'application/octet-stream'

        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)
        hora_local_str = now_local.strftime('%Y-%m-%d %H:%M:%S')

        bot_number = whatsapp_instance.gupshup_source_number if whatsapp_instance else request.env[
            'ir.config_parameter'].sudo().get_param('numero_chatbot')

        message_dict = {
            'name': message_body or bot_number,
            'message_id': bot_number,
            'chatId': chat_id,
            'type': message_type,
            'state': 'sent',
            'fromMe': True,
            'time': now_local.strftime('%Y-%m-%d %H:%M:%S'),
            'senderName': 'Chatbot',
            'to': chat_id,
            'author': bot_number
        }

        def create_response(message):
            return {
                "id": message.id,
                "chatId": chat_id,
                "message_body": message.message_body,
                "type": message_type,
                "filename": filename,
                "mime_type": mime_type,
            }

        message = False
        if message_type == 'text':
            result = MetaAPi.enviar_mensaje_texto(numero=chat_id, mensaje=message_body)
            if result:
                # pass
                # message = self.sudo().create({**message_dict, 'message_body': message_body})
                # return create_response(message)
                return {}
            return {"error": True, "message": "Falló el envío de texto"}

        if isinstance(attachment_data, str) and attachment_data.startswith('data:'):
            attachment_data = attachment_data.split(',')[1]

        try:
            base64.b64decode(attachment_data)
        except Exception as e:
            return {"error": True, "message": f"Base64 inválido: {str(e)}"}

        message = self.sudo().create(message_dict)

        attachment_dict = {
            'name': filename,
            'datas': attachment_data,
            'type': 'binary',
            'res_model': 'whatsapp.messages',
            'res_id': message.id,
            'mimetype': mime_type
        }

        attachment = self.env['ir.attachment'].sudo().create(attachment_dict)

        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        url_field = f"{message_type}_url"
        message.write({
            'message_body': message_body,
            'attachment_id': attachment.id,
            url_field: base_url + attachment.local_url
        })

        # Envío a través de Meta
        send_result = False
        if message_type == 'image':
            send_result = MetaAPi.enviar_mensaje_imagen(number=chat_id, imagen_base64=attachment_data)
        elif message_type == 'video':
            send_result = MetaAPi.enviar_mensaje_video(number=chat_id, video_base64=attachment_data,
                                                       caption=message_body)
        elif message_type == 'audio':
            send_result = MetaAPi.enviar_mensaje_audio(number=chat_id, audio_base64=attachment_data, filename=filename)
        elif message_type == 'document':
            send_result = MetaAPi.enviar_mensaje_documento(numero=chat_id, documento_base64=attachment_data,
                                                           caption=message_body, mime_type=mime_type)
        elif message_type == 'sticker':
            send_result = MetaAPi.enviar_mensaje_sticker(number=chat_id, sticker_base64=attachment_data)

        if send_result:
            return create_response(message)
        else:
            return {"error": True, "message": f"Falló el envío del tipo {message_type}"}

    @api.model
    def get_conversations(self, offset=0, limit=20):

        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)
        now_naive = now_local.replace(tzinfo=None)

        # 1. PRIMERO: cargar TODOS los chats fijados (sin paginación)
        pinned_chats = self.env['whatsapp.chatbot'].sudo().search([
            ('pinned', '=', True)
        ])
        pinned_chat_ids = [rec.number for rec in pinned_chats if rec.number]

        # 2. Luego: cargar chats normales con paginación (excluyendo los pinned ya cargados)
        exclude_domain = [('chatId', 'not in', pinned_chat_ids)] if pinned_chat_ids else []
        domain = [('chatId', '!=', False)] + exclude_domain

        grouped_chats = self.read_group(
            domain,
            ['chatId', 'time:max'],
            ['chatId'],
            orderby='time desc',
            offset=offset,
            limit=limit
        )

        # 3. Combinar: todos los pinned + los paginados normales
        all_chat_ids = pinned_chat_ids + [chat['chatId'] for chat in grouped_chats]

        # Eliminar duplicados manteniendo orden
        seen = set()
        unique_chat_ids = []
        for cid in all_chat_ids:
            if cid not in seen:
                seen.add(cid)
                unique_chat_ids.append(cid)

        # 4. Construir datos completos
        conversations_data = []
        for chat_id in unique_chat_ids:
            last_message = self.search([('chatId', '=', chat_id)], order="time desc", limit=1)
            if not last_message:
                continue

            # Buscar info del contacto y chatbot
            contact = self.env['whatsapp.contact'].sudo().search([('chat_id', '=', chat_id)], limit=1)
            chatbot = self.env['whatsapp.chatbot'].sudo().search([('number', '=', chat_id)], limit=1)

            last_incoming = self.search([
                ('chatId', '=', chat_id),
                ('fromMe', '=', False)
            ], order="time desc", limit=1)

            display_name = (
                    (contact and contact.custom_name) or
                    (last_incoming and last_incoming.senderName) or
                    last_message.senderName or
                    last_message.chatName or
                    chat_id
            )

            conversations_data.append({
                'chatId': chat_id,
                'displayName': display_name,
                'chatName': last_message.chatName or chat_id,
                'message_body': last_message.message_body or last_message.name or '',
                'lastMessageTime': last_message.time,
                'senderName': last_message.senderName or 'Desconocido',
                'unreadCount': self.search_count([
                    ('chatId', '=', chat_id),
                    ('is_read', '=', False),
                    ('res_id', '!=', False)
                ]),
                'pinned': bool(chatbot.pinned) if chatbot else False,
                'pin_sequence': chatbot.pin_sequence if chatbot else 10,
            })

        return conversations_data

    @api.model
    def get_unread_counts(self, chat_ids):
        """
        Método ligero para obtener solo los contadores de no leídos
        """
        if not chat_ids:
            return []

        unread_data = []
        for chat_id in chat_ids:
            unread_count = self.search_count([
                ('chatId', '=', chat_id),
                ('is_read', '=', False),
                ('res_id', '!=', False)
            ])
            unread_data.append({
                'chatId': chat_id,
                'unreadCount': unread_count
            })

        return unread_data

    @api.model
    def get_conversation_by_message_id(self, message_id):
        message = self.browse(message_id)
        conversations_data = []

        if not message.exists():
            return conversations_data

        # Tiempo del último mensaje
        formatted_time = message.time or fields.Datetime.now()

        chat_id = message.chatId

        # 1) Nombre personalizado (si existe)
        contact = self.env['whatsapp.contact'].sudo().search([('chat_id', '=', chat_id)], limit=1)

        # 2) Último mensaje entrante (para usar su senderName si no hay custom_name)
        last_incoming = self.search(
            [('chatId', '=', chat_id), ('fromMe', '=', False)],
            order='time desc',
            limit=1
        )

        # 3) Fijado/pinned (opcional pero útil para mantener orden visual)
        chatbot = self.env['whatsapp.chatbot'].sudo().search([('number', '=', chat_id)], limit=1)
        pinned = bool(chatbot and chatbot.pinned)

        # 4) Armar display_name con prioridades:
        # custom_name > senderName de último entrante > senderName del mensaje > chatName > chatId
        display_name = (
                (contact and contact.custom_name) or
                (last_incoming and last_incoming.senderName) or
                (message.senderName) or
                (message.chatName) or
                chat_id
        )

        # 5) Contador de no leídos (sólo de mensajes con res_id != False si así lo manejas)
        unread_count = self.search_count([
            ('chatId', '=', chat_id),
            ('is_read', '=', False),
            ('res_id', '!=', False),
        ])

        conversations_data.append({
            'chatId': chat_id,
            'displayName': display_name,  # ← IMPORTANTE para el frontend
            'chatName': message.chatName or display_name,
            'message_body': message.message_body or message.name,
            'lastMessageTime': formatted_time,
            'senderName': message.senderName or 'Desconocido',
            'unreadCount': unread_count,
            'pinned': pinned,  # ← mantiene el orden de fijados
        })

        return conversations_data

    @api.model
    def get_messages(self, chat_id, last_time=None):
        """Obtiene todos los mensajes de un chat, independientemente del estado"""
        domain = [('chatId', '=', chat_id)]

        # Ordenar por tiempo descendente para obtener los más recientes primero
        messages = self.search(domain, order='time desc', limit=10)

        # Convertir a lista y ordenar ascendente para el frontend
        message_list = [{
            'id': msg.id,
            'message_id': msg.message_id,
            'name': msg.name,
            'message_body': msg.message_body,
            'type': msg.type,
            'image_url': msg.image_url,
            'audio_url': msg.audio_url,
            'video_url': msg.video_url,
            'document_url': msg.document_url,
            'sticker_url': msg.sticker_url,
            'location_url': msg.location_url or (
                f"https://www.google.com/maps/?q={msg.location_latitude},{msg.location_longitude}"
                if msg.location_latitude and msg.location_longitude else None
            ),

            'location_latitude': msg.location_latitude,
            'location_longitude': msg.location_longitude,

            'fromMe': msg.fromMe,
            'time': msg.time,
            'senderName': msg.senderName,
            'chatName': msg.chatName,
        } for msg in messages]

        # Invertir el orden para que el más antiguo quede primero
        message_list.reverse()

        return {
            'messages': message_list
        }

    @api.model
    def send_message(self, message_data):
        """Envía un mensaje y actualiza el estado"""
        try:
            chat_id = message_data.get('chatId')
            message_type = message_data.get('type')
            user_tz = pytz.timezone('America/Guayaquil')
            now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
            now_local = now_utc.astimezone(user_tz)
            now_naive = now_local.replace(tzinfo=None)

            # now_utc_str = fields.Datetime.now()
            # now_utc_dt = fields.Datetime.from_string(now_utc_str)
            # now_local_dt = fields.Datetime.context_timestamp(request.env.user, now_utc_dt)
            # now_naive = now_local_dt.replace(tzinfo=None)

            if message_type == 'text':
                message_dict = {
                    'chatId': chat_id,
                    'fromMe': True,
                    'type': 'text',
                    'message_body': message_data.get('message', ''),
                    'time': now_naive
                }
            elif message_type in ['image', 'video', 'document']:
                file = message_data.get('file')
                if not file:
                    raise ValueError('No se proporcionó el archivo')

                file_base64 = base64.b64encode(file.read())
                message_dict = {
                    'chatId': chat_id,
                    'fromMe': True,
                    'type': message_type,
                    'attachment_data': file_base64,
                    'message_body': '',
                    'filename': file.name,
                    'time': now_naive
                }
            elif message_type == 'audio':
                audio = message_data.get('audio')
                if not audio:
                    raise ValueError('No se proporcionó el audio')

                audio_base64 = base64.b64encode(audio)
                message_dict = {
                    'chatId': chat_id,
                    'fromMe': True,
                    'type': 'audio',
                    'attachment_data': audio_base64,
                    'filename': 'voz.mp3',
                    'time': now_naive
                }
            else:
                raise ValueError(f'Tipo de mensaje no soportado: {message_type}')
            message = self.create(message_dict)
            if message_type in ['image', 'video', 'document', 'audio']:
                attachment_dict = {
                    'name': message_dict.get('filename', 'Archivo adjunto'),
                    'datas': message_dict.get('attachment_data'),
                    'type': 'binary',
                    'res_model': 'whatsapp.messages',
                    'res_id': message.id,
                    'mimetype': self._get_mimetype(message_type)
                }
                attachment = self.env['ir.attachment'].create(attachment_dict)
                message.write({'attachment_id': attachment.id})

            return {'success': True, 'message_id': message.id}

        except Exception as e:
            print(f"Error al enviar mensaje: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _get_mimetype(self, message_type):
        """Obtiene el mimetype correcto según el tipo de mensaje"""
        mimetypes = {
            'image': 'image/jpeg',
            'video': 'video/mp4',
            'document': 'application/pdf',
            'audio': 'audio/mpeg'
        }
        return mimetypes.get(message_type, 'application/octet-stream')

    @api.model
    def create(self, vals):
        if vals.get('message_body'):
            try:
                if isinstance(vals['message_body'], str):
                    message_content = json.loads(vals['message_body'])
                    if isinstance(message_content, dict):
                        if 'body' in message_content:
                            vals['message_body'] = message_content['body']
                        elif 'text' in message_content:
                            vals['message_body'] = message_content['text']
                elif isinstance(vals['message_body'], dict):
                    if 'body' in vals['message_body']:
                        vals['message_body'] = vals['message_body']['body']
                    elif 'text' in vals['message_body']:
                        vals['message_body'] = vals['message_body']['text']
            except:
                pass

        if vals.get('name'):
            try:
                if isinstance(vals['name'], str):
                    message_content = json.loads(vals['name'])
                    if isinstance(message_content, dict):
                        if 'body' in message_content:
                            vals['name'] = message_content['body']
                        elif 'text' in message_content:
                            vals['name'] = message_content['text']
                elif isinstance(vals['name'], dict):
                    if 'body' in vals['name']:
                        vals['name'] = vals['name']['body']
                    elif 'text' in vals['name']:
                        vals['name'] = vals['name']['text']
            except:
                pass

        record = super().create(vals)
        self.env.cr.commit()

        self._send_message_to_bus(record)

        return record

    def write(self, vals):
        res = super(WhatsappMessages, self).write(vals)
        if not 'is_read' in vals:
            for record in self:
                self.env.cr.commit()
                self._send_message_to_bus(record)
        return res

    @api.model
    def get_order_details(self, chat_id):
        """Obtiene los detalles de la orden para un chat específico."""
        message = self.search([('chatId', '=', chat_id), ('state', '=', 'confirmar_pago')], limit=1)
        if not message or not message.orden:
            return False

        try:
            order_data = json.loads(message.orden)
            return {
                'id': message.id,
                'state': message.state,
                'nombres_completo': order_data.get('nombres_completo', ''),
                'tipo_documento': order_data.get('tipo_documento', ''),
                'documento': order_data.get('documento', ''),
                'direccion_factura': order_data.get('direccion_factura', ''),
                'tipo_pago': order_data.get('tipo_pago', ''),
                'tipo_envio': order_data.get('tipo_envio', ''),
                'items': order_data.get('items', []),
                'total': sum(item.get('subtotal', 0) for item in order_data.get('items', [])),
                'created_at': message.create_date.strftime('%Y-%m-%d %H:%M:%S')
            }

        except Exception as e:
            _logger.error(f"Error al procesar los detalles de la orden: {str(e)}")
            return False

    def _build_conversation_dict(self, chat_id):
        """Arma el dict de una conversación dado su chat_id."""
        last_message = self.search([('chatId', '=', chat_id)], order="time desc", limit=1)
        if not last_message:
            return None

        # Buscar partner por chatId o number (según cómo esté tu modelo)
        partner = self.env['res.partner.chatbot'].sudo().search([
            '|', ('chatId', '=', chat_id),
            ('mobile', '=', chat_id),
        ], limit=1)

        last_incoming = self.search([('chatId', '=', chat_id), ('fromMe', '=', False)],
                                    order="time desc", limit=1)

        # --- Dentro de _build_conversation_dict(chat_id) ---
        contact = self.env['whatsapp.contact'].sudo().search([('chat_id', '=', chat_id)], limit=1)
        display_name = (
                (contact and contact.custom_name) or
                (partner and partner.name) or
                (last_incoming and last_incoming.senderName) or
                last_message.senderName or
                last_message.chatName or
                chat_id
        )

        unread_count = self.search_count([
            ('chatId', '=', chat_id),
            ('is_read', '=', False),
            ('res_id', '!=', False),
        ])

        return {
            'chatId': chat_id,
            'displayName': display_name,
            'chatName': last_message.chatName or last_message.time,
            'message_body': last_message.message_body or last_message.name,
            'lastMessageTime': last_message.time,
            'senderName': last_message.senderName or 'Desconocido',
            'unreadCount': unread_count,
        }

    @api.model
    def search_conversations(self, query, offset=0, limit=20):
        q = (query or '').strip()
        if not q:
            return self.get_conversations(offset=offset, limit=limit)

        import re
        qf = _fold(q)
        qdig = re.sub(r'\D', '', q)

        domain = ['|', '|', '|',
                  ('chatid_fold', 'ilike', qf),
                  ('sendername_fold', 'ilike', qf),
                  ('chatname_fold', 'ilike', qf),
                  ('message_body_fold', 'ilike', qf),
                  ]
        if qdig:
            domain = ['|', ('chatid_digits', 'ilike', qdig)] + domain

        grouped = self.read_group(
            [('chatId', '!=', False)] + domain,
            ['chatId', 'time:max'], ['chatId'],
            orderby='time desc', offset=offset, limit=limit
        )
        res = []
        for g in grouped:
            d = self._build_conversation_dict(g['chatId'])
            if d: res.append(d)
        return res



