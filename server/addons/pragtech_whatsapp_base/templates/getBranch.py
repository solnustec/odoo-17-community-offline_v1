import requests
from math import radians, sin, cos, sqrt, atan2
from odoo.http import request
from shapely.geometry import shape, Point
import json
from pathlib import Path
from shapely.geometry import shape, Point

GEOJSON_PATH = Path(__file__).parent.parent / 'static' / 'src' / 'geo' / 'ec.json'

with open(GEOJSON_PATH, 'r', encoding='utf-8') as geo_file:
    PROVINCIAS_DATA = json.load(geo_file)

def obtener_provincia_por_coordenadas(lat, lon):
    point = Point(lon, lat)
    for feature in PROVINCIAS_DATA.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue

        polygon = shape(geometry)

        if polygon.contains(point):
            return feature.get("properties", {}).get("name")

    return ""


class GetBranch:
    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        """Calcula la distancia en kilómetros entre dos coordenadas geográficas."""
        R = 6371  # Radio de la Tierra en km
        dLat = radians(lat2 - lat1)
        dLon = radians(lon2 - lon1)
        a = sin(dLat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dLon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c


    @classmethod
    def generate_google_maps_link(cls, lat, lon):
        """Genera un enlace de Google Maps para navegar a la sucursal."""
        return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}&travelmode=driving"

    @classmethod
    def get_companies_with_coordinates(cls):
        companies = request.env["stock.warehouse"].sudo().search([]).filtered(lambda c: c.x_lat and c.x_long)
        result = []
        for company in companies:
            try:
                lat = float(str(company.x_lat).replace(',', '.'))
                lon = float(str(company.x_long).replace(',', '.'))
                result.append({
                    "id": company.id,
                    "name": company.name,
                    "street": company.street,
                    "street2": company.street2 or "",
                    "city": company.city or "",
                    "x_lat": lat,
                    "x_long": lon,
                    "x_turno": company.x_turno,
                    "x_24hours": company.x_24hours,
                })
            except Exception as e:
                print(f"[get_companies_with_coordinates] Error con sucursal '{company.name}': {e}")
        return result

    @staticmethod
    def get_city_from_coordinates(latitude, longitude):
        """Obtiene el nombre de la ciudad a partir de coordenadas usando OpenStreetMap (Nominatim)."""
        url = f"https://nominatim.openstreetmap.org/reverse?lat={latitude}&lon={longitude}&format=json&addressdetails=1"
        headers = {
            "User-Agent": "OdooBot/1.0 (your_email@example.com)"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data and "address" in data:
                city = data["address"].get("city") or data["address"].get("town") or data["address"].get("village")
                return city.capitalize() if city else "Ciudad no encontrada"
        except requests.RequestException as e:
            print(f"Error al obtener la ciudad: {e}")
        return "Error en la geocodificación"
