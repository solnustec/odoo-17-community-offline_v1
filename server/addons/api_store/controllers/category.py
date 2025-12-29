from datetime import datetime

from .api_security import validate_api_static_token
from .utils import ProductUtils
from odoo import http
from odoo.http import request, Response
import json

from ..utils.time_cache import APICache


class Category(http.Controller):
    api_cache = APICache(timeout=3600, max_size=1000)


    @http.route('/api/store/categories', type='http', auth='public',
                methods=['GET'],
                csrf=False, cors="*")
    @validate_api_static_token
    @api_cache.cache()
    def get_categories(self):
        # Obtener las categorías
        try:
            categories = request.env['product.public.category'].sudo().search([('parent_id', '=', False)])

            base_url = request.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')
            # Formatear los datos de las categorías
            unique_image_key = datetime.now().strftime("%Y%m%d%H%M%S")
            category_data = [{
                'id': category.id,
                'name': category.name,
                'parent_id': category.parent_id.id,
                'image_512': f"{base_url}/web/image/product.public.category/{category.id}/image_512?{unique_image_key}",
                'image_256': f"{base_url}/web/image/product.public.category/{category.id}/image_256?{unique_image_key}",
                # 'image_512': f"http://192.168.0.165:8069/web/image/product.public.category/{category.id}/image_512",
                # 'image_256': f"http://192.168.0.165:8069/web/image/product.public.category/{category.id}/image_256",
            } for category in categories]

            return Response(
                json.dumps(
                    {
                        'status': 'success',
                        'message': 'Categorías obtenidas exitosamente',
                        'data': category_data
                    }
                ),
                status=200,
                content_type='application/json'
            )
        except Exception as e:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        "message": "Hubo un error al obtener las categorias" + str(
                            e),
                        'data': None
                    }
                ),
                status=500,
                content_type='application/json'
            )

    @http.route('/api/store/products/category/<int:category_id>', type='http',
                auth='public', methods=['GET'], csrf=False, cors="*")
    @validate_api_static_token
    @api_cache.cache()
    def get_products_by_category(self, category_id, **kw):
        try:
            # data = json.loads(request.httprequest.data.decode('utf-8'))
            try:
                limit = int(kw.get('limit', 10))
                offset = int(kw.get('offset', 0))
                city_id = int(kw.get('city_id', 1413))
            except ValueError:
                return Response(
                    json.dumps(
                        {
                            'status': 'error',
                            'message': 'Invalid limit or offset',
                            'data': None
                        }
                    ),
                    status=400,
                    content_type='application/json'
                )

            warehouse_domain = [('app_mobile_warehouse', '=', True),
                                ('city_id', '=', city_id)]
            warehouse = request.env['stock.warehouse'].sudo().search(
                warehouse_domain, limit=1)

            # Obtener productos con stock
            stock_quant_domain = [
                ('warehouse_id', '=', warehouse.id),
                ('quantity', '>', 0),  # Solo productos con stock positivo
                ('product_id.is_published', '=', True)
            ]
            products_with_stock = request.env['stock.quant'].sudo().search(
                stock_quant_domain
            ).mapped('product_id.product_tmpl_id').ids
            # pricelist = request.env['product.pricelist'].browse()
            # products = request.env['product.template'].sudo().search(
            #     [('is_published', '=', True),
            #      ('public_categ_ids', 'in', category_id)],
            #     limit=limit,
            #     offset=offset
            # )
            products = request.env['product.template'].sudo().search(
                [('id', 'in', products_with_stock), ('public_categ_ids', 'in', category_id)],
                limit=limit,
                offset=offset,
                order='name asc'  # Ordenar por nombre
            )

            base_url = request.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')

            product_data = ProductUtils._prepare_product_data(products,
                                                              base_url,
                                                              )

            total_products = len(products)
            response_data = {
                'data': product_data,
                'pagination': {
                    'limit': limit,
                    'offset': offset,
                    'total_products': total_products,
                    'remaining_products': max(total_products - offset - limit,
                                              0),
                }
            }

            return Response(
                json.dumps(
                    {
                        'status': 'success',
                        'message': 'Productos obtenidos exitosamente',
                        'data': response_data
                    }
                ),
                status=200,
                content_type='application/json'
            )
        except Exception as e:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        "message": "Eroor al obtener los productos" + str(e),
                        'data': None
                    }
                ),
                status=500,
                content_type='application/json'
            )

    @http.route('/api/store/category/product/home', methods=['GET'], type='http', auth='public', csrf=False, cors="*")
    @validate_api_static_token
    # @api_cache.cache()
    @http.route('/api/store/category/product/home', methods=['GET'], type='http', auth='public',
                csrf=False, cors="*")
    @validate_api_static_token
    def get_home_products(self, **kw):
        try:
            city_id = int(kw.get('city_id', 1413))
            limit = int(kw.get('limit', 20))
            offset = int(kw.get('offset', 0))
        except ValueError:
            return Response(
                json.dumps({
                    'status': 'error',
                    'code': 'INVALID_PARAMS',
                    'message': 'Invalid limit, offset, or city_id'
                }),
                status=400,
                content_type='application/json'
            )

        # Buscar categoría principal
        main_category = request.env['product.public.category'].sudo().search(
            [('is_main_app_category', '=', True)],
            limit=1
        )

        # Buscar almacén
        warehouse = request.env['stock.warehouse'].sudo().search(
            [('app_mobile_warehouse', '=', True), ('city_id.id', '=', city_id)],
            limit=1
        )

        if not warehouse:
            return Response(
                json.dumps({
                    'status': 'error',
                    'message': 'No existe un almacén para esta ciudad',
                    'data': None
                }),
                status=404,
                content_type='application/json'
            )

        # Obtener productos con stock
        stock_quant_domain = [
            ('warehouse_id', '=', warehouse.id),
            ('product_id.is_published', '=', True),
        ]

        products_with_stock = request.env['stock.quant'].sudo().search(
            stock_quant_domain
        ).mapped('product_id.product_tmpl_id').ids

        if not products_with_stock:
            return Response(
                json.dumps({
                    'status': 'success',
                    'message': 'No hay productos disponibles en esta ciudad',
                    'data': {
                        'category_name': main_category.name if main_category else 'Productos',
                        'data': [],
                        'pagination': {
                            'limit': limit,
                            'offset': offset,
                            'total_products': 0,
                            'remaining_products': 0
                        }
                    }
                }),
                status=200,
                content_type='application/json'
            )

        # Construir dominio de búsqueda
        product_domain = [('id', 'in', products_with_stock)]

        # Si existe categoría principal, filtrar por ella
        if main_category:
            product_domain.append(('public_categ_ids', 'child_of', main_category.id))

        # Buscar productos con paginación
        products = request.env['product.template'].sudo().search(
            product_domain,
            limit=limit,
            offset=offset,
            order='name asc'
        )

        # Contar total de productos con el filtro aplicado
        total_products = request.env['product.template'].sudo().search_count(product_domain)

        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        product_data = ProductUtils._prepare_product_data(products, base_url)

        response_data = {
            'category_name': main_category.name if main_category else 'Productos',
            'data': product_data,
            'pagination': {
                'limit': limit,
                'offset': offset,
                'total_products': total_products,
                'remaining_products': max(total_products - offset - limit, 0)
            }
        }

        return Response(
            json.dumps({
                'status': 'success',
                'message': 'Productos obtenidos exitosamente',
                'data': response_data
            }),
            status=200,
            content_type='application/json'
        )

