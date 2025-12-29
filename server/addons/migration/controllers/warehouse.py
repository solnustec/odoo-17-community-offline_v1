import json

from odoo import http
from odoo.http import request, Response


class Warehouses(http.Controller):
    """
    Api para sincronizar almacenes desde el otro sistema a Odoo
    1. Crear nuevas bodegas si no existen
    2. Actualizar bodegas existentes basadas en external_id
    3. Ignorar entradas con datos incompletos
    4. Responder con estado de éxito o error
    id,name,address,lat,longi,province,city

    """

    @http.route('/api/sync/warehouses', type='http', auth='public',
                methods=['POST'], csrf=False)
    def save_warehouses(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        w = data.get('data', [])
        if not w:
            return Response(
                json.dumps({
                    'status': 'error',
                    'message': 'Datos incompletos: external_id y name son requeridos.'
                })
            )
        external_id = w[0].get('id').lstrip('0')  # Eliminar ceros a la izquierda
        name = w[0].get('name')
        address = w[0].get('address')
        lat = w[0].get('lat')
        longi = w[0].get('longi')
        province = w[0].get('province')
        city = w[0].get('city')

        if not external_id or not name:
            request.env['sales.summary.error'].sudo().create({
                'error_details': f'Datos incompletos para bodega: {w}',
            })
            return Response(
                json.dumps({
                    'status': 'error',
                    'message': 'Datos incompletos: external_id y name son requeridos.'
                }), status=404, content_type='application/json',
            )

        # Buscar bodega por external_id
        warehouse = request.env['stock.warehouse'].sudo().search(
            [('external_id', '=', external_id)], limit=1)
        state_id = self.get_city(province)

        if warehouse:
            # Actualizar bodega existente
            warehouse.sudo().write({
                # 'name': name,
                # 'code': name[:4],
                'country_id': 63,
                'street': address,
                'city': city,
                'state_id': state_id.id if state_id else 1413,
                'x_lat': lat,
                'x_long': longi,
            })
            return Response(
                json.dumps({
                    'status': 'success',
                    'message': f'Bodega {name} actualizada correctamente.'
                }),
                status=201,
                content_type='application/json'
            )
        else:
            # Crear nueva bodega
            request.env['stock.warehouse'].sudo().create({
                'name': name,
                'code': name[4:],
                'external_id': external_id,
                'country_id': 63,
                'street': address,
                'city': city,
                'state_id': state_id.id if state_id else 1413,
                'x_lat': lat,
                'x_long': longi,
                "company_id": 1,
                "sequence": 10,
            })
            return Response(
                json.dumps({
                    'status': 'success',
                    'message': f'Bodega {name} creada correctamente.'
                }),
                status=201,
                content_type='application/json'
            )

    @classmethod
    def get_city(cls, province):

        # city_name = ciudad_a_provincia.get(city.strip().upper())

        city_id = request.env['res.country.state'].sudo().search(
            [('name', 'ilike', province.strip().upper()), ('country_id', '=', 'Ecuador')], limit=1)
        print(city_id)
        return city_id
