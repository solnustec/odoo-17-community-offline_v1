import requests

from .api_security import validate_api_static_token
from odoo import http
from odoo.http import request, Response, _logger
import json

from .jwt import validate_jwt
from .utils import ProductUtils, OrderUtils


class CartController(http.Controller):

    @http.route('/api/store/cart/add', type='http', auth='public',
                methods=['POST'], csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def add_to_cart(self, **kwargs):
        # try:
        data = json.loads(request.httprequest.data.decode('utf-8'))
        partner_id = data.get('partner_id', False)
        city_id = data.get('city_id', 1413)
        lines = data.get('lines', [])
        order = None
        # waregousr
        warehouse = request.env['stock.warehouse'].sudo().search([
            ('city_id.id', '=', city_id),
            ('app_mobile_warehouse', '=', True)
        ], limit=1)

        if not warehouse:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'No se encontró un almacén asociado a la ciudad',
                    'data': None
                }),
                status=404, content_type='application/json')
        # Buscar el carrito (sale.order) en estado 'cart' (borrador)
        order = request.env['sale.order'].sudo().search([
            ('partner_id.id', '=', partner_id),
            ('state', '=', 'draft'),
            ('website_id', '=', 1),
        ], limit=1)

        if not order:
            # Si no existe, creamos un nuevo carrito
            order = request.env['sale.order'].sudo().create({
                'partner_id.id': partner_id,
                'website_id': 1,
                'state': 'draft',
                'partner_shipping_id': '',
                'warehouse_id': warehouse.id,
                'is_order_app': True
            })

        for line in lines:
            product_id = line.get('product_id', False)
            # city_id = line.get('city_id', 1413)
            quantity = line.get('quantity', False)
            # partner_id = line.get('partner_id', False)

            # Buscar el producto seleccionado
            # product_template = request.env['product.template'].sudo().browse(
            #     product_id)
            product = request.env['product.product'].sudo().search(
                [('product_tmpl_id', '=', product_id)]
            )
            if not product.exists():
                return Response(json.dumps(
                    {
                        'status': 'error',
                        'message': 'Producto no encontrado',
                        'data': None
                    }),
                    status=404, content_type='application/json')
            # Verificar si el producto ya está en el carrito
            order_line = request.env['sale.order.line'].sudo().search([
                ('order_id', '=', order.id),
                ('product_id', '=', product.id)
            ], limit=1)

            if product.product_tmpl_id.sale_uom_ecommerce:
                price = product.product_tmpl_id.list_price * product.product_tmpl_id.uom_po_id.factor_inv
            else:
                price = product.product_tmpl_id.list_price

            if order_line:
                product_is_available = order_line._check_qty_with_other_quotations(
                    warehouse_id=warehouse.id,
                    current_quantity_requested=order_line.product_uom_qty + quantity)
                _logger.info(f"product_is_available {product_is_available}")
                if not product_is_available:
                    return Response(json.dumps(
                        {
                            'status': 'error',
                            'message': f'No hay suficiente stock disponible para el producto {product.name}.',
                            'data': None
                        }),
                        status=400, content_type='application/json')

                # Si existe, solo actualizamos la cantidad
                order_line.sudo().write(
                    {'product_uom_qty': order_line.product_uom_qty + quantity})
            else:
                # Si no existe, creamos una nueva línea
                order_line = request.env['sale.order.line'].sudo().create({
                    'order_id': order.id,
                    'product_id': product.id,
                    'product_uom_qty': quantity,
                    'price_total': price,
                    'company_id': 1,
                })
                if order_line:
                    product_is_available = order_line._check_qty_with_other_quotations(
                        warehouse_id=warehouse.id, current_quantity_requested=quantity)
                    _logger.info(f"product_is_available {product_is_available}")
                    if not product_is_available:
                        order_line.sudo().unlink()
                        return Response(json.dumps(
                            {
                                'status': 'error',
                                'message': f'No hay suficiente stock disponible para el producto {product.name}.',
                                'data': None
                            }),
                            status=400, content_type='application/json')

                # Asignar el almacén al pedido
            order.sudo().write({'warehouse_id': warehouse.id})
            order.apply_app_mobile_promotions()
        data = OrderUtils.format_data_response(order)
        return Response(json.dumps(
            data
        ),
            status=200, content_type='application/json')

        # except Exception as e:
        #     return Response(json.dumps(
        #         {
        #             'status': 'error',
        #             'message': 'Ha ocurrido un error al agregar el producto al carrito ' + str(
        #                 e),
        #             'data': None
        #         }
        #     ),
        #         status=500, content_type='application/json')

    @http.route('/api/store/cart/update', type='http', auth='public',
                methods=['POST'], csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def update_cart(self):
        try:

            data = json.loads(request.httprequest.data.decode('utf-8'))
            order_id = data.get('order_id')
            if not order_id:
                return Response(json.dumps(
                    {
                        "status": "error",
                        "message": "El parámetro 'order_id' es obligatorio",
                        "data": None
                    }
                ), status=400, content_type='application/json')
            # verificar si tiene una orden confirmada
            existing_order = request.env['sale.order'].sudo().search([
                ('partner_id.id', '=', data.get('partner_id')),
                ('state', '=', 'sale'),
                ('is_order_app', '=', True)
            ], limit=1)
            if existing_order:
                data = OrderUtils.format_data_response(existing_order)
                return Response(json.dumps(data), status=200, content_type='application/json')
            # Buscar orden
            order = request.env['sale.order'].sudo().search([
                ('id', '=', int(order_id)),
                ('state', '=', 'draft'),
                ('website_id', '=', 1)
            ], limit=1)
            if not order:
                return Response(json.dumps(
                    {
                        "status": "error",
                        "message": "La orden no fue encontrada, o ya fue procesada",
                        "data": None
                    }
                ), status=404, content_type='application/json')

            partner_id = data.get('partner_id', False)
            if partner_id:
                order.sudo().write({'partner_id.id': partner_id})

            if data.get('order_completed', False):
                order.sudo().write({'state': 'sale'})

            address_delivery = data.get('address_delivery', False)
            if address_delivery:
                order.sudo().write(
                    {'address_delivery_calculate': address_delivery})
            # verificar si el productyo de envio tiene precio 0 y eliminar la linea
            shipping_product = request.env['product.product'].sudo().search(
                [('default_code', '=', 'ENVIOSAPPMOVIL'),
                 ('detailed_type', '=', 'service')], limit=1
            )
            if shipping_product.exists():
                shipping_line = request.env['sale.order.line'].sudo().search([
                    ('order_id', '=', order.id),
                    ('product_id', '=', shipping_product.id),
                    ('price_unit', '=', 0)
                ], limit=1)
                if shipping_line.exists():
                    order.sudo().write(
                        {'partner_shipping_id': False})

            lines = data.get('lines', [])
            for line in lines:
                product_id = line.get('product_id')
                quantity = line.get('quantity')
                if not product_id or quantity is None:
                    return Response(json.dumps(
                        {
                            "status": "error",
                            "message": "El parámetro 'product_id' y 'quantity' son obligatorios",
                            "data": None
                        }
                    ), status=400, content_type='application/json')

                product = request.env['product.product'].sudo().search(
                    [('product_tmpl_id', '=', product_id)]
                )
                if not product.exists():
                    return Response(json.dumps(
                        {
                            "status": "error",
                            "message": f"El producto con el id {product_id} no fue encontrado",
                            "data": None
                        }
                    ), status=400, content_type='application/json')

                order_line = request.env['sale.order.line'].sudo().search([
                    ('order_id', '=', order.id),
                    ('product_id', '=', product.id)
                ], limit=1)

                # has_claimed_reward_line = order.has_claimed_reward_line()
                if order_line:
                    if quantity == 0:
                        try:
                            order_line.sudo().unlink()
                        except Exception as e:
                            return Response(json.dumps(
                                {
                                    "status": "error",
                                    "message": "No se puede eliminar la última línea del pedido si contiene una recompensa reclamada.",
                                    "data": None
                                }
                            ), status=400, content_type='application/json')

                    else:
                        product_is_available = order_line._check_qty_with_other_quotations(
                            warehouse_id=order.warehouse_id.id,
                            current_quantity_requested=quantity)

                        if not product_is_available:
                            # order_line.sudo().unlink()
                            return Response(json.dumps(
                                {
                                    'status': 'error',
                                    'message': f'No hay suficiente stock disponible para el producto {product.name}.',
                                    'data': None
                                }),
                                status=400, content_type='application/json')
                        order_line.sudo().write({'product_uom_qty': quantity})
                # if len(order.order_line) == 0:
                #     order.sudo().write({'partner_shipping_id': False})
                elif quantity > 0:
                    order_line = request.env['sale.order.line'].sudo().create({
                        'order_id': order.id,
                        'product_id': product.id,
                        'product_uom_qty': quantity,
                        'price_unit': product.list_price,
                    })
                    product_is_available = order_line._check_qty_with_other_quotations(
                        warehouse_id=order.warehouse_id.id,
                        current_quantity_requested=quantity)

                    if not product_is_available:
                        order_line.sudo().unlink()
                        return Response(json.dumps(
                            {
                                'status': 'error',
                                'message': f'No hay suficiente stock disponible para el producto {product.name}.',
                                'data': None
                            }),
                            status=400, content_type='application/json')

            order.apply_app_mobile_promotions()
            OrderUtils.apply_order_global_discount(order)
            data = OrderUtils.format_data_response(order)
            return Response(json.dumps(
                data
            ),
                status=200, content_type='application/json')

        except ValueError as e:
            return Response(json.dumps(
                {
                    "status": "error",
                    "message": str(e),
                    "data": None
                }
            ), status=400, content_type='application/json')
        # except Exception as e:

    #     print(e)
    #     return Response(json.dumps(
    #         {
    #             "status": "error",
    #             "message": "Error al actualizar la orden",
    #             "data": None
    #         }
    #     ), status=500, content_type='application/json')

    @http.route('/api/store/cart/details', type='http', auth='public',
                methods=['GET'])
    @validate_api_static_token
    @validate_jwt
    def get_cart_details(self, **kwargs):
        try:
            # Obtener el parámetro order_id desde la URL
            order_id = kwargs.get('order_id')

            if not order_id:
                return Response(json.dumps(
                    {'status': 'error',
                     'message': 'El parámetro "order_id" es obligatorio'}),
                    status=400, content_type='application/json')

            # Convertir a entero
            try:
                order_id = int(order_id)
            except ValueError:
                return Response(json.dumps(
                    {'status': 'error',
                     'message': 'El parámetro "order_id" debe ser un número válido'}),
                    status=400, content_type='application/json')

            # Buscar el carrito del cliente en estado 'draft'
            order = request.env['sale.order'].sudo().search([
                ('id', '=', order_id),
                ('state', 'in', ['draft', 'sale']),
                ('in_payment_process', '=', False),
                ('website_id', '=', 1),
            ], limit=1)

            if not order:
                return Response(json.dumps(
                    {'status': 'error', 'message': 'Carrito no encontrado'}),
                    status=404, content_type='application/json')
            data = OrderUtils.format_data_response(order)
            return Response(json.dumps(
                data
            ),
                status=200, content_type='application/json')

        except Exception as e:
            return Response(json.dumps(
                {'status': 'error', 'message': str(e)}),
                status=500, content_type='application/json')

    @http.route('/api/store/cart', type='http', auth='public',
                methods=['POST'], csrf=False, cors="*")
    @validate_api_static_token
    def get_or_create_sale_order(self, **kwargs):
        """
        API endpoint to retrieve or create a draft sale order for a given partner_id.
        :param partner_id: ID of the partner (customer)
        :return: JSON with sale order ID and status
        """
        try:
            jwt_data = getattr(request, '_jwt_data', {})
            user_id = jwt_data.get('user_id')
            data = json.loads(request.httprequest.data.decode('utf-8'))
            partner_id = data.get('partner_id')
            city_id = data.get('city_id', 1413)
            warehouse_id = request.env['stock.warehouse'].sudo().search([
                ('city_id.id', '=', city_id),
                ('app_mobile_warehouse', '=', True)
            ], limit=1)

            if not warehouse_id:
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'No se encontró un almacén asociado a la ciudad',
                    'data': None
                }), status=400, content_type='application/json')

            if not partner_id:
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'El partner_id es obligatorio',
                    'data': None
                }), status=400, content_type='application/json')

            env = request.env['sale.order'].sudo()

            existing_order = request.env['sale.order'].sudo().search([
                ('partner_id.id', '=', data.get('partner_id')),
                ('state', '=', 'sale'),
                ('in_payment_process', '=', False),
                ('is_order_app', '=', True)
            ], limit=1)
            order_state = existing_order.check_order_payment_status(existing_order.id)
            if existing_order and not order_state.get("payment_status") == "Pagada":
                data = OrderUtils.format_data_response(existing_order)
                return Response(json.dumps(data), status=200, content_type='application/json')

            sale_order = env.search([
                ('partner_id', '=', int(partner_id)),
                ('state', '=', 'draft'),
                ('user_id', '=', user_id),
                ('in_payment_process', '=', False),
                ('is_order_app', '=', True)
            ], limit=1)

            if sale_order:
                data = OrderUtils.format_data_response(sale_order)
                return Response(json.dumps(
                    data
                ),
                    status=200, content_type='application/json')

            # If no draft order exists, create a new one
            new_sale_order = env.create({
                'partner_id': int(partner_id),
                'state': 'draft',
                'website_id': 1,
                'user_id': user_id,
                'warehouse_id': warehouse_id.id,
                'is_order_app': True,
            })

            data = OrderUtils.format_data_response(new_sale_order)
            return Response(json.dumps(
                data
            ),
                status=200, content_type='application/json')
        except Exception as e:
            return Response(
                json.dumps({
                    'status': 'error',
                    'message': 'Servicio no disponible, intente más tarde. ',
                    'data': None,
                }), status=500, content_type='application/json')

    @http.route('/api/store/cart/<int:order_id>', type='http', auth='public', method=['DELETE'],
                cors='*', csrf=False)
    @validate_api_static_token
    @validate_jwt
    def delete_cart(self, **kwargs):
        try:
            order_id = kwargs.get('order_id')
            if not order_id:
                return Response(json.dumps(
                    {
                        'status': 'error',
                        'message': 'El parámetro "order_id" es obligatorio',
                        'data': None
                    }
                ), status=400, content_type='application/json')

            order = request.env['sale.order'].sudo().search([
                ('id', '=', int(order_id)),
                ('state', '=', 'sale'),
                ('in_payment_process', '=', False),
                # ('website_id', '=', 1)
            ], limit=1)

            if not order:
                return Response(json.dumps(
                    {
                        'status': 'error',
                        'message': 'La orden no fue encontrada, o ya fue procesada',
                        'data': None
                    }
                ), status=404, content_type='application/json')

            # order.sudo().action_cancel()
            # verificar si no tiene pagos asociados payment_transaction
            payment_count = request.env['payment.transaction'].sudo().search_count([
                ('sale_order_ids', 'in', order.id), ('is_app_transaction', '=', True),
                ('state', 'in', ['pending'])
            ])

            if payment_count > 0:
                # print(payment_count.provider_id.code, '---------payment_count')
                # pasar a estado cancelado
                try:
                    payment_transactions = request.env['payment.transaction'].sudo().search([
                        ('sale_order_ids', 'in', order.id), ('is_app_transaction', '=', True),
                        ('state', 'in', ['pending']), ('payment_method_id.code', '=', 'card')
                    ])
                    for p in payment_transactions:
                        request.env['payment.transaction'].manual_check_payment_status(
                            p.payment_transaction_id)
                except Exception as e:
                    print(e)
                    pass
                order.sudo().write({'in_payment_process': True})

                return Response(json.dumps(
                    {
                        'status': 'error',
                        'message': 'Su orden esta en proceso de validación de pago',
                        'data': None
                    }
                ), status=200, content_type='application/json'

                )
            # order.sudo().with_context(disable_cancel_warning=True).action_cancel()
            # order.sudo().action_draft()
            # liominar la linea de producto de envio
            # shipping_product = request.env['product.product'].sudo().search(
            #     [('default_code', '=', 'ENVIOSAPPMOVIL'),
            #      ('detailed_type', '=', 'service')], limit=1
            # )
            # if shipping_product.exists():
            #     shipping_line = request.env['sale.order.line'].sudo().search([
            #         ('order_id', '=', order.id),
            #         ('product_id', '=', shipping_product.id)
            #     ], limit=1)
            #     if shipping_line.exists():
            #         shipping_line.sudo().unlink()
            # remove partner_shipping_id

            # order.sudo().write({'partner_shipping_id': False})
            # order.sudo().with_context(disable_cancel_warning=True).action_draft()
            # order.apply_app_mobile_promotions()
            # remove all lines
            # order.order_line.sudo().unlink()
            # order.apply_discount_to_all_lines(order.partner_id.id, remove=True)
            # return Response(json.dumps(
            #     {
            #         'status': 'success',
            #         'message': 'Carrito eliminado correctamente',
            #         'data': None
            #     }
            # ), status=200, content_type='application/json')
        except Exception as e:
            _logger.error('El orden no fue encontrada', e)
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'Error interno del servidor: ' + str(e),
                    'data': None
                }
            ), status=404, content_type='application/json')

    @http.route('/api/store/cart/invoice', type='http',
                auth='public',
                methods=['PATCH'], csrf=False, cors='*')
    @validate_api_static_token
    @validate_jwt
    def invoice_direction(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        order_id = data.get('order_id')
        invoice_direction_id = data.get('invoice_address_id')
        if not order_id:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'El parámetro "order_id" es obligatorio',
                    'data': None
                }
            ), status=400, content_type='application/json')
        order = request.env['sale.order'].sudo().search([
            ('id', '=', int(order_id)),
            ('state', 'in', ['draft', 'sale']),
            ('website_id', '=', 1)
        ], limit=1)
        if not order:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'La orden no fue encontrada, o ya fue procesada',
                    'data': None
                }
            ), status=404, content_type='application/json')
        if not invoice_direction_id:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'La direccion de facturación es obligatoria',
                    'data': None
                }
            ), status=400, content_type='application/json')
        order.sudo().write({'partner_invoice_id': invoice_direction_id})
        data = OrderUtils.format_data_response(order)
        return Response(json.dumps(
            data
        ),
            status=200, content_type='application/json')

    @http.route('/api/store/cart/delivery', type='http', auth='public',
                methods=['PATCH'], csrf=False, cors='*')
    @validate_api_static_token
    @validate_jwt
    def update_delivery_order(self, **post):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        order_id = data.get('order_id')
        city_id = data.get('city_id')
        delivery_id = data.get('address_delivery_id')
        if not order_id:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'El parámetro "order_id" es obligatorio',
                    'data': None
                }
            ), status=400, content_type='application/json')
        order = request.env['sale.order'].sudo().search([
            ('id', '=', int(order_id)),
            ('state', '=', 'draft'),
            ('website_id', '=', 1)
        ], limit=1)

        if not order:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'La orden no fue encontrada, o ya fue procesada',
                    'data': None
                }
            ), status=404, content_type='application/json')

        if not delivery_id:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'El parámetro "delivery_id" es obligatorio',
                    'data': None
                }
            ), status=400, content_type='application/json')

        warehouse_id = request.env['stock.warehouse'].sudo().search([
            ('city_id', '=', city_id),
            ('app_mobile_warehouse', '=', True)
        ], limit=1)

        if not warehouse_id:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'No se encontró un almacén asociado a la ciudad',
                    'data': None
                }
            ), status=404, content_type='application/json')
        # calcular la distancia
        delivery = request.env['res.partner'].sudo().search([
            ('id', '=', int(delivery_id)),
        ], limit=1)
        if not delivery.exists():
            order.sudo().write({'partner_shipping_id': False, 'address_delivery_calculate': '',
                                "ubication_url": ''})
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'La Dirección de envio no fue encontrada',
                    'data': None
                }
            ), status=404, content_type='application/json')
        delivery_info = OrderUtils.is_point_in_ecuador(delivery.partner_latitude,
                                                       delivery.partner_longitude)
        if not delivery_info:
            order.sudo().write({'partner_shipping_id': False, 'address_delivery_calculate': '',
                                'ubication_url': ''})
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'No existe cobertura de envíos en la dirección seleccionada',
                    'data': None
                }
            ), status=400, content_type='application/json')
        url_destination_map = f"https://www.google.com/maps/dir/?api=1&destination={delivery.partner_latitude},{delivery.partner_longitude}&travelmode=driving"
        order.sudo().write(
            {
                'address_delivery_calculate': f"{delivery.ref}-{delivery.street}- {delivery.street2} ,{delivery.partner_latitude},{delivery.partner_longitude}",
                "partner_shipping_id": delivery.id, 'ubication_url': url_destination_map})
        # agrega el producto de envio
        shipping_product = request.env['product.product'].sudo().search(
            [('default_code', '=', 'ENVIOSAPPMOVIL'),
             ('detailed_type', '=', 'service')], limit=1
        )
        if not shipping_product.exists():
            # crear un producto de envio por defecto
            shipping_product = request.env[
                'product.product'].sudo().create({
                'name': 'Envio Estándar',
                'default_code': 'ENVIOSAPPMOVIL',
                'detailed_type': 'service',
                'list_price': 1.75,
                'id_database_old': 28262,
                'taxes_id': [(6, 0, [10])],
                'is_delivery_product': True,
            })
        latitud_origin = warehouse_id.x_lat
        longitude_origin = warehouse_id.x_long
        latitude_destination = delivery.partner_latitude
        longitude_destination = delivery.partner_longitude
        coords = [latitud_origin, longitude_origin, latitude_destination,
                  longitude_destination]
        # Calcular la distancia entre las coordenadas
        distance_km = calculate_distance(self, coords)

        # TODO REVISAR la DISTANCIa si es mayor a 10km usar servientrega
        if distance_km is False:
            order.sudo().write({'partner_shipping_id': False, "address_delivery_calculate": '',
                                'ubication_url': ''})
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'La dirección de envío está fuera del área de cobertura',
                }
            ), status=400, content_type='application/json')

        city_name = get_city_from_coords(
            latitude_destination, longitude_destination)

        try:
            if distance_km < 10 and city_name.get('province').strip() == 'Loja':
                price_delivery = order.calculate_delivery_price(
                    round(distance_km, 3))
                order.sudo().write({'distance_delivery': round(distance_km, 3)})
            elif distance_km > 10 and city_name.get('province').strip() == "Loja":
                # usar envios  a cantones de loja
                price_delivery = get_delivery_city(self, city_name.get(
                    'province').strip())
            else:
                price_delivery = get_delivery_city(self, city_name.get(
                    'province').strip())
        except Exception as e:
            _logger.info("Error al calcular el precio de envío", e)
            order.sudo().write({'partner_shipping_id': False, 'address_delivery_calculate': '',
                                'ubication_url': ''})
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'La dirección de envío está fuera del área de cobertura',
                }
            ), status=400, content_type='application/json')

        # Verificar si hay líneas de productos (excluyendo envío)
        product_lines = request.env['sale.order.line'].sudo().search([
            ('order_id', '=', order.id),
            ('product_id', '!=', shipping_product.id)
        ])

        shipping_line = request.env['sale.order.line'].sudo().search([
            ('order_id', '=', order.id),
            ('product_id', '=', shipping_product.id)
        ], limit=1)

        if product_lines:
            try:
                if shipping_line:
                    shipping_line.sudo().write(
                        {
                            'product_uom_qty': 1,
                            'price_unit': price_delivery.get('price'),
                            'name': shipping_product.name + ' ' + price_delivery.get(
                                'delivery_name'),
                            'is_delivery_product': True,
                            'tax_id': [(6, 0, [10])],
                        })
                else:
                    request.env['sale.order.line'].sudo().create({
                        'order_id': order.id,
                        'product_id': shipping_product.id,
                        'product_uom_qty': 1,
                        'name': shipping_product.name + ' ' + price_delivery.get(
                            'delivery_name'),
                        'price_unit': price_delivery.get('price'),
                        'tax_id': [(6, 0, [10])],
                        'is_delivery_product': True,
                    })
            except Exception as e:
                order.sudo().write({'partner_shipping_id': False, 'address_delivery_calculate': '',
                                    'ubication_url': ''})
                return Response(json.dumps(
                    {
                        'status': 'error',
                        'message': 'La dirección de envío está fuera del área de cobertura',
                    }
                ), status=400, content_type='application/json')
        elif shipping_line:
            shipping_line.sudo().unlink()

        # OrderUtils.apply_order_global_discount(order)
        data = OrderUtils.format_data_response(order)
        return Response(json.dumps(
            data
        ),
            status=200, content_type='application/json')


def calculate_distance(self, coords):
    lat_origin, long_origin = float(coords[0]), float(coords[1])
    lat_destine, long_destine = float(coords[2]), float(coords[3])
    mapbox_token = request.env['ir.config_parameter'].sudo().get_param(
        'mapbox_token')
    if not mapbox_token:
        return False
    base_url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{long_origin},{lat_origin};{long_destine},{lat_destine}?alternatives=false&geometries=geojson&overview=simplified&steps=false&notifications=none&access_token={mapbox_token}"
    response = requests.get(base_url)
    data = response.json()
    if 'routes' not in data or not data['routes']:
        return False
    distance = data['routes'][0]['distance']
    if distance is None or distance <= 0:
        return False
    return distance / 1000


def get_city_from_coords(lat, lon):
    mapbox_token = request.env['ir.config_parameter'].sudo().get_param(
        'mapbox_token')
    if not mapbox_token:
        return False
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json"
    params = {
        'access_token': mapbox_token,
        'types': 'place',
        'language': 'es'  # opcional
    }
    response = requests.get(url, params=params)
    data = response.json()

    if data.get('features'):
        return {
            "canton": data['features'][0]['place_name'].split(',')[0],
            "province": data['features'][0]['place_name'].split(',')[1],
        }
    return None


def get_delivery_city(self, city_name):
    city_id = request.env['res.country.state'].sudo().search([
        ('name', '=', city_name), ('country_id.name', '=', 'Ecuador')
    ], limit=1).id
    if not city_id:
        return False
    delivery_carriers = request.env['delivery.carrier'].sudo().search(
        [('state_ids', 'in', city_id)])
    delivery_carrier = delivery_carriers.sorted(key=lambda r: r.fixed_price,
                                                reverse=True)[:1]

    return {"price": delivery_carrier.fixed_price,
            "delivery_name": delivery_carrier.name}
