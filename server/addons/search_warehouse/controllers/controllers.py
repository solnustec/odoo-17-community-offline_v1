# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class WarehouseController(http.Controller):
    @http.route('/pos/warehouses', type='http', auth='public', csrf=False, methods=['GET'])
    def get_warehouses(self, **kwargs):
        """
        GET /pos/warehouses?product_id=<id>[&city=<nombre>]
        - product_id: id de product.product o product.template
        - city: opcional, filtra por nombre de ciudad (ilike)
        Devuelve stock por almacén usando free_qty con contexto de ubicación.
        Excluye almacenes con stock 0, pero muestra negativos y positivos.
        """
        try:
            product_id = kwargs.get('product_id')
            if not product_id:
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'Falta el ID del producto'}),
                    headers={'Content-Type': 'application/json'}, status=400
                )

            product_id = int(product_id)
            Product = request.env['product.product'].sudo()

            # Si no es una variante, tomar todas las variantes del template
            product = Product.browse(product_id)
            products = product if product.exists() else Product.search([('product_tmpl_id', '=', product_id)])

            if not products:
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'Producto no encontrado'}),
                    headers={'Content-Type': 'application/json'}, status=404
                )

            # Filtrar almacenes por ciudad si viene en query
            wh_domain = []
            city_filter = (kwargs.get('city') or '').strip()
            if city_filter:
                wh_domain.append(('city', 'ilike', city_filter))

            warehouses = request.env['stock.warehouse'].sudo().search(wh_domain, order='name')

            results = []
            for wh in warehouses:
                # Contexto por ubicación raíz del almacén (incluye hijas)
                ctx = {
                    'location': wh.lot_stock_id.id,
                    'compute_child': True,
                }
                # free_qty: disponible (no reservado). Si prefieres on hand, usa 'qty_available'
                rows = products.with_context(**ctx).read(['free_qty'])
                available = sum((r.get('free_qty') or 0.0) for r in rows)

                # Excluir stock exactamente igual a 0
                if available != 0:
                    results.append({
                        'id': wh.id,
                        'warehouse_name': wh.name,
                        'city': (wh.city or '').strip(),
                        'state_id': wh.state_id.id or None,
                        'state_name': wh.state_id.name or '',
                        'available_quantity': float(available),
                    })

            return request.make_response(
                json.dumps({'status': 'success', 'warehouses': results}, ensure_ascii=False),
                headers={'Content-Type': 'application/json'}, status=200
            )

        except Exception as e:
            _logger.error("Error al obtener almacenes: %s", e, exc_info=True)
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(e)}),
                headers={'Content-Type': 'application/json'}, status=500
            )
