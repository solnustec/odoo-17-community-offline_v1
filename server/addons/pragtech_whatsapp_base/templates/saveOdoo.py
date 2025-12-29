from odoo.http import request
from .getBranch import GetBranch
from odoo.http import request
from odoo import fields
import datetime
import pytz


class SaveOdoo:

    # Guardar informacion de farmacia turno/24 horas
    @staticmethod
    def save_duty_to_odoo(number, latitude, longitude, closest_company, pharmacy_type):
        """Guarda la ubicación del usuario directamente en Odoo."""
        city_name = GetBranch.get_city_from_coordinates(latitude, longitude)

        try:
            request.env['chatbot_message.city'].sudo().create({
                'user_id': number,
                'latitude': latitude,
                'longitude': longitude,
                'city_name': city_name,
                'pharmacy_name': closest_company,
                'pharmacy_type': pharmacy_type
            })

        except Exception as e:
            print(f"Error al guardar en Odoo: {e}")

    # Guardar informacion de sucursal mas cercana
    @staticmethod
    def save_location_to_odoo(number, latitude, longitude, closest_company):
        """Guarda la ubicación del usuario directamente en Odoo."""
        city_name = GetBranch.get_city_from_coordinates(latitude, longitude)
        try:
            request.env['chatbot_message.location'].sudo().create({
                'user_id': number,
                'latitude': latitude,
                'longitude': longitude,
                'city_name': city_name,
                'pharmacy_name': closest_company
            })
        except Exception as e:
            print(f"Error al guardar en Odoo: {e}")

    # Guardar interaccion odoo
    @classmethod
    def save_interacction(cls, menu_selection):
        """Guarda la selección del usuario en Odoo en el modelo chatbot_message.interaction."""
        try:
            interaction = request.env['chatbot_message.interaction'].sudo().search([
                ('menu_selection', '=', menu_selection)
            ], limit=1)

            if interaction:
                interaction.sudo().write({'quantity': interaction.quantity + 1})
            else:
                request.env['chatbot_message.interaction'].sudo().create({
                    'menu_selection': menu_selection,
                    'quantity': 1,
                })

        except Exception as e:
            print(f"⚠️ Error al guardar la interacción: {e}")

    @classmethod
    def save_product_to_odoo(cls, number, product_name):
        """Guarda el producto seleccionado por el usuario en Odoo."""
        try:
            request.env['chatbot_message.product'].sudo().create({
                'user_id': number,
                'product_name': product_name,
            })
        except Exception as e:
            print(f"Error al guardar el producto en Odoo: {e}")

    # Guardar mensajes del bot en odoo
    @classmethod
    def save_bot_message(cls, chat_id, message_body):
        """
        Guarda los messages enviados por el bot en el modelo whatsapp.messages.
        """
        whatsapp_instance = request.env['whatsapp.instance'].sudo().search([
            ('status', '!=', 'disable'),
            ('provider', '=', 'meta'),
            ('default_instance', '=', True)
        ], limit=1)

        num_chatbot = request.env['ir.config_parameter'].sudo().get_param('numero_chatbot')
        bot_number = whatsapp_instance.gupshup_source_number if whatsapp_instance else num_chatbot

        whatsapp_message = request.env['whatsapp.messages'].sudo().search(
            [('chatId', '=', chat_id), ('partner_id', '!=', False)], limit=1
        )
        user_tz = pytz.timezone('America/Guayaquil')
        now_utc = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(user_tz)

        message_data = {
            'name': message_body,
            'message_body': message_body,
            'message_id': bot_number,
            'chatId': chat_id,
            'state': 'sent',
            'partner_id': whatsapp_message[0].partner_id.id if whatsapp_message else False,
            'fromMe': True,
            'type': 'text',
            'senderName': 'Chatbot',
            'time': now_local.strftime('%Y-%m-%d %H:%M:%S'),
        }
        request.env['whatsapp.messages'].sudo().create(message_data)

    # Guardar información de envío
    @classmethod
    def save_shipping_price_log(cls, order_id, user_id, gps_address_link, province, city, main_street, shipping_price,
                                distance_km, type_delivery=None):
        """
        Guarda el precio del envío y actualiza el tipo de entrega en la orden.
        """
        try:
            # Guardar log
            request.env['chatbot_message.delivery'].sudo().create({
                'sale_order_id': order_id,
                'user_id': user_id,
                'gps_address_link': gps_address_link,
                'province': province,
                'city': city,
                'main_street': main_street,
                'shipping_price': shipping_price,
                'distance_km': distance_km,
                'type_delivery': type_delivery
            })

            # Actualizar tipo de entrega en la orden
            if order_id and type_delivery:
                order = request.env['sale.order'].sudo().browse(order_id)
                if order.exists():
                    order.write({'type_delivery': type_delivery})
        except Exception as e:
            print(f"Error al guardar el log de envío o actualizar la orden: {e}")
