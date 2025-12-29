import datetime
import time

from .api_security import validate_api_static_token

from odoo import http
from odoo.http import request, Response
import json

from .utils import ProductUtils
from ..utils.time_cache import APICache


class ProductListController(http.Controller):
    # api_cache = APICache(timeout=3600, max_size=1000)

    @http.route("/api/store/products", auth="public", type="http",
                methods=["GET"],
                csrf=False, cors="*")
    @validate_api_static_token
    # @api_cache.cache()
    def get_products(self, **kw):
        time_start = time.time()
        try:
            # Validar parámetros de entrada
            try:
                limit = int(kw.get('limit', 10))
                offset = int(kw.get('offset', 0))
                city_id = int(kw.get('city_id', 1413))
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

            # Buscar almacén
            warehouse_domain = [('app_mobile_warehouse', '=', True),
                                ('city_id', '=', city_id)]
            warehouse = request.env['stock.warehouse'].sudo().search(
                warehouse_domain, limit=1)
            if not warehouse:
                return Response(
                    json.dumps({
                        'status': 'error',
                        'code': 'WAREHOUSE_NOT_FOUND',
                        'message': 'No warehouse configured for the mobile app in this city'
                    }),
                    status=404,
                    content_type='application/json'
                )

            # Obtener productos con stock
            stock_quant_domain = [
                ('warehouse_id', '=', warehouse.id),
                # ('quantity', '>', 0),  # Solo productos con stock positivo
                ('product_id.is_published', '=', True)
            ]

            products_with_stock = request.env['stock.quant'].sudo().search(
                stock_quant_domain
            ).mapped('product_id.product_tmpl_id').ids

            if not products_with_stock:
                return Response(
                    json.dumps({
                        'status': 'success',
                        'message': 'No products available in this city',
                        'data': {
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

            # Buscar productos con paginación
            products = request.env['product.template'].sudo().search(
                [('id', 'in', products_with_stock)],
                limit=limit,
                offset=offset,
                order='name asc'  # Ordenar por nombre
            )
            base_url = request.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')
            product_data = ProductUtils._prepare_product_data(products,
                                                              base_url)
            response_data = {
                'data': product_data,
                'pagination': {
                    'limit': limit,
                    'offset': offset,
                    'total_products': len(products_with_stock),
                    'remaining_products': max(
                        len(products_with_stock) - offset - limit, 0)
                }
            }
            time_end = time.time()
            print(f"Tiempo de ejecución: {time_end - time_start} segundos")

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
                        "message": "Error al obtener los productos: " + str(e),
                        'data': None
                    }
                ),
                status=400,
                content_type='application/json'
            )

    @http.route('/api/store/products/<int:product_id>', type='http',
                auth='public',
                methods=['GET'], csrf=False, cors="*")
    @validate_api_static_token
    # @api_cache.cache()
    def product_detail(self, product_id):
        try:
            product = request.env['product.template'].sudo().browse(product_id)
            if not product.exists():
                return Response(
                    json.dumps(
                        {
                            'status': 'error',
                            'message': 'Producto no encontrado',
                            'data': None
                        }
                    ),
                    status=400,
                    content_type='application/json'
                )
            # pricelist = ProductUtils._get_store_pricelist()
            # price = pricelist._compute_price_rule(product, 1)
            product_info = {
                'id': product.id,
                'name': product.name,
                'price': product.list_price * product.uom_po_id.factor_inv if product.sale_uom_ecommerce else product.list_price,
                'description': product.description_sale,
                'stock': product.qty_available,
                'uom': product.uom_po_id.name,
                'description_sale': product.description_sale,
                'description_ecommerce': product.description_ecommerce,
                'image_url': f"/web/image/product.product/{product.id}/image_1920?{datetime.datetime.now()}",
                'category': [
                    {
                        'id': category.id, 'name': category.name,
                        'parent_category_id': category.parent_id.id,
                        'parent_category_name': category.parent_id.name
                    }
                    for category in product.public_categ_ids
                ]
            }

            return Response(
                json.dumps({
                    'status': 'success',
                    'message': 'Producto obtenido exitosamente',
                    'data': product_info
                }),
                status=200,
                content_type='application/json'
            )
        except Exception as e:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        "message": "Error al obtener el producto " + str(e),
                        'data': None
                    }
                ),
                status=400,
                content_type='application/json'
            )

    @http.route('/api/store/search_products', type='http', auth='public',
                methods=['GET'], csrf=False, cors="*")
    @validate_api_static_token
    def search_products(self, **kwargs):
        try:
            # Obtener parámetros de búsqueda
            search_term = kwargs.get('q', '')  # término de búsqueda
            limit = int(kwargs.get('limit', 30))
            offset = int(kwargs.get('offset', 0))
            category_id = int(kwargs.get('category_id', 0))
            order = kwargs.get('order', 'name ASC')


            if search_term:
                domain = self.build_product_search_domain_simple(self, category_id, search_term)

                # Buscar productos
                Product = request.env['product.template'].sudo()
                products = Product.search(domain, limit=limit, offset=offset,
                                          order=order)

                # pricelist = ProductUtils._get_store_pricelist()
                # prices = ProductUtils._get_product_prices(products,
                #                                           pricelist) if pricelist else {}
                total_count = Product.search_count(domain)
                base_url = request.env['ir.config_parameter'].sudo().get_param(
                    'web.base.url')

                product_data = ProductUtils._prepare_product_data(products,
                                                                  base_url,
                                                                  )

                response_data = {
                    'total_count': total_count,
                    'offset': offset,
                    'limit': limit,
                    'products': product_data
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
            else:
                return Response(
                    json.dumps({
                        'status': 'error',
                        'message': 'Escriba algo para buscar',
                        'data': None
                    }),
                    status=200,
                    content_type='application/json'
                )
        except Exception as e:
            return Response(
                json.dumps({
                    'status': 'error',
                    'message': 'Hubo un error al buscar los productos ' + str(
                        e),
                    'data': None
                }),
                status=500,
                content_type='application/json'
            )

    @staticmethod
    def build_product_search_domain_simple(self, category_id, search_term):
        """
        Búsqueda simple: busca el término completo en los campos principales
        Similar a cómo funcionan Amazon, MercadoLibre, etc.
        """
        domain = [
            ('website_published', '=', True),
            ('active', '=', True)
        ]

        # Filtro por categoría
        if category_id and category_id > 0:
            Category = request.env['product.public.category']
            all_categs = Category.search([('id', 'child_of', category_id)]).ids
            if all_categs:
                domain.append(('public_categ_ids', 'in', all_categs))

        # Filtro por búsqueda (término completo)
        if search_term:
            term = search_term.strip()
            domain.extend([
                '|', '|', '|',
                ('name', 'ilike', term),
                ('description_ecommerce', 'ilike', term),
                ('default_code', 'ilike', term),
                ('public_categ_ids.name', 'ilike', term)
            ])

        return domain

    @http.route('/api/store/cache_info', type='http', auth='public', methods=['GET'], csrf=False,
                cors="*")
    # @validate_api_static_token
    def cache_info(self):
        print("Obteniendo información del caché")
        cache_info = self.api_cache.info()
        response = request.make_response(
            json.dumps(cache_info, indent=2, sort_keys=True),
            headers={'Content-Type': 'application/json'}
        )
        print("Información del caché obtenida")
        return response
