import requests
from odoo import models

from .dutyPharmacy_flow import DutyPharmacy
from .getBranch import GetBranch
from .saveOdoo import SaveOdoo
from ..templates.meta_api import MetaAPi
from ..utils.user_session import UserSession
from odoo.http import request


class BranchFlow:

    @classmethod
    def handle_location_input(self, numero, latitude, longitude):
        """Procesa la ubicación del usuario, encuentra la sucursal más cercana y guarda la ubicación en Odoo."""
        user_session = UserSession(request.env)
        session = user_session.get_session(numero)
        try:
            companies = GetBranch.get_companies_with_coordinates()

            if not companies:
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('branch_hello') or "No hay sucursales disponibles en este momento"
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                MetaAPi.enviar_mensaje_con_botones_salida(numero)
                return

            latitude = DutyPharmacy.safe_float(latitude)
            longitude = DutyPharmacy.safe_float(longitude)

            # Filtrar solo compañías con coordenadas válidas
            valid_companies = [
                company for company in companies
                if DutyPharmacy.safe_float(company.get("x_lat")) is not None
                   and DutyPharmacy.safe_float(company.get("x_long")) is not None
            ]

            if not valid_companies:
                mensaje = request.env['whatsapp_messages_user'].sudo().get_message('branch_hello') or \
                          "No hay sucursales con coordenadas válidas en este momento."
                MetaAPi.enviar_mensaje_texto(numero, mensaje)
                MetaAPi.enviar_mensaje_con_botones_salida(numero)
                return

            # Buscar la más cercana
            closest_company = min(
                valid_companies,
                key=lambda company: GetBranch.calculate_distance(
                    latitude, longitude,
                    DutyPharmacy.safe_float(company["x_lat"]),
                    DutyPharmacy.safe_float(company["x_long"])
                ),
            )

            google_maps_link = GetBranch.generate_google_maps_link(
                closest_company["x_lat"], closest_company["x_long"]
            )

            message = (
                "La *sucursal más cercana* desde tu posición actual es:\n\n"
                f"Nombre: {closest_company['name']}\n"
                f"Dirección: {closest_company['street']} {closest_company.get('street2', '')}\n"
                f"Distancia: {GetBranch.calculate_distance(latitude, longitude, closest_company['x_lat'], closest_company['x_long']):.2f} km\n"
                f"Ciudad: {closest_company['city']}\n\n"
                f"🔗 *Cómo llegar:* {google_maps_link}"
            )

            MetaAPi.enviar_mensaje_texto(numero, message)
            UserSession(request.env).update_session(numero, state="manejar_salida")
            MetaAPi.enviar_mensaje_con_botones_salida(numero)

            # Guardar la ubicación en Odoo
            SaveOdoo.save_location_to_odoo(numero, latitude, longitude, closest_company['name'])

        except Exception as e:
            print(f"Error al procesar la ubicación: {e}")
            mensaje_error = request.env['whatsapp_messages_user'].sudo().get_message('branch_error') or "❌ Ha ocurrido un error. Intenta nuevamente."
            MetaAPi.enviar_mensaje_texto(numero, mensaje_error)
            MetaAPi.enviar_mensaje_con_botones_salida(numero)

    @staticmethod
    def solicitar_ubicacion(numero, mensaje=None):
        """Solicita al usuario que envíe su ubicación en WhatsApp."""
        mensaje = request.env['whatsapp_messages_user'].sudo().get_message('branch_location')
        # image_url = "https://i.postimg.cc/VNLNMbCd/Whats-App-Image-2025-04-11-at-17-25-04.jpg"

        try:
            MetaAPi.enviar_mensaje_texto(numero, mensaje)
            # resultado = MetaAPi.enviar_imagen_desde_url(numero, image_url)
            # if not resultado:
            #     MetaAPi.enviar_mensaje_texto(numero, "No se pudo enviar la guía visual.")
            # else:
            #     print("Imagen enviada exitosamente según la API")
            # return resultado
        except Exception as e:
            print(f"Error en solicitar_ubicacion: {str(e)}")
            mensaje_error = request.env['whatsapp_messages_user'].sudo().get_message('branch_general_error')
            MetaAPi.enviar_mensaje_texto(numero, mensaje_error)
            return False