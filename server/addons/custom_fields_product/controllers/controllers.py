from odoo import http
from odoo.http import request, Response
import requests
import json


class ProductAPI(http.Controller):
    @http.route('/api/products/update-laboratory', type='json', auth='public',
                methods=['POST'], csrf=False)
    def update_product(self, **kwargs):
        try:
            # Parse JSON payload
            data = request.httprequest.get_json()
            products = data.get('data', [])
            if not products:
                return {"status": "error", "message": "No data provided"}

            for product_data in products:
                product_id = product_data.get('id')
                laboratory_name = product_data.get('laboratorio')
                brand_name = product_data.get('marca')

                # Find the product using sudo
                product = request.env['product.template'].sudo().search(
                    [('id_database_old', '=', product_id)], limit=1)
                if not product:
                    return {"status": "error",
                            "message": f"Product with ID {product_id} not found"}

                # Find or create laboratory using sudo
                laboratory = request.env['product.laboratory'].sudo().search(
                    [('name', '=', laboratory_name)], limit=1)
                if not laboratory and laboratory_name:
                    laboratory = request.env['product.laboratory'].sudo().create(
                        {'name': laboratory_name})

                # Find or create brand using sudo
                brand = request.env['product.brand'].sudo().search(
                    [('name', '=', brand_name)], limit=1)
                if not brand and brand_name:
                    brand = request.env['product.brand'].sudo().create(
                        {'name': brand_name})

                # Update the product fields using sudo
                product.sudo().write({
                    'laboratory_id': laboratory.id if laboratory else False,
                    'brand_id': brand.id if brand else False,
                })

            return {"status": "success", "message": "Products updated successfully"}

        except Exception as e:
            return {"status": "error", "message": str(e)}


