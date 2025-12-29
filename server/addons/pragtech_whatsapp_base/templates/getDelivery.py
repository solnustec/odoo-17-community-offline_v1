from odoo.http import request, Response
import googlemaps

import logging
import unicodedata

_logger = logging.getLogger(__name__)
class GetDelivery:

    @classmethod
    def get_all_shipping_methods(cls):
        carriers = request.env["delivery.carrier"].sudo().search([])
        shipping_methods = []

        def eliminar_tildes(texto):
            texto_normalizado = unicodedata.normalize('NFKD', texto)
            texto_sin_tildes = ''.join(c for c in texto_normalizado if not unicodedata.combining(c))
            return texto_sin_tildes.lower()

        for carrier in carriers:
            shipping_methods.append({
                "carrier_id": carrier.id,
                "carrier_name": eliminar_tildes(carrier.name),
                "fixed_price": carrier.fixed_price,
                "product_id": carrier.product_id.id,
            })
        return shipping_methods

    @classmethod
    def calculate_distance(cls, coords):
        try:
            # Obtener la API Key desde la configuración
            googlemaps_token = request.env['ir.config_parameter'].sudo().get_param('googlemaps_token')
            if not googlemaps_token:
                raise ValueError("API key de Google Maps no configurada.")

            # Inicializar cliente de Google Maps
            gmaps = googlemaps.Client(key=googlemaps_token)

            origen = f"{coords[0]},{coords[1]}"
            destino = f"{coords[2]},{coords[3]}"

            # Llamada a la API Distance Matrix
            resultado = gmaps.distance_matrix(
                origins=origen,
                destinations=destino,
                mode='driving',
                units='metric',
                language='es'
            )

            elementos = resultado['rows'][0]['elements'][0]
            status_api = elementos.get('status')

            if status_api == 'OK':
                distancia_metros = elementos['distance']['value']
                distancia_km = distancia_metros / 1000
                return distancia_km
            elif status_api == 'REQUEST_DENIED':
                _logger.error(
                    "Google Maps API: acceso denegado. Verifica que tengas habilitada la 'Routes API' en tu proyecto.")
            else:
                _logger.warning(f"Google Maps API devolvió estado no esperado: {status_api}")
            return None

        except Exception as e:
            _logger.error(f"Error al calcular distancia: {e}")
            return None