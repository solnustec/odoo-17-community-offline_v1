# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request, Response
import json

class WarehouseCityAPI(http.Controller):

    @http.route("/api/warehouses/cities", type="http", auth="public", csrf=False, methods=["GET"])
    def all_cities(self, **params):
        """
        Devuelve todas las ciudades únicas registradas en los almacenes.
        Ejemplo: GET /api/warehouses/cities
        """
        rows = request.env["stock.warehouse"].sudo().read_group(
            domain=[("city", "!=", False)],
            fields=["city"],
            groupby=["city"],
            lazy=False,
        )

        # Normaliza y ordena
        cities = sorted([r["city"] for r in rows if r.get("city")], key=lambda s: s.lower())

        data = {
            "status": "ok",
            "count": len(cities),
            "results": [{"name": c} for c in cities],
        }
        return Response(json.dumps(data, ensure_ascii=False), content_type="application/json", status=200)
