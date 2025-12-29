from odoo import http
from odoo.http import request, Response
import json
import logging

_logger = logging.getLogger(__name__)


class CompanyWebController(http.Controller):
    @http.route("/api/company_by_state", type="http", auth="public", methods=["GET"],
                csrf=False)
    def get_companies_by_state(self, **kw):
        try:
            state_name = kw.get("state_name", "")

            # Obtener todas las compañías
            companies = request.env["stock.warehouse"].sudo().search(
                [('is_public', '=', True)],
                order='name asc'
            )

            # Filtrar compañías por estado usando Python si state_name no está vacío
            if state_name:
                filtered_companies = companies.filtered(
                    lambda
                        c: c.state_id and c.state_id.name.lower() == state_name.lower()
                )
            else:
                filtered_companies = companies

            # Construir la respuesta con la información de las compañías encontradas
            company_data = []
            for company in filtered_companies:
                company_info = {
                    "id": company.id,
                    "name": company.name,
                    "street": company.street,
                    "street2": company.street2,
                    "city": company.city or "",
                    "state": company.state_id.name if company.state_id else "",
                    "zip": company.zip,
                    "country": company.country_id.name if company.country_id else "",
                    "x_latitud": company.x_lat,
                    "x_longitud": company.x_long,
                    "mobile": company.mobile or "",
                    "phone": company.phone or "",
                }
                company_data.append(company_info)

            # Devolver la respuesta con formato JSON
            return Response(
                json.dumps({"status": "success", "companies": company_data}),
                content_type='application/json', status=200)
        except Exception as e:
            # Registrar el error en el log del servidor Odoo
            error_message = str(e)
            _logger = http.logging.getLogger(__name__)
            _logger.error(
                f"Error en el endpoint /api/company_by_state: {error_message}")

            # Devolver un mensaje de error detallado
            return Response(json.dumps(
                {"status": "error", "message": "Internal Server Error",
                 "details": error_message}), content_type='application/json',
                            status=500)

    @http.route("/api/all_companies", type="http", auth="public", methods=["GET"], csrf=False)
    def get_all_companies(self, **kw):
        try:
            # Obtener todas las compañías sin filtrar
            companies = request.env["stock.warehouse"].sudo().search(
                [('is_public', '=', True)],
                order='name asc'
            )

            # Construir la respuesta
            company_data = []
            for company in companies:
                company_info = {
                    "id": company.id,
                    "name": company.name,
                    "street": company.street,
                    "street2": company.street2,
                    "city": company.city or "",
                    "state": company.state_id.name if company.state_id else "",
                    "zip": company.zip,
                    "country": company.country_id.name if company.country_id else "",
                    "x_latitud": company.x_lat,
                    "x_longitud": company.x_long,
                    "mobile": company.mobile or "",
                    "phone": company.phone or "",
                }
                company_data.append(company_info)

            return Response(
                json.dumps({"status": "success", "companies": company_data}),
                content_type='application/json', status=200)
        except Exception as e:
            request.env.cr.rollback()
            error_message = str(e)
            _logger = http.logging.getLogger(__name__)
            _logger.error(f"Error en el endpoint /api/all_companies: {error_message}")
            return Response(json.dumps(
                {"status": "error", "message": "Internal Server Error",
                 "details": error_message}), content_type='application/json',
                status=500)