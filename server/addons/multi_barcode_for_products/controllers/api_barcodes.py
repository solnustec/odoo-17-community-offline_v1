# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json


class ProductMultiBarcodeAPI(http.Controller):

    @http.route('/api/product/barcodes', type='http', auth='public', methods=['POST'], csrf=False)
    def create_multiple_barcodes(self, **kwargs):
        """
        API para crear múltiples códigos de barras asociados a un producto o template.
        JSON esperado:
        {
            "id_database_old": 12345,  // campo personalizado del template
            "barcodes": ["1111111111111", "2222222222222"]
        }
        """
        try:
            data = request.httprequest.get_json()
            if not data:
                return request.make_response(
                    json.dumps({"status": "error", "message": "No se recibió JSON válido."}),
                    headers=[("Content-Type", "application/json")]
                )

            id_database_old = data[0].get("id_database_old")
            barcodes = data[0].get("barcodes")

            if not id_database_old or not barcodes:
                return request.make_response(
                    json.dumps({"status": "error", "message": "Debe enviar 'id_database_old' y 'barcodes'."}),
                    headers=[("Content-Type", "application/json")]
                )

            # Buscar producto.template por campo personalizado
            ProductTemplate = request.env["product.template"].sudo()
            template = ProductTemplate.search([("id_database_old", "=", id_database_old)], limit=1)

            if not template:
                return request.make_response(
                    json.dumps({
                        "status": "error",
                        "message": f"No se encontró un producto con id_database_old={id_database_old}."
                    }),
                    headers=[("Content-Type", "application/json")]
                )

            # Usar la primera variante asociada
            if not template.product_variant_ids:
                return request.make_response(
                    json.dumps({
                        "status": "error",
                        "message": f"El template '{template.name}' no tiene variantes asociadas."
                    }),
                    headers=[("Content-Type", "application/json")]
                )

            product = template.product_variant_ids[0]

            created = []
            skipped = []

            for barcode in barcodes:
                existing = request.env["product.multiple.barcodes"].sudo().search([
                    ("product_multi_barcode", "=", barcode)
                ], limit=1)

                if existing:
                    skipped.append(barcode)
                    continue

                request.env["product.multiple.barcodes"].sudo().create({
                    "product_id": product.id,
                    "product_template_id": template.id,
                    "product_multi_barcode": barcode,
                })
                created.append(barcode)

            result = {
                "status": "success",
                "product": template.name,
                "id_database_old": id_database_old,
                "message": f"Se crearon {len(created)} códigos, {len(skipped)} duplicados.",
                "created": created,
                "skipped": skipped
            }

            return request.make_response(
                json.dumps(result),
                headers=[("Content-Type", "application/json")]
            )

        except Exception as e:
            error = {"status": "error", "message": str(e)}
            return request.make_response(json.dumps(error), headers=[("Content-Type", "application/json")])
