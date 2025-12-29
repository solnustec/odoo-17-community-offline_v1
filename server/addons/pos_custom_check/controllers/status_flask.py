# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request

class SincronizacionFlaskAPI(http.Controller):

    @http.route('/api/sincronizacion_flask', type='http', auth='public', methods=['GET'], csrf=False)
    def get_sincronizacion_flask(self, **kwargs):
        icp = request.env['ir.config_parameter'].sudo()
        value = icp.get_param('sincronizacion_flask', default='')

        body = json.dumps({
            "key": "sincronizacion_flask",
            "value": value,
        })

        return request.make_response(
            body,
            headers=[('Content-Type', 'application/json')],
            status=200
        )
