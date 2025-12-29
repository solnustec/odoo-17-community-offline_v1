# Productos tienda
import json

from odoo import http
from odoo.http import Response
from odoo.http import request

import json


class ProductQuantityController(http.Controller):
    @http.route("/api/product_quantity", auth="public", type="http", methods=["GET"])
    def get_product_quantity(self, **kw):
        product_name_search = kw.get("product_name", "")

        try:
            limit = int(kw.get("limit", 5))
            offset = int(kw.get("offset", 0))
        except ValueError:
            return Response(
                json.dumps({"status": "error", "message": "Invalid limit or offset"}),
                status=400,
                content_type="application/json",
            )

        # Se eliminó el filtro de 'is_published' y la referencia a la lista de precios 537
        products = request.env["product.product"].sudo().search(
            [("name", "ilike", product_name_search)],
            limit=limit,
            offset=offset,
        )

        if products:
            product_data = []
            for product in products:
                product_data.append(
                    {
                        "id": product.id,
                        "name": product.name,
                        "qty_available": product.qty_available,
                        "price": product.lst_price,
                    }
                )

            total_products = request.env["product.product"].sudo().search_count(
                [("name", "ilike", product_name_search)]
            )

            response_data = {
                "status": "success",
                "products": product_data,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total_products": total_products,
                    "remaining_products": max(total_products - offset - limit, 0),
                },
            }
            return Response(json.dumps(response_data), status=200, content_type="application/json")

        else:
            return Response(
                json.dumps(
                    {"status": "error", "message": f"No existen productos con el nombre: {product_name_search}"}
                ),
                status=200,
                content_type="application/json",
            )


# Sucursal mas cercana
class CompanyController(http.Controller):
    @http.route("/api/companies_with_coordinates", type="http", auth="public", methods=["GET"])
    def get_companies_with_coordinates(self, **kw):
        # Obtener todas las compañías con latitud y longitud definidas
        companies_with_coordinates = request.env["res.company"].sudo().search([]).filtered(
            lambda c: c.x_lat and c.x_long
        )

        # Construir la respuesta con las compañías encontradas
        company_data = []
        for company in companies_with_coordinates:
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
                "x_turno": company.x_turno,
                "x_24hours": company.x_24hours
            }
            company_data.append(company_info)

        if company_data:
            return json.dumps({"status": "success", "companies": company_data})
        else:
            return json.dumps({"status": "error", "message": "No companies found"})


# Orden de venta con cliente
class PurchaseOrderController(http.Controller):

    @http.route('/api/sale_order/create', type='json', auth='public',
                methods=['POST'],
                csrf=False)
    def create_sale_order(self, **kwargs):
        try:
            # Procesar los datos de la solicitud
            data = json.loads(request.httprequest.data.decode('utf-8'))

            # Extraer datos del cliente
            customer_data = data.get('customer', {})
            vat_number = customer_data.get('vat')
            name = customer_data.get('name')
            email = customer_data.get('email')
            phone = customer_data.get('phone')
            street = customer_data.get('street')
            city = customer_data.get('city')

            # Validar datos mínimos
            if not vat_number or not name or not email:
                return {'status': 'error',
                        'message': 'Nombre, email y cédula/RUC son requeridos.'}

            # Verificar si el cliente ya existe por su número de identificación
            existing_partner = request.env['res.partner'].sudo().search(
                [('vat', '=', vat_number)], limit=1)

            if existing_partner:
                partner_id = existing_partner.id
            else:
                # Si no existe, crear el cliente usando los datos proporcionados
                vat_identifier = 0
                if len(vat_number) == 10:
                    vat_identifier = 5  # Tipo de identificación para cédula
                elif len(vat_number) == 13:
                    vat_identifier = 4  # Tipo de identificación para RUC

                try:
                    new_partner = request.env['res.partner'].sudo().create({
                        'name': name,
                        'email': email,
                        'phone': phone,
                        'street': street,
                        'city': city,
                        'l10n_latam_identification_type_id': vat_identifier,
                        'vat': vat_number,
                    })
                    partner_id = new_partner.id
                except Exception as e:
                    return {'status': 'error',
                            'message': f'Error al crear el cliente: {str(e)}'}

            # Extraer líneas de pedido
            order_lines = data.get('order_line', [])

            if not order_lines:
                return {'status': 'error',
                        'message': 'Líneas de pedido faltantes en la solicitud.'}

            # Crear la orden de venta
            try:
                order = request.env['sale.order'].sudo().create({
                    'partner_id': partner_id,
                    'order_line': [
                        (0, 0, {
                            'product_id': line['product_id'],
                            'product_uom_qty': line.get('product_uom_qty', 1),
                        }) for line in order_lines
                    ]
                })
                return {'status': 'success', 'order_id': order.id}
            except Exception as e:
                return {'status': 'error',
                        'message': f'Error al crear la orden de venta: {str(e)}'}
        except Exception as e:
            return {'status': 'error',
                    'message': f'Error al procesar la solicitud: {str(e)}'}


# Farmacia de turno
class PharmacyOnDutyController(http.Controller):

    @http.route("/api/pharmacy_on_duty_by_city", type="http", auth="public",
                methods=["GET"], cors="*")
    def get_pharmacies_on_duty_by_city(self, **kw):
        city_name = kw.get("city_name", "").strip()

        # Buscar farmacias de turno (x_turno = True)
        companies_on_duty = request.env["res.company"].sudo().search([('x_turno', '=', True)])

        # Filtrar por ciudad si se proporciona city_name
        if city_name:
            companies_on_duty = companies_on_duty.filtered(
                lambda c: c.city and c.city.lower() == city_name.lower()
            )

        # Si no hay farmacias de turno, buscar farmacias 24 horas (x_24hours = True)
        companies_24hours = []
        if not companies_on_duty:
            companies_24hours = request.env["res.company"].sudo().search([('x_24hours', '=', True)])
            if city_name:
                companies_24hours = companies_24hours.filtered(
                    lambda c: c.city and c.city.lower() == city_name.lower()
                )

        # Determinar qué conjunto de sucursales se debe mostrar
        companies_to_display = companies_on_duty or companies_24hours

        # Construir la respuesta
        company_data = []
        for company in companies_to_display:
            company_info = {
                "name": company.name,
                "street": company.street,
                "city": company.city or "",
                "x_latitud": company.x_lat,
                "x_longitud": company.x_long,
                "x_turno": company.x_turno,
                "x_24hours": company.x_24hours,
            }
            company_data.append(company_info)

        if company_data:
            return request.make_response(
                json.dumps({"status": "success", "pharmacies": company_data}),
                headers=[("Content-Type", "application/json")],
            )
        else:
            return request.make_response(
                json.dumps({"status": "error",
                            "message": "No pharmacies found"}),
                headers=[("Content-Type", "application/json")],
            )


# Valores del envio
class DeliveryController(http.Controller):

    @http.route("/api/fixed_price_by_province", type="http", auth="public",
                methods=["GET"])
    def get_fixed_price_by_province(self, **kw):
        # Obtener el nombre de la provincia desde los parámetros de la URL
        province_name = kw.get("province_name", "")

        # Verificar que se haya proporcionado un nombre de provincia
        if not province_name:
            return json.dumps(
                {"status": "error", "message": "Province name is required"})

        # Buscar la provincia en el modelo res.country.state
        province = request.env["res.country.state"].sudo().search(
            [("name", "ilike", province_name)], limit=1)

        if not province:
            return json.dumps(
                {"status": "error", "message": "Province not found"})

        # Buscar transportistas (delivery.carrier) que tienen esta provincia en el campo state_ids
        carriers = request.env["delivery.carrier"].sudo().search(
            [("state_ids", "in", province.id)])

        if not carriers:
            return json.dumps(
                {"status": "error",
                 "message": "No carriers found for this province"})

        # Construir la respuesta con los datos de los transportistas y sus precios fijos
        carrier_data = []
        for carrier in carriers:
            carrier_info = {
                "carrier_id": carrier.id,
                "carrier_name": carrier.name,
                "fixed_price": carrier.fixed_price,
                "product_id": carrier.product_id.id
            }
            carrier_data.append(carrier_info)

        return json.dumps({"status": "success", "carriers": carrier_data})



