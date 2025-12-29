# -*- coding: utf-8 -*-
from .api_security import validate_api_static_token
from odoo import http

from odoo.http import request, Response
import json

class PharmacyWebController(http.Controller):
    @http.route("/api/store/pharmacies_on_duty/<city_name>", type="http", auth="public",
                methods=["GET"], csrf=False, cors="*")
    @validate_api_static_token
    def get_pharmacies_on_duty(self, city_name):

        try:
            if not city_name:
                return Response(
                    json.dumps({
                        "status": "error",
                        "message": "City name is required."
                    }),
                    content_type='application/json', status=400)

            pharmacies = request.env["res.company"].sudo().search([
                ('city', '=ilike', city_name),
                # ('x_turno', '=', True)
            ])

            pharmacy_data = [{
                "id": pharmacy.id,
                "name": pharmacy.name,
                "latitude": pharmacy.x_lat,
                "longitude": pharmacy.x_long,
            } for pharmacy in pharmacies]

            return Response(
                json.dumps({"status": "success", "pharmacies": pharmacy_data or []}),
                content_type='application/json', status=200,
            )

        except Exception as e:
            response_data = {
                "status": "error",
                "message": "An unexpected error occurred."
            }
            # Incluir detalles en modo debug
            if request.env.context.get("debug"):
                response_data["details"] = str(e)

            return Response(
                json.dumps(response_data),
                content_type='application/json', status=500

            )
