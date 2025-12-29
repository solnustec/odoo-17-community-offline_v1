# -*- coding: utf-8 -*-
from odoo import models, fields, api
import pytz
from datetime import datetime


# Timezone configurada para Ecuador
CHATBOT_TIMEZONE = 'America/Guayaquil'


def get_local_datetime():
    """
    Obtiene la fecha y hora actual en la zona horaria de Ecuador.
    Retorna un tuple (date, time_str) con la fecha y hora local.

    Nota: NO se debe restar horas adicionales después de convertir a timezone local,
    ya que astimezone() ya realiza la conversión correctamente.
    """
    tz = pytz.timezone(CHATBOT_TIMEZONE)
    # Obtener hora UTC actual con timezone aware
    now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
    # Convertir a timezone local
    now_local = now_utc.astimezone(tz)
    return now_local.date(), now_local.strftime('%H:%M:%S')


class UserCity(models.Model):
    _name = 'chatbot_message.city'
    _description = 'User City'

    user_id = fields.Char(string='Identificador de usuario', required=False)
    latitude = fields.Float(string='Latitud', required=False)
    longitude = fields.Float(string='Longitud', required=False)
    city_name = fields.Char(string='Nombre de la ciudad', required=False)
    pharmacy_name = fields.Char(string='Farmacia cercana', required=False)
    pharmacy_type = fields.Char(string='Farmacia turno/24 horas', required=False)
    create_date = fields.Date(string='Fecha de creación', required=False)
    create_time = fields.Char(string='Hora de creación', required=False)

    @api.model_create_multi
    def create(self, vals_list):
        local_date, local_time = get_local_datetime()
        for vals in vals_list:
            vals['create_date'] = local_date
            vals['create_time'] = local_time
        return super().create(vals_list)


class UserLocation(models.Model):
    _name = 'chatbot_message.location'
    _description = 'User Location'

    user_id = fields.Char(string='Identificador de usuario', required=False)
    latitude = fields.Float(string='Latitud', required=False)
    longitude = fields.Float(string='Longitud', required=False)
    city_name = fields.Char(string='Nombre de la ciudad', required=False)
    pharmacy_name = fields.Char(string='Farmacia cercana', required=False)
    create_date = fields.Date(string='Fecha de creación', required=False)
    create_time = fields.Char(string='Hora de creación', required=False)

    @api.model_create_multi
    def create(self, vals_list):
        local_date, local_time = get_local_datetime()
        for vals in vals_list:
            vals['create_date'] = local_date
            vals['create_time'] = local_time
        return super().create(vals_list)


class UserProduct(models.Model):
    _name = 'chatbot_message.product'
    _description = 'User Product'

    user_id = fields.Char(string='Identificador de usuario', required=False)
    product_name = fields.Char(string='Nombre del producto', required=False)
    create_date = fields.Date(string='Fecha de creación', required=False)
    create_time = fields.Char(string='Hora de creación', required=False)

    @api.model_create_multi
    def create(self, vals_list):
        local_date, local_time = get_local_datetime()
        for vals in vals_list:
            vals['create_date'] = local_date
            vals['create_time'] = local_time
        return super().create(vals_list)


class ChatbotInteraction(models.Model):
    _name = 'chatbot_message.interaction'
    _description = 'Interacciones del Chatbot con el Usuario'

    menu_selection = fields.Char(string='Menu de Selección', required=False)
    create_date = fields.Date(string='Fecha de creación', required=False)
    quantity = fields.Integer(string='Cantidad', default=1)
    create_time = fields.Char(string='Hora de creación', required=False)

    @api.model_create_multi
    def create(self, vals_list):
        local_date, local_time = get_local_datetime()
        for vals in vals_list:
            vals['create_date'] = local_date
            vals['create_time'] = local_time
        return super().create(vals_list)


class ShippingPriceLog(models.Model):
    _name = 'chatbot_message.delivery'
    _description = 'Shipping Price Record'

    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta')
    user_id = fields.Char(string='Identificador de usuario', required=False)
    gps_address_link = fields.Char(string='Enlace GPS')
    province = fields.Char(string='Provincia')
    city = fields.Char(string='Ciudad')
    main_street = fields.Char(string='Dirección')
    shipping_price = fields.Float(string='Precio envío')
    distance_km = fields.Float(string='Distancia (KM)')
    type_delivery = fields.Char(string='Tipo de servicio')
    create_date = fields.Date(string='Fecha de creación', required=False)
    create_time = fields.Char(string='Hora de creación', required=False)

    @api.model_create_multi
    def create(self, vals_list):
        local_date, local_time = get_local_datetime()
        for vals in vals_list:
            vals['create_date'] = local_date
            vals['create_time'] = local_time
        return super().create(vals_list)
