import base64

from .api_security import validate_api_static_token
from odoo import http
from odoo.http import request, Response
import json

from ..utils.time_cache import APICache


class BannerController(http.Controller):
    api_cache = APICache(timeout=86400, max_size=1000)

    @http.route('/api/store/warehouses', type='http',
                auth='public', methods=['POST'], csrf=False, cors='*')
    @validate_api_static_token
    @api_cache.cache()
    def get_companies_by_state(self, **kw):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            city_id = data.get('city_id')
            # if not city_id:
            #     warehouses = request.env["stock.warehouse"].sudo().search([])

            state_id = request.env['res.country.state'].sudo().browse(
                int(city_id))
            if not state_id.exists():
                return Response(
                    json.dumps(
                        {"status": "error", "message": "State not found",
                         "data": []}),
                    content_type='application/json', status=404)

            # Obtener todas las compañías
            warehouses = request.env["stock.warehouse"].sudo().search([
                ('company_id', '=', 1),
                ('x_long', '!=', False),
                ('x_lat', '!=', False),
                ('state_id', '=', state_id.id),
                ('is_public', '=', True)
            ])
            # Construir la respuesta con la información de las compañías encontradas
            warehouse_data = []
            for warehouse in warehouses:
                warehouse_info = {
                    "id": warehouse.id,
                    "name": f"Sucursal {warehouse.name}",
                    "street": warehouse.street,
                    "street2": warehouse.street2,
                    "city": warehouse.city or "",
                    "state": warehouse.state_id.name if warehouse.state_id else "",
                    "zip": warehouse.zip,
                    "country": warehouse.country_id.name if warehouse.country_id else "",
                    "x_latitud": warehouse.x_lat,
                    "x_longitud": warehouse.x_long,
                    "x_turno": warehouse.x_turno,
                    "x_24hours": warehouse.x_24hours,
                    "mobile": warehouse.mobile or "",
                    "phone": warehouse.phone or "",
                }
                warehouse_data.append(warehouse_info)

            # Devolver la respuesta con formato JSON
            return Response(
                json.dumps({"status": "success", "message": "Warehouses found",
                            "data": warehouse_data}),
                content_type='application/json', status=200)
        except Exception as e:
            return Response(json.dumps(
                {"status": "error", "message": "Internal Server Error",
                 "details": e}), content_type='application/json',
                status=500)
