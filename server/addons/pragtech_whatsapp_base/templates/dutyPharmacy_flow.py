import requests

from .getBranch import GetBranch
from .saveOdoo import SaveOdoo
from ..templates.meta_api import MetaAPi
from ..utils.user_session import UserSession
from odoo.http import request


class DutyPharmacy:

    @staticmethod
    def safe_float(val):
        try:
            return float(str(val).replace(',', '.'))
        except (ValueError, TypeError) as e:
            print(f"[safe_float] Error al convertir '{val}' a float: {e}")
            return None

    def is_true(val):
        return str(val).strip().lower() in ["true", "1", "si", "sí"]

    @classmethod
    def handle_duty_pharmacy(self, numero, latitude, longitude):
        """Procesa la ubicación del usuario y encuentra la farmacia de turno más cercana."""

        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        try:
            pharmacies = GetBranch.get_companies_with_coordinates()

            # Filtrar farmacias disponibles: de turno o 24 horas
            pharmacies = [
                p for p in pharmacies
                if DutyPharmacy.is_true(p.get("x_24hours")) or DutyPharmacy.is_true(p.get("x_turno"))
            ]

            if not pharmacies:
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message(
                    'pharmacy_hello') or "No hay farmacias de turno o 24 horas disponibles en este momento."
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                MetaAPi.enviar_mensaje_con_botones_salida(numero)
                return

            latitude = DutyPharmacy.safe_float(latitude)
            longitude = DutyPharmacy.safe_float(longitude)

            closest_pharmacy = min(
                pharmacies,
                key=lambda pharmacy: GetBranch.calculate_distance(
                    latitude, longitude,
                    pharmacy["x_lat"], pharmacy["x_long"]
                ),
            )

            google_maps_link = GetBranch.generate_google_maps_link(
                closest_pharmacy["x_lat"], closest_pharmacy["x_long"]
            )

            if DutyPharmacy.is_true(closest_pharmacy.get("x_24hours")):
                pharmacy_type = "24 horas"
            elif DutyPharmacy.is_true(closest_pharmacy.get("x_turno")):
                pharmacy_type = "de turno"
            else:
                pharmacy_type = "no disponible"

            message = (
                f"*Farmacia {pharmacy_type}* más cercana desde tu ubicación es:\n\n"
                f"Nombre: {closest_pharmacy['name']}\n"
                f"Dirección: {closest_pharmacy['street']} {closest_pharmacy.get('street2', '')}\n"
                f"Distancia: {GetBranch.calculate_distance(latitude, longitude, closest_pharmacy['x_lat'], closest_pharmacy['x_long']):.2f} km\n"
                f"Ciudad: {closest_pharmacy['city']}\n"
                f"Tipo: Farmacia {pharmacy_type}\n"
                f"\n🔗 *Cómo llegar:* {google_maps_link}"
            )

            MetaAPi.enviar_mensaje_texto(numero, message)
            UserSession(request.env).update_session(numero, state="manejar_salida")
            MetaAPi.enviar_mensaje_con_botones_salida(numero)
            SaveOdoo.save_duty_to_odoo(numero, latitude, longitude, closest_pharmacy['name'], pharmacy_type)

        except Exception as e:
            print(f"Error al procesar la ubicación: {e}")
            mensaje_error = request.env['whatsapp_messages_user'].sudo().get_message(
                'pharmacy_error') or "Ha ocurrido un error al procesar tu ubicación. Intenta nuevamente."
            MetaAPi.enviar_mensaje_texto(numero, mensaje_error)
            MetaAPi.enviar_mensaje_con_botones_salida(numero)

    @staticmethod
    def farmacia_turno(numero, mensaje=None):
        try:
            mensaje = request.env['whatsapp_messages_user'].sudo().get_message('pharmacy_location')

            MetaAPi.enviar_mensaje_texto(numero, mensaje)
            # image_url = "https://i.postimg.cc/VNLNMbCd/Whats-App-Image-2025-04-11-at-17-25-04.jpg"
            # reultado = MetaAPi.enviar_imagen_desde_url(numero, image_url)
            # if not reultado:
            #     mensaje_error = request.env['whatsapp_messages_user'].sudo().get_message('pharmacy_image_error') or "No se pudo enviar la guía visual."
            #     MetaAPi.enviar_mensaje_texto(numero, mensaje_error)
        except Exception as e:
            print(f"Error en solicitar_ubicacion: {str(e)}")
            mensaje_error = request.env['whatsapp_messages_user'].sudo().get_message(
                'pharmacy_general_error') or "Ocurrio un error."
            MetaAPi.enviar_mensaje_texto(numero, mensaje_error)
