import json
import base64
import requests
import re


import hashlib
from odoo.http import request
import logging
import base64
from .saveOdoo import SaveOdoo
import os

_logger = logging.getLogger(__name__)

# Constantes
API_VERSION = "v22.0"
BASE_URL = "https://graph.facebook.com"
DEFAULT_TIMEOUT = 10


class MetaAPIError(Exception):
    """Errores de la API de Meta"""

    def __init__(self, message, status_code=None, response=None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)

    def __str__(self):
        error_msg = self.message
        if self.status_code:
            error_msg += f" (Código de estado: {self.status_code})"
        if self.response:
            error_msg += f" - Respuesta: {self.response}"
        return error_msg


def handle_api_response(response):
    """Función auxiliar para manejar respuestas de la API de manera consistente"""
    try:
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        error_msg = f"Error en la API: {str(e)}"
        print(error_msg)
        raise MetaAPIError(
            message=error_msg,
            status_code=e.response.status_code if e.response else None,
            response=e.response.text if e.response else None
        )


class MetaAPi:
    _config = None

    @classmethod
    def _get_headers(cls, access_token, content_type=None):
        """Método auxiliar para generar headers consistentes"""
        headers = {"Authorization": f"Bearer {access_token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    @classmethod
    def _get_api_url(cls, phone_number, endpoint):
        """Método auxiliar para generar URLs de API consistentes"""
        return f"{BASE_URL}/{API_VERSION}/{phone_number}/{endpoint}"

    @classmethod
    def enviar_imagen_desde_url(cls, numero, image_url, caption=""):
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                print(f"Error: La URL no contiene una imagen válida (Content-Type: {content_type})")
                cls.enviar_mensaje_texto(numero, "Error: No se pudo procesar la imagen.")
                return False

            image_data = base64.b64encode(response.content).decode("utf-8")

            resultado = cls.enviar_imagen(numero, image_data, caption)

            if not resultado:
                print("No se pudo enviar la imagen según enviar_imagen")
                cls.enviar_mensaje_con_botones_salida(numero)
            return resultado

        except requests.RequestException as e:
            print(f"Error al descargar la imagen desde la URL: {str(e)}")
            cls.enviar_mensaje_texto(numero, "No se pudo descargar la imagen. Intenta nuevamente.")
            cls.enviar_mensaje_con_botones_salida(numero)
            return False
        except Exception as e:
            print(f"Error inesperado al procesar la imagen desde URL: {str(e)}")
            cls.enviar_mensaje_texto(numero, "Ha ocurrido un error al procesar la imagen. Intenta nuevamente.")
            cls.enviar_mensaje_con_botones_salida(numero)
            return False

    @classmethod
    def get_whatsapp_instance(cls, env=None):
        if env is None:
            try:
                # Si hay un request, se usa, pero en cron no se alcanzará aquí.
                env = request.env
            except Exception as e:
                raise MetaAPIError("No se pudo obtener el entorno de Odoo: " + str(e))
        base_url = env['ir.config_parameter'].sudo().get_param('web.base.url')
        url = f"{base_url}/api/whatsapp_instance"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': ''
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)

            response.raise_for_status()
            data = response.json()

            required_fields = ['meta_phone_number', 'meta_api_token']
            missing_fields = [field for field in required_fields if field not in data]

            if missing_fields:
                return None

            if not data.get('meta_phone_number') or not data.get('meta_api_token'):
                return None

            meta_url = f"https://graph.facebook.com/v22.0/{data.get('meta_phone_number')}/messages"

            meta_access_token = data.get('meta_api_token')

            return {
                "meta_url": meta_url,
                "meta_access_token": meta_access_token,
                "meta_phone_number": data['meta_phone_number']
            }
        except requests.RequestException as e:
            print(f"Error al consultar la API: {str(e)}")
            return None

    @classmethod
    def _send_message(cls, number, payload, env=None):
        """Método base para enviar messages"""
        try:
            data = cls.get_whatsapp_instance(env)
            if not data:
                raise MetaAPIError("No se pudo obtener la instancia de WhatsApp")

            headers = cls._get_headers(data['meta_access_token'], "application/json")
            response = requests.post(
                data['meta_url'],
                headers=headers,
                json=payload,
                timeout=DEFAULT_TIMEOUT
            )
            return handle_api_response(response)
        except Exception as e:
            print(f"Error al enviar message: {str(e)}")
            raise MetaAPIError(f"Error al enviar message: {str(e)}")

    @classmethod
    def _upload_media(cls, file_bytes, mime_type, filename):
        """Método base para subir archivos multimedia"""
        try:
            data = cls.get_whatsapp_instance()
            if not data:
                print("No se pudo obtener la instancia de WhatsApp")
                return False

            headers = cls._get_headers(data['meta_access_token'])
            files = {
                'file': (filename, file_bytes, mime_type),
                'messaging_product': (None, 'whatsapp'),
            }

            media_url = cls._get_api_url(data['meta_phone_number'], 'media')
            response = requests.post(media_url, headers=headers, files=files, timeout=DEFAULT_TIMEOUT)

            if response.status_code != 200:
                print(f"Error en la subida: {response.text}")
                return False

            result = response.json()
            media_id = result.get('id')

            if not media_id:
                print("No se recibió ID de media en la respuesta")
                return False

            return media_id

        except Exception as e:
            print(f"Error al subir archivo multimedia: {str(e)}")
            print(f"Tipo de error: {type(e)}")
            return False

    @classmethod
    def enviar_mensaje_texto(cls, numero, mensaje, env=None):

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero,
            "type": "text",
            "text": {
                "body": mensaje
            }
        }

        response = cls._send_message(numero, payload,env=env)
        if response:
            SaveOdoo.save_bot_message(numero, mensaje)
        return response

    @staticmethod
    def enviar_imagen_al_usuario(numero, image_path, caption=""):
        """
        Envía una imagen ubicada en `image_path` al número especificado.

        Parámetros:
            numero (str): Número de teléfono del destinatario.
            image_path (str): Ruta local del archivo de imagen.
            caption (str): Texto descriptivo para la imagen (opcional).
        """
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("utf-8")

        resultado = MetaAPi.enviar_imagen(numero, image_data, caption)

        if resultado is None:
            MetaAPi.enviar_mensaje_texto(numero, "Error al enviar la imagen.")
            MetaAPi.enviar_mensaje_con_botones_salida(numero)
        return resultado

    @classmethod
    def enviar_imagen(cls, numero, imagen_base64, caption=""):
        """
        Envía una imagen al usuario.

        Parámetros:
            numero (str): Número de teléfono del destinatario.
            imagen_base64 (str): Imagen ya codificada en base64.
            caption (str): Texto descriptivo para la imagen (opcional).

        Retorna:
            El resultado del envío de la imagen (según lo devuelto por enviar_mensaje_imagen).
        """
        return cls.enviar_mensaje_imagen(numero, imagen_base64, caption)

    @classmethod
    def enviar_mensaje_documento(cls, numero, documento_base64, caption=None, mime_type='application/octet-stream',
                                 filename='archivo'):
        """Envía un documento de cualquier tipo permitido a través de la API de WhatsApp (Meta)"""

        try:
            # Obtener la instancia activa
            whatsapp_instance = request.env['whatsapp.instance'].sudo().search([
                ('status', '!=', 'disable'),
                ('provider', '=', 'meta'),
                ('default_instance', '=', True)
            ], limit=1)

            if not whatsapp_instance:
                print("❌ No se encontró una instancia de WhatsApp activa")
                return False

            # Limpiar base64 si tiene encabezado tipo data:
            if documento_base64.startswith('data:'):
                documento_base64 = documento_base64.split(',')[1]

            # Validar base64
            try:
                documento_bytes = base64.b64decode(documento_base64)
            except Exception as e:
                print(f"❌ El documento recibido no está en base64 válido: {str(e)}")
                return False

            # Tipos MIME permitidos (ampliables)
            TIPOS_PERMITIDOS = [
                'application/pdf',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'text/plain',
                'application/zip',
                'application/vnd.rar',
            ]
            if mime_type not in TIPOS_PERMITIDOS:
                print(f"❌ Tipo MIME no permitido: {mime_type}")
                return False

            # Subir el documento a la API de Meta
            media_id = cls._upload_media(documento_bytes, mime_type, filename)
            if not media_id:
                print("❌ No se pudo subir el documento a la API de Meta")
                return False

            # Preparar el payload
            payload = {
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "document",
                "document": {
                    "id": media_id,
                    "caption": caption or filename,
                    "filename": filename
                }
            }

            # Enviar mensaje
            response = requests.post(
                f"https://graph.facebook.com/v22.0/{whatsapp_instance.whatsapp_meta_phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {whatsapp_instance.whatsapp_meta_api_token}",
                    "Content-Type": "application/json"
                },
                json=payload
            )

            if response.status_code == 200:
                return True
            else:
                print(f"❌ Error al enviar documento: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"❌ Excepción general al enviar documento: {str(e)}")
            return False

    @classmethod
    def enviar_mensaje_imagen(cls, number, imagen_base64, caption=""):
        try:

            whatsapp_instance = request.env['whatsapp.instance'].sudo().search(
                [('status', '!=', 'disable'), ('provider', '=', 'meta'), ('default_instance', '=', True)], limit=1)
            if not whatsapp_instance:
                print("No se encontró una instancia de WhatsApp activa")
                return False

            if isinstance(imagen_base64, str):
                try:
                    # Limpiar cabecera base64 si existe
                    match = re.match(r'^data:image\/[a-zA-Z]+;base64,(.*)$', imagen_base64)
                    if match:
                        imagen_base64 = match.group(1)

                    imagen_bytes = base64.b64decode(imagen_base64)
                    media_id = cls._upload_media(imagen_bytes, 'image/jpeg', 'image.jpg')
                    if not media_id:
                        print("No se pudo obtener el media_id de la API")
                        return False

                    payload = {
                        "messaging_product": "whatsapp",
                        "to": number,
                        "type": "image",
                        "image": {"id": media_id, "caption": caption}
                    }

                    response = requests.post(
                        f"https://graph.facebook.com/v22.0/{whatsapp_instance.whatsapp_meta_phone_number_id}/messages",
                        headers={
                            "Authorization": f"Bearer {whatsapp_instance.whatsapp_meta_api_token}",
                            "Content-Type": "application/json"
                        },
                        json=payload
                    )

                    if response.status_code == 200:
                        response_json = response.json()
                        message_id = response_json.get('messages', [{}])[0].get('id')
                        if message_id:
                            status_url = f"https://graph.facebook.com/v22.0/{message_id}"
                            requests.get(
                                status_url,
                                headers={"Authorization": f"Bearer {whatsapp_instance.whatsapp_meta_api_token}"},
                                timeout=10
                            )
                        return True
                    else:
                        _logger.error(f"Error al enviar imagen: {response.text}")
                        return False

                except Exception as e:
                    print(f"Error en el proceso de envío de imagen: {str(e)}")
                    return False
            else:
                print(f"El parámetro imagen_base64 no es una cadena válida. Tipo: {type(imagen_base64)}")
                return False
        except Exception as e:
            print(f"Error al enviar imagen: {str(e)}")
            return False

    @classmethod
    def enviar_mensaje_audio(cls, number, audio_base64, filename="voz.mp3"):
        """Envía un audio a WhatsApp"""
        try:
            if audio_base64.startswith('data:audio'):
                audio_base64 = audio_base64.split(',')[1]
            audio_bytes = base64.b64decode(audio_base64)

            media_id = cls._upload_media(audio_bytes, 'audio/mpeg', filename)

            payload = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "audio",
                "audio": {"id": media_id}
            }

            response = cls._send_message(number, payload)
            return response

        except Exception as e:
            print(f"Error al enviar audio: {str(e)}")
            return False

    @classmethod
    def enviar_mensaje_lista(cls, number,
                             message="¿En qué te puedo ayudar hoy? 👇\n\n"
                                     "1. Cotizar receta\n"
                                     "2. Sucursal cercana\n"
                                     "3. Farmacia turno/24h\n"
                                     "4. Tienda\n"
                                     "5. Trabaja con nosotros\n"
                                     "6. Salir"):
        """Envía un message con botones interactivos a WhatsApp."""
        data = cls.get_whatsapp_instance()
        access_token = data['meta_access_token']
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Obtener mensaje de bienvenida personalizado de la base de datos
        mensaje_saludo = request.env['whatsapp_messages_user'].sudo().get_message('bienvenida')

        payload = {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": mensaje_saludo
                },
                "footer": {
                    "text": "Elige una opción"
                },
                "action": {
                    "button": "Menú de opciones",
                    "sections": [
                        {
                            "title": "Opciones disponibles",
                            "rows": [
                                {
                                    "id": "cotizar-receta",
                                    "title": "Cotiza con un asesor",
                                    # "description": "contacta con un asesor"
                                },
                                {
                                    "id": "promociones",
                                    "title": "Tienda Cuxibamba",
                                    # "description": "comprar en linea"
                                },
                                # {
                                #     "id": "farmacia-turno",
                                #     "title": "Farmacia turno/24h",
                                #     # "description": "conocer la farmacia turno/24h más cercana"
                                # },
                                # {
                                #     "id": "sucursal-cercana",
                                #     "title": "Sucursal cercana",
                                #     # "description": "conocer la sucursal más cercana"
                                # },
                                #
                                # {
                                #     "id": "trabaja-con-nosotros",
                                #     "title": "Trabaja con nosotros",
                                #     # "description": "información sobre postulaciones"
                                # },
                                {
                                    "id": "finalizar",
                                    "title": "Salir",
                                    # "description": "salir del chat"
                                }
                            ]
                        }
                    ]
                }
            }
        }
        response = requests.post(data['meta_url'], headers=headers, data=json.dumps(payload))
        SaveOdoo.save_bot_message(number, mensaje_saludo)
        return response.json()

    @classmethod
    def enviar_mensaje_con_botones_salida(cls, numero,
                                          mensaje="¿Cómo deseas continuar?\n\n"
                                                  "1. Regresar al menú\n"
                                                  "2. Salir del chat"):
        """Envía un mensaje con botones interactivos a WhatsApp."""
        data = cls.get_whatsapp_instance()
        headers = {
            "Authorization": f"Bearer {data['meta_access_token']}",
            "Content-Type": "application/json"
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "¿Cómo deseas continuar?"},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "regresar_menu",
                                                    "title": "Regresar al menú"}},
                        {"type": "reply", "reply": {"id": "finalizar",
                                                    "title": "Salir del chat"}},
                    ]
                }
            }
        }

        response = requests.post(data['meta_url'], headers=headers, data=json.dumps(payload))
        SaveOdoo.save_bot_message(numero, mensaje)
        return response.json()

    @classmethod
    def _create_interactive_message(cls, number, body_text, action_data, interactive_type="button"):
        """Método base para crear messages interactivos"""
        return {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "interactive",
            "interactive": {
                "type": interactive_type,
                "body": {"text": body_text},
                "action": action_data
            }
        }

    @classmethod
    def botones_tipo_envio(cls, number, message="¿Cómo desea la entrega?\n\n"
                                                "1. Domicilio\n"
                                                "2. Retiro en local\n"
                                                "3. Regresar atrás"):
        """Envía botones para seleccionar tipo de envío"""
        message = request.env['whatsapp_messages_user'].sudo().get_message('tipo_envio')
        action_data = {
            "buttons": [
                {"type": "reply", "reply": {"id": "envio_domicilio", "title": "Domicilio"}},
                {"type": "reply", "reply": {"id": "envio_local", "title": "Retiro en local"}},
                {"type": "reply", "reply": {"id": "regresar_paso", "title": "Regresar atrás"}}
            ]
        }
        payload = cls._create_interactive_message(number, message, action_data)
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def botones_tipo_pago(cls, number, message="¿Cúal es tu forma de pago?\n\n"
                                               "Tarjeta\n"
                                               "Efectivo (Loja)\n"
                                               "Transferencia\n"
                                               "Pago por ahorira! / deuna!"
                                               "Regresar atrás"):
        """Envía botones para seleccionar forma de pago"""
        message = request.env['whatsapp_messages_user'].sudo().get_message('tipo_pago')
        action_data = {
            "button": "Método de pago",
            "sections": [{
                "title": "Tipos de pagos",
                "rows": [
                    {"id": "pago_tarjeta", "title": "Tarjeta"},
                    {"id": "pago_efectivo", "title": "Efectivo (Loja)"},
                    {"id": "pago_transferencia", "title": "Transf. (Bco. Pichincha)"},
                    # {"id": "pago_codigo", "title": "Ahorita!"},
                    {"id": "pago_codigo_deuna", "title": "Deuna! (Bco. Pichincha)"},
                    # {"id": "pago_codigo", "title": "Ahorita!/Deuna!"},
                    {"id": "pago_codigo", "title": "Ahorita! (Bco. Loja)"},
                    {"id": "regresar_paso", "title": "Regresar atrás"}
                ]
            }]
        }
        payload = cls._create_interactive_message(number, message, action_data, "list"
                                                  )
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def botones_tipo_pago_tarjeta(cls, number, message="¿Cúal es tu forma de pago?\n\n"
                                               "Efectivo (Loja)\n"
                                               "Transferencia\n"
                                               "Pago por ahorira! / deuna!"
                                               "Regresar atrás"):
        """Envía botones para seleccionar forma de pago"""
        message = request.env['whatsapp_messages_user'].sudo().get_message('tipo_pago')
        action_data = {
            "button": "Método de pago",
            "sections": [{
                "title": "Tipos de pagos",
                "rows": [
                    {"id": "pago_efectivo", "title": "Efectivo (Loja)"},
                    {"id": "pago_transferencia", "title": "Transferencia"},
                    # {"id": "pago_codigo", "title": "Ahorita!"},
                    {"id": "pago_codigo_deuna", "title": "Deuna!"},
                    # {"id": "pago_codigo", "title": "Ahorita!/Deuna!"},
                    {"id": "pago_codigo", "title": "Ahorita!"},
                    {"id": "regresar_paso", "title": "Regresar atrás"}
                ]
            }]
        }
        payload = cls._create_interactive_message(number, message, action_data, "list"
                                                  )
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def mostrar_ciudades_disponibles(cls, number, message="Selecciona la ciudad donde deseas retirar tu compra:\n\n"
                                                          "Loja\n"
                                                          "Riobamba\n"
                                                          "Ambato\n"
                                                          "Regresar atrás"):
        """Envía lista de ciudades disponibles"""
        message = request.env['whatsapp_messages_user'].sudo().get_message('withdraw_purchase')
        action_data = {
            "button": "Seleccionar Ciudad",
            "sections": [{
                "title": "Ciudades disponibles",
                "rows": [
                    {"id": "cuxibamba-loja", "title": "Loja"},
                    # {"id": "cuxibamba-riobamba", "title": "Riobamba"},
                    # {"id": "cuxibamba-ambato", "title": "Ambato"},
                    {"id": "regresar_paso", "title": "Regresar atrás"}
                ]
            }]
        }
        payload = cls._create_interactive_message(
            number, message,
            action_data,
            "list"
        )
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    # @classmethod
    # def enviar_mensaje_con_botones(cls, number, message="¿Qué deseas hacer ahora?\n\n"
    #                                                     "Seguir comprando\n"
    #                                                     "Proceder al pago\n"
    #                                                     "Salir"):
    #     """Envía botones para continuar comprando o ir a pagar"""
    #     action_data = {
    #         "buttons": [
    #             {"type": "reply", "reply": {"id": "continuar_compra", "title": "Seguir comprando"}},
    #             {"type": "reply", "reply": {"id": "ir_a_pagar", "title": "Proceder al pago"}},
    #             {"type": "reply", "reply": {"id": "finalizar", "title": "Salir"}}
    #         ]
    #     }
    #     payload = cls._create_interactive_message(number, "¿Qué deseas hacer ahora?", action_data)
    #     response = cls._send_message(number, payload)
    #     SaveOdoo.save_bot_message(number, message)
    #     return response

    @classmethod
    def enviar_mensaje_con_botones(cls, number, message="¿Qué deseas hacer ahora?\n\n"
                                                        "Editar orden\n"
                                                        "Proceder al pago\n"
                                                        "Salir"):
        """Envía botones para continuar comprando o ir a pagar"""
        action_data = {
            "buttons": [
                {"type": "reply", "reply": {"id": "editar_orden", "title": "Editar orden"}},
                {"type": "reply", "reply": {"id": "ir_a_pagar", "title": "Proceder al pago"}},
                {"type": "reply", "reply": {"id": "finalizar", "title": "Salir"}}
            ]
        }
        payload = cls._create_interactive_message(number, "¿Qué deseas hacer ahora?", action_data)
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def botones_confirmar_compra(cls, number,
                                 message="¿Deseas continuar con la compra o cancelarla?\n\n"
                                         "Continuar\n"
                                         "Cancelar"):
        """Envía botones para confirmar o cancelar la compra"""
        action_data = {
            "buttons": [
                {"type": "reply", "reply": {"id": "confirmar_compra", "title": "Continuar"}},
                {"type": "reply", "reply": {"id": "cancelar_compra", "title": "Cancelar"}}
            ]
        }
        payload = cls._create_interactive_message(number, "¿Deseas continuar con la compra o cancelarla?", action_data)
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def edit_order(cls, number,
                                 message="¿Qué deseas hacer?\n\n"
                                         "Seguir comprando\n"
                                         "Eliminar producto\n"
                                         "Regresar atrás"):
        """Envía botones para confirmar o cancelar la compra"""
        action_data = {
            "buttons": [
                {"type": "reply", "reply": {"id": "continuar_compra", "title": "Seguir comprando"}},
                {"type": "reply", "reply": {"id": "eliminar_producto", "title": "Eliminar producto"}},
                {"type": "reply", "reply": {"id": "regresar_paso", "title": "Regresar atrás"}}
            ]
        }
        payload = cls._create_interactive_message(number, "¿Qué deseas hacer?", action_data)
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def contactar_asesor(cls, number,
                         message="¿Desea buscar otro producto o contactar un asesor?\n\n"
                                 "Buscar producto\n"
                                 "Contactar un asesor\n"
                                 "Regresar al menú"):
        """Envía botones para confirmar o cancelar la compra"""
        action_data = {
            "buttons": [
                {"type": "reply", "reply": {"id": "promociones", "title": "Buscar otro producto"}},
                {"type": "reply", "reply": {"id": "cotizar-receta", "title": "Contactar un asesor"}},
                {"type": "reply", "reply": {"id": "regresar_menu", "title": "Regresar al menú"}}
            ]
        }
        payload = cls._create_interactive_message(number, "¿Desea buscar otro producto o contactar un asesor?", action_data)
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def confirmar_datos_factura(cls, number,
                                message="¿Son correctos los datos?\n\n"
                                        "Sí\n"
                                        "No"):
        """Envía botones para confirmar o cancelar la compra"""
        action_data = {
            "buttons": [
                {"type": "reply", "reply": {"id": "confirmar_datos", "title": "Sí"}},
                {"type": "reply", "reply": {"id": "solicitar_cedula_ruc", "title": "No"}}
            ]
        }
        payload = cls._create_interactive_message(number, "¿Son correctos los datos?", action_data)
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def confirmar_nombre_botones(cls, number, nombre):
        """Envía botones para confirmar o modificar el nombre ingresado"""
        message = f"El nombre ingresado es: *{nombre}*\n\n¿Es correcto?"
        action_data = {
            "buttons": [
                {"type": "reply", "reply": {"id": "confirmar_nombre", "title": "Confirmar"}},
                {"type": "reply", "reply": {"id": "modificar_nombre", "title": "Modificar"}}
            ]
        }
        payload = cls._create_interactive_message(number, message, action_data)
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def confirmar_datos_email(cls, number,
                                message="¿Desea agregar correo electrónico?\n\n"
                                        "Sí\n"
                                        "No"):
        """Envía botones para confirmar o cancelar la compra"""
        action_data = {
            "buttons": [
                {"type": "reply", "reply": {"id": "recibir_email", "title": "Sí"}},
                {"type": "reply", "reply": {"id": "manejar_datos_factura", "title": "No"}}
            ]
        }
        payload = cls._create_interactive_message(number, "¿Desea agregar correo electrónico?", action_data)
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response

    @classmethod
    def confirmar_politicas(cls, number):
        """Envía botones para confirmar o cancelar la compra"""
        message = request.env['whatsapp_messages_user'].sudo().get_message('confirmar_politicas')
        action_data = {
            "buttons": [
                {"type": "reply", "reply": {"id": "acepta_condiciones", "title": "Estoy de acuerdo"}},
                {"type": "reply", "reply": {"id": "rechaza_condiciones", "title": "No en este momento"}}
            ]
        }
        payload = cls._create_interactive_message(number, message, action_data)
        response = cls._send_message(number, payload)
        SaveOdoo.save_bot_message(number, message)
        return response


    @classmethod
    def enviar_mensaje_video(cls, number, video_base64, caption=""):
        """Envía un video a WhatsApp"""
        try:
            if video_base64.startswith('data:'):
                video_base64 = video_base64.split(',')[1]
            video_bytes = base64.b64decode(video_base64)

            media_id = cls._upload_media(video_bytes, 'video/mp4', 'video.mp4')

            payload = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "video",
                "video": {
                    "id": media_id,
                    "caption": caption
                }
            }

            response = cls._send_message(number, payload)
            return response

        except Exception as e:
            print(f"Error al enviar video: {str(e)}")
            return False

    @classmethod
    def enviar_mensaje_sticker(cls, number, sticker_base64):
        """Envía un sticker a WhatsApp"""
        try:
            # Limpiar el base64 si viene con prefijo data:
            if sticker_base64.startswith('data:'):
                sticker_base64 = sticker_base64.split(',')[1]

            # Decodificar el base64 a bytes
            sticker_bytes = base64.b64decode(sticker_base64)

            # Obtener la instancia de WhatsApp
            whatsapp_instance = request.env['whatsapp.instance'].sudo().search(
                [('status', '!=', 'disable'), ('provider', '=', 'meta'),
                 ('default_instance', '=', True)], limit=1)

            if not whatsapp_instance:
                print("No se encontró una instancia de WhatsApp activa")
                return False

            # Subir el sticker a la API de Meta
            # Los stickers deben estar en formato WebP
            media_id = cls._upload_media(sticker_bytes, 'image/webp', 'sticker.webp')
            if not media_id:
                print("No se pudo subir el sticker a la API de Meta")
                return False

            # Preparar el payload
            payload = {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "sticker",
                "sticker": {
                    "id": media_id
                }
            }

            # Hacer la petición a la API
            response = requests.post(
                f"https://graph.facebook.com/v22.0/{whatsapp_instance.whatsapp_meta_phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {whatsapp_instance.whatsapp_meta_api_token}",
                    "Content-Type": "application/json"
                },
                json=payload
            )

            if response.status_code == 200:
                return True
            else:
                print(f"Error al enviar sticker: {response.text}")
                return False

        except Exception as e:
            print(f"Error al enviar sticker: {str(e)}")
            return False

    @classmethod
    def enviar_mensaje_template(cls, numero, template_name, language_code="es", variables=None, button_url=None):
        whatsapp_instance = request.env['whatsapp.instance'].sudo().search([
            ('status', '!=', 'disable'),
            ('provider', '=', 'meta'),
            ('default_instance', '=', True)
        ], limit=1)

        if not whatsapp_instance:
            raise Exception("No hay instancia WhatsApp Meta activa o predeterminada")

        components = []

        if variables:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": str(v)} for v in variables]
            })

        if button_url:
            components.append({
                "type": "button",
                "sub_type": "URL",
                "index": 0,
                "parameters": [{"type": "text", "text": button_url}]
            })

        payload = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components
            }
        }

        try:
            response = requests.post(
                f"https://graph.facebook.com/v22.0/{whatsapp_instance.whatsapp_meta_phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {whatsapp_instance.whatsapp_meta_api_token}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return {"success": True, "data": response.json()}

        except requests.exceptions.RequestException as e:
            error = e.response.text if e.response else str(e)
            _logger.error(f"Error WhatsApp Meta: {error}")
            return {"success": False, "error": error}