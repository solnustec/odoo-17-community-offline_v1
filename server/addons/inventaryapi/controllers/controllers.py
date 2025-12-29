from odoo import http
from odoo.http import request

import json


class ProductQuantityController(http.Controller):
    @http.route("/api/product_quantity", auth="public", type="http", methods=["GET"])
    def get_product_quantity(self, **kw):
        product_name_search = kw.get("product_name", "")
        category_id_46 = 40  # ID de la categoría "Promociones"

        # Buscar las plantillas de productos que contengan el nombre proporcionado
        # y que pertenezcan a la categoría con ID 46
        product_templates = (
            request.env["product.template"]
            .sudo()
            .search([
                ("name", "ilike", product_name_search),
                ("categ_id", "=", category_id_46)  # Filtro por categoría
            ])
        )

        # Verificar si se encontraron plantillas de productos
        if product_templates:
            # Construir una lista de productos con su información
            products_data = []
            for product_template in product_templates:
                product_name = product_template.name
                product_price = product_template.list_price

                # Obtener la cantidad en stock de la primera variante del producto (si existe)
                product = (
                    request.env["product.product"]
                    .sudo()
                    .search([
                        ("product_tmpl_id", "=", product_template.id),
                        ("qty_available", ">", 0)  # Filtro de cantidad mayor a 0
                    ], limit=1)
                )
                quantity = product.qty_available if product else "Not available"

                # Agregar la información del producto a la lista, incluyendo el ID de product.product
                if product:
                    products_data.append(
                        {
                            "product_id": product.id,  # ID de la variante del producto
                            "name": product_name,
                            "price": product_price,
                            "quantity": product.qty_available,  # Cantidad disponible
                            "is_published": True,
                            "category_name": product.categ_id.name,
                            # Nombre de la categoría
                        }
                    )

            # Si hay productos con cantidad > 0, retornar la respuesta
            if products_data:
                response_data = {"status": "success", "products": products_data}
            else:
                # Si no hay productos disponibles con cantidad > 0
                response_data = {
                    "status": "error",
                    "message": f"No products with quantity > 0 found for '{product_name_search}' in category ID 46",
                }

            return request.make_response(
                json.dumps(response_data),
                headers=[("Content-Type", "application/json")],
            )
        else:
            # Construir la respuesta de error JSON
            response_data = {
                "status": "error",
                "message": f"No products found containing '{product_name_search}' in category ID 46",
            }

            # Retornar la respuesta de error JSON
            return request.make_response(
                json.dumps(response_data),
                headers=[("Content-Type", "application/json")],
            )


class CompanyController(http.Controller):
    @http.route("/api/company_by_city", type="http", auth="public", methods=["GET"])
    def get_companies_by_city(self, **kw):

        city_name = kw.get("city_name", "")

        # Obtener todas las compañías
        companies = request.env["res.company"].sudo().search([])

        # Filtrar compañías por ciudad usando Python si city_name no está vacío
        if city_name:
            filtered_companies = companies.filtered(
                lambda c: c.city and c.city.lower() == city_name.lower()
            )
        else:
            filtered_companies = companies
        # Construir la respuesta con la información de las compañías encontradas
        company_data = []
        if filtered_companies:
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
                    "x_latitud": company.x_latitud,
                    "x_longitud": company.x_longitud,
                    "x_sector": company.x_sector
                }
                company_data.append(company_info)

            return json.dumps({"status": "success", "companies": company_data})
        else:
            return json.dumps({"status": "error", "message": "No companies found"})


class PurchaseOrderController(http.Controller):
    @http.route('/api/endpoint', type='json', auth='public', methods=['POST'],
                csrf=False)
    def create_purchase_order(self, **kwargs):
        data = request.jsonrequest
        amount_total = data.get('fields', {}).get('amount_total')
        order_lines = data.get('fields', {}).get('order_line', [])
        user_id = data.get('user_id')
        if amount_total and order_lines:
            order = request.env['purchase.order'].sudo().create({
                'amount_total': amount_total,
                'order_line': [(0, 0, {'product_id': line['product_id']}) for line in
                               order_lines],
                'partner_id': user_id
                # Asociar la orden con un cliente (si es necesario)
            })
            return {'status': 'success', 'order_id': order.id}
        else:
            return {'status': 'error', 'message': 'Datos faltantes en la solicitud'}



class PharmacyOnDutyController(http.Controller):

    @http.route("/api/pharmacy_on_duty_by_city", type="http", auth="public",
                methods=["GET"])
    def get_pharmacies_on_duty_by_city(self, **kw):
        city_name = kw.get("city_name", "").strip()

        # Buscar las compañías que tienen 'description' en True (farmacias de turno)
        companies = request.env["res.company"].sudo().search(
            [('description', '=', True)])

        # Filtrar compañías por ciudad si se proporciona city_name
        if city_name:
            companies = companies.filtered(
                lambda c: c.city and c.city.lower() == city_name.lower())

        # Si se encuentran compañías, construir la respuesta con la información
        company_data = []
        for company in companies:
            company_info = {
                "name": company.name,
                "street": company.street,
                "city": company.city or "",
            }
            company_data.append(company_info)

        if company_data:
            return request.make_response(
                json.dumps({"status": "success", "pharmacies_on_duty": company_data}),
                headers=[("Content-Type", "application/json")],
            )
        else:
            # Si no se encuentran farmacias de turno en esa ciudad
            return request.make_response(
                json.dumps({"status": "error",
                            "message": "No pharmacies on duty found in the specified city"}),
                headers=[("Content-Type", "application/json")],
            )

class DeliveryController(http.Controller):

    @http.route("/api/fixed_price_by_province", type="http", auth="public", methods=["GET"])
    def get_fixed_price_by_province(self, **kw):
        # Obtener el nombre de la provincia desde los parámetros de la URL
        province_name = kw.get("province_name", "")

        # Verificar que se haya proporcionado un nombre de provincia
        if not province_name:
            return json.dumps({"status": "error", "message": "Province name is required"})

        # Buscar la provincia en el modelo res.country.state
        province = request.env["res.country.state"].sudo().search([("name", "ilike", province_name)], limit=1)

        if not province:
            return json.dumps({"status": "error", "message": "Province not found"})

        # Buscar transportistas (delivery.carrier) que tienen esta provincia en el campo state_ids
        carriers = request.env["delivery.carrier"].sudo().search([("state_ids", "in", province.id)])

        if not carriers:
            return json.dumps({"status": "error", "message": "No carriers found for this province"})

        # Construir la respuesta con los datos de los transportistas y sus precios fijos
        carrier_data = []
        for carrier in carriers:
            carrier_info = {
                "carrier_id": carrier.id,
                "carrier_name": carrier.name,
                "fixed_price": carrier.fixed_price
            }
            carrier_data.append(carrier_info)

        return json.dumps({"status": "success", "carriers": carrier_data})


