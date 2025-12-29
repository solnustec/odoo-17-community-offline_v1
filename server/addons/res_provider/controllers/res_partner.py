# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request, Response


class ResProvider(http.Controller):
    @http.route('/api/provider/info', auth='public', method=['POST'], csrf=False)
    def save_provider_data_from_vf(self, **kw):
        datas = json.loads(request.httprequest.data.decode('utf-8')).get('data')

        for data in datas:

            provider_id = data.get('id').lstrip('0')
            provider = request.env['res.partner'].sudo().search([('id_database_old_provider', '=', provider_id), ('supplier_rank', '=', 1)], limit=1)
            print(provider,'provider')
            print(provider,'provider')
            #TODO revisar el guardado el json
            if not provider:
                request.env['res.partner'].sudo().create({
                    'name': data.get('name'),
                    'id_database_old_provider': provider_id,
                    'supplier_rank': 1,
                    'street': data.get('address'),
                    'email': data.get('email'),
                    'phone': data.get('phone'),
                    'mobile': data.get('mobile'),
                    'city': data.get('city'),
                    'country_id': 63,
                    'provider_config': data
                })
            else:
                print('provider',data)

                provider.sudo().write({
                    'supplier_rank': 1,
                    'provider_config': data
                })
        # provider.write({'provider_config': data})
            return Response(json.dumps({
                'success': True,
                'message': f'Proveedor(es) guardado(s) correctamente: {provider_id}',
                'data': {}
            }), status=201, mimetype='application/json')
