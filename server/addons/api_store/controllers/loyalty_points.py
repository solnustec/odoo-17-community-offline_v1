import json

from .api_security import validate_api_static_token
from odoo import http
from odoo.http import request, Response
from .jwt import validate_jwt
from ..utils.time_cache import APICache


class LoyaltyAPI(http.Controller):
    # api_cache = APICache(timeout=3600, max_size=1000)

    @http.route('/api/store/loyalty/points/<int:partner_id>', type='http',
                auth='public',
                methods=['GET'], csrf=False)
    @validate_api_static_token
    def get_loyalty_cards(self, partner_id):
        """
        API para obtener todas las tarjetas de lealtad del cliente autenticado.
        Solo devuelve tarjetas de programas con app_mobile_ok=True.
        """
        # Obtener el usuario autenticado

        # Obtener el cliente asociado al usuario
        partner = partner_id
        if not partner:
            return Response(json.dumps(
                {
                    'status': 'error',
                    'message': 'No se encontró el cliente, intente de nuevo',
                    'data': None
                }
            ),
                status=404, content_type='application/json'
            )

        # Buscar tarjetas de lealtad del cliente, solo para programas con app_mobile_ok=True
        loyalty_cards = request.env['loyalty.card'].sudo().search([
            ('partner_id', '=', partner_id),
            ('program_id.app_ok', '=', True),
            # ('active', '=', True)
        ])

        # Preparar la respuesta
        cards_data = []
        for card in loyalty_cards:
            cards_data.append({
                'code': card.code,
                'program_name': card.program_id.name,
                'points': round(card.points, 2),
                'expiration_date': card.expiration_date if card.expiration_date else False,
            })

        return Response(json.dumps(
            {
                'status': 'success',
                'message': 'Tarjetas de lealtad obtenidas exitosamente',
                'data': cards_data
            }
        ), status=200, content_type='application/json'
        )

    @http.route('/api/store/loyalty/cupons/<int:partner_id>', auth='public',
                type='http', methods=['GET'])
    @validate_api_static_token
    def get_loyalty_rewards(self, **kwargs):
        partner_id = kwargs.get('partner_id')
        try:
            programs = request.env['loyalty.program'].sudo().search([
                ('program_type', '=', 'loyalty'),
                ('active', '=', True),
                ('app_ok', '=', True),
            ])

            if not programs:
                return http.Response(
                    json.dumps({
                        'status': 'error',
                        'message': 'No se encontraron programas de tarjetas de lealtad activos', 'data': []}),
                    content_type='application/json',
                    status=404
                )

            loyalty_cards = request.env['loyalty.card'].sudo().search_read([
                ('partner_id', '=', partner_id),
                ('program_id.app_ok', '=', True),
            ],['id','points'],limit=1)
            if not loyalty_cards:
                return http.Response(
                    json.dumps({
                        'status': 'success',
                        'message': 'El cliente no tiene una tarjeta de lealtad asociada a estos programas', 'programs': []}),
                    content_type='application/json',
                    status=200
                )
            if loyalty_cards and loyalty_cards[0].get('points', 0) <= 0:
                return http.Response(
                    json.dumps({
                        'status': 'error',
                        'message': 'El cliente no tiene puntos disponibles', 'programs': []}),
                    content_type='application/json',
                    status=404
                )

            program_list = []
            base_url = request.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')

            for program in programs:
                rewards = request.env['loyalty.reward'].sudo().search([
                    ('program_id', '=', program.id),
                    ('active', '=', True),
                ])


                reward_list = []
                for reward in rewards:
                    if reward.reward_type in ['discount', 'product',
                                              'shipping']:
                        if reward.required_points <= loyalty_cards[0].get('points', 0):
                            reward_data = {
                                'id': reward.id,
                                'description': reward.description or '',
                                'reward_type': reward.reward_type,
                                'required_points': reward.required_points,
                                'image_128': f"{base_url}/web/image/product.product/{reward.reward_product_id.id}/image_128" ,
                                'image_256': f"{base_url}/web/image/product.product/{reward.reward_product_id.id}/image_256" ,
                                'discount': reward.discount if reward.reward_type == 'discount' else 0.0,
                                'discount_mode': reward.discount_mode if reward.reward_type == 'discount' else '',
                                'discount_max_amount': reward.discount_max_amount if reward.reward_type == 'discount' else 0.0,
                                'product_ids': reward.reward_product_id.id if reward.reward_type == 'product' else [],
                                'free_shipping': reward.reward_type == 'free_shipping',
                            }
                            reward_list.append(reward_data)

                if reward_list:
                    program_data = {
                        'id': program.id,
                        'name': program.name,
                        'website_id': program.website_id.id if program.website_id else False,
                        'rewards': reward_list,
                    }
                    program_list.append(program_data)

            return http.Response(
                json.dumps({
                    'status': 'success',
                    'programs': program_list
                }),
                content_type='application/json',
                status=200
            )

        except Exception as e:
            return http.Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )

    @http.route('/api/store/claim_reward', type='http', auth='public',
                methods=['POST'], csrf=False)
    @validate_api_static_token
    @validate_jwt
    def claim_reward(self, **kwargs):
        try:
            jwt_data = getattr(request, '_jwt_data', {})
            user_id = jwt_data.get('user_id')
            data = json.loads(request.httprequest.data.decode('utf-8'))
            partner_id = data.get('partner_id')
            reward_id = data.get('reward_id')
            pos_order_id = data.get('order_id')

            if not all([partner_id, reward_id, pos_order_id]):
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'Todos los campos son obligatorios'
                }), status=400, content_type='application/json')

            # Obtener modelos
            Reward = request.env['loyalty.reward'].sudo()
            SaleOrder = request.env['sale.order'].sudo()

            # Buscar partne, recompensa y orden
            reward = Reward.browse(reward_id)
            sale_order = SaleOrder.search([('id', '=', pos_order_id), ('state', '=', 'draft')], limit=1)

            if not partner_id:
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'Cliente no encontrado'
                }), status=404, content_type='application/json')
            if not reward:
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'Recompensa no encontrada'
                }), status=404, content_type='application/json')
            if len(sale_order.order_line) == 0:
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'No se puede aplicar la recompensa, agregue un producto al carrito'
                }), status=400, content_type='application/json')
            if not sale_order.exists():
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'Orden no encontrada, no se puede aplicar la recompensa'
                }), status=404, content_type='application/json')

            # Verificar puntos disponibles
            loyalty_program = reward.program_id
            loyalty_card = request.env['loyalty.card'].sudo().search([
                ('partner_id', '=', partner_id),
                ('program_id', '=', loyalty_program.id)
            ], limit=1)

            if not loyalty_card:
                return Response(json.dumps({
                    'status': 'error',
                    'message': 'El cliente no tiene una tarjeta de lealtad asociada a este programa'
                }), status=404, content_type='application/json')

            if loyalty_card.points < reward.required_points:
                return Response(json.dumps({
                    'status': 'error',
                    'message': f'Puntos insuficientes. Necesitas {reward.required_points}, pero tienes {round(loyalty_card.points, 2)}'
                }), status=400, content_type='application/json')

            # Aplicar la recompensa a la orden
            # Aplicar la recompensa según el tipo
            if reward.reward_type == 'discount':
                # Seleccionar el primer producto de descuento
                discount_product = reward.discount_line_product_id
                if not discount_product:
                    return Response(json.dumps({
                        'status': 'error',
                        'message': 'No se ha configurado un producto de descuento para esta recompensa'
                    }), status=404, content_type='application/json')

                # Calcular el monto del descuento
                discount_amount = reward.discount
                if reward.discount_mode == 'percent':
                    order_total = sum(line.price_subtotal for line in
                                      sale_order.order_line)
                    discount_amount = -(
                            order_total * reward.discount / 100)
                elif reward.discount_mode == 'fixed_amount':
                    discount_amount = -reward.discount

                sale_order.write({
                    'order_line': [(0, 0, {
                        'product_id': discount_product.id,
                        'name': f'Recompensa: {reward.description}',
                        'product_uom_qty': 1,
                        'price_unit': discount_amount,
                        'is_claimed_reward': True,
                        'tax_id': [(6, 0, [10])],
                    })]
                })
                loyalty_card.write(
                    {'points': loyalty_card.points - reward.required_points})

            elif reward.reward_type == 'product':
                # Agregar producto gratuito
                gift_product = reward.discount_line_product_id
                if not gift_product:
                    return Response(json.dumps({
                        'status': 'error',
                        'message': 'No se ha configurado un producto gratuito para esta recompensa'
                    }), status=400, content_type='application/json')

                sale_order.write({
                    'order_line': [(0, 0, {
                        'product_id': gift_product.id,
                        'name': f'Recompensa: {reward.description}',
                        'product_uom_qty': 1,
                        'price_unit': 0,
                        'is_claimed_reward': True,
                        'tax_id': [(6, 0, [10])],
                    })]
                })

                loyalty_card.write(
                    {'points': loyalty_card.points - reward.required_points})

            elif reward.reward_type == 'shipping':
                # Aplicar envío gratuito
                sale_order.write({
                    'order_line': [(0, 0, {
                        'product_id': reward.discount_line_product_id.id,
                        'name': f'Recompensa: Envío Gratuito ({reward.description})',
                        'product_uom_qty': 1,
                        'price_unit': 0,
                        'tax_id': [(6, 0, [10])],
                        'is_claimed_reward': True,
                        # Sin impuestos para envío gratuito
                    })]
                })
                sale_order.remove_shipping_product_line(sale_order.order_line)
                loyalty_card.write(
                    {'points': loyalty_card.points - reward.required_points})

            try:
                message_record = request.env[
                    'notification.message'].sudo().get_message_by_type(
                    'reward_claimed')
                if '{{recompensa}}' in message_record.body:
                    body = message_record.body.replace('{{recompensa}}', reward.description)
                else:
                    body = message_record.body
                request.env['user.notification'].sudo().create({
                    'name': message_record.title,
                    'user_id': user_id,
                    'message': f"{body}",
                })
                request.env['firebase.service']._send_single_push_notification(user_id=user_id, title=message_record.title, body=body)
            except Exception as e:
                pass

            return Response(json.dumps({
                'status': 'success',
                'message': 'Recompensa aplicada exitosamente'

            }), status=200, content_type='application/json')

        except Exception as e:
            return Response(json.dumps({
                'status': 'error',
                'message': str(e)
            }), status=500, content_type='application/json')
