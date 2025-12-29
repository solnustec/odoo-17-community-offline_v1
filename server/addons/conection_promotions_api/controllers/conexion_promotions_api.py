from datetime import datetime

from odoo import http
from odoo.http import request
import json


class PromotionsUpdateApi(http.Controller):

    @http.route('/api/loyalty-program/update', type='json', auth='public',
                methods=['POST'], csrf=False)
    def update_discount_promotions(self, **kwargs):
        # json de envio

        # {
        #     "product_discounts": [
        #         {"product_id": 19417, "discount": 11.0}
        #     ]
        # }
        data = json.loads(request.httprequest.data)

        # Expecting a list of objects with product_id and discount
        product_discount_list = data.get('product_discounts', [])

        if not product_discount_list or not isinstance(product_discount_list,
                                                       list):
            return {
                'error': 'No se proporcionaron descuentos de productos o el formato es inválido'}

        results = []
        for item in product_discount_list:
            product_id = item.get('product_id')
            discount = item.get('discount')

            # Validate inputs
            if not product_id:
                results.append({'product_id': None,
                                'error': 'No se proporcionó ID de producto'})
                continue
            if not isinstance(discount, (int, float)):
                results.append({'product_id': product_id, 'error': 'Valor de descuento inválido'})
                continue

            # Buscar producto
            product = request.env['product.product'].sudo().search([
                ('product_tmpl_id.id_database_old', '=', product_id)
            ], limit=1)
            if not product:
                results.append({'product_id': product_id, 'error': 'ID de producto inválido'})
                continue

            # Buscar programas de lealtad (sin limit=1 para procesar todos)
            loyalty_programs = request.env['loyalty.program'].sudo().search([
                ('reward_ids.discount_product_ids', 'in', [product.id]),
                ('active', '=', True),
                ('program_type', '!=', 'coupons'),
                '|',
                '&', ('applies_to_the_second', '=', True), ('reward_ids.is_main', '=', False),
                ('applies_to_the_second', '=', False),
            ])

            if not loyalty_programs and discount != 0:
                # Caso: No existe programa de lealtad, crear uno nuevo con una recompensa de descuento y una regla
                loyalty_program = request.env['loyalty.program'].sudo().create({
                    'name': f'Create-Discount-{product.product_tmpl_id.name}',
                    'program_type': 'promotion',
                    'pos_ok': True,
                    'sale_ok': False,
                    'ecommerce_ok': False,
                    'active': True,
                    'trigger': 'auto',
                })
                # Crear la recompensa de descuento
                reward = request.env['loyalty.reward'].sudo().create({
                    'program_id': loyalty_program.id,
                    'reward_type': 'discount',
                    'discount': discount,
                    'discount_applicability': 'specific',
                    'required_points': 0,
                    'discount_product_ids': [(6, 0, [product.id])],
                })
                reward._compute_description()
                loyalty_program.sudo().write({
                    'write_date': datetime.now(),
                })
                # Crear la regla para el programa
                request.env['loyalty.rule'].sudo().create({
                    'program_id': loyalty_program.id,
                    'minimum_qty': 1,
                    'minimum_amount': 0,
                    'reward_point_amount': 1,
                    'product_ids': [(6, 0, [product.id])],
                    'reward_point_mode': 'unit',
                })
                results.append({
                    'product_id': product_id,
                    'success': 'Programa de lealtad, recompensa de descuento y regla creados exitosamente'
                })
                continue
            elif not loyalty_programs:
                # No hay programa y el descuento es 0, no hacer nada
                results.append({
                    'product_id': product_id,
                    'error': 'No existe programa de lealtad y el descuento es 0'
                })
                continue

            # Procesar cada programa de lealtad
            for loyalty_program in loyalty_programs:

                # Obtener las recompensas del programa
                rewards = loyalty_program.reward_ids
                # discount_rewards = rewards.filtered(
                #     lambda r: r.reward_type == 'discount')
                discount_rewards = rewards.filtered(
                    lambda r: r.reward_type == 'discount' and (
                            not r.program_id.applies_to_the_second or not r.is_main
                    )
                )
                product_rewards = rewards.filtered(
                    lambda r: r.reward_type == 'product')

                if len(discount_rewards) == 1 and len(
                        rewards) == 1 and discount == 0:
                    # Caso 1: Solo hay una recompensa de tipo descuento y el descuento es 0
                    loyalty_program.sudo().write({'active': False})
                    results.append({
                        'product_id': product_id,
                        'success': f'Programa de lealtad {loyalty_program.name} desactivado porque el descuento es 0 y solo existe una recompensa'
                    })

                    if loyalty_program.ecommerce_ok:
                        loyalty_program.sudo().write({
                            'write_date': datetime.now(),
                        })

                    continue

                if discount != 0:
                    if discount_rewards:
                        # Caso 2: Existe una recompensa de descuento y el descuento no es 0, actualizar
                        discount_rewards.sudo().write({'discount': discount})
                        discount_rewards._compute_description()
                        results.append({
                            'product_id': product_id,
                            'success': f'Descuento del programa de lealtad {loyalty_program.name} actualizado exitosamente'
                        })
                    else:

                        if loyalty_program.ecommerce_ok and len(product_rewards) == 1:
                            continue

                        # Caso 3: No existe recompensa de descuento, crear una nueva
                        reward = request.env['loyalty.reward'].sudo().create({
                            'program_id': loyalty_program.id,
                            'reward_type': 'discount',
                            'discount': discount,
                            'discount_applicability': 'specific',
                            'required_points': 0,
                            'discount_product_ids': [(6, 0, [product.id])],
                        })
                        reward._compute_description()
                        results.append({
                            'product_id': product_id,
                            'success': f'Recompensa de descuento del programa de lealtad {loyalty_program.name} creada exitosamente'
                        })

                    if loyalty_program.ecommerce_ok:
                        loyalty_program.sudo().write({
                            'write_date': datetime.now(),
                        })

                    continue

                if discount == 0 and len(rewards) > 1 and discount_rewards:
                    # Caso 4: Descuento es 0, hay más de una recompensa, eliminar la recompensa de descuento
                    discount_rewards.unlink()
                    results.append({
                        'product_id': product_id,
                        'success': f'Recompensa de descuento del programa de lealtad {loyalty_program.name} eliminada porque el descuento es 0 y existen múltiples recompensas'
                    })
                    continue

                results.append({
                    'product_id': product_id,
                    'error': f'No se realizó ninguna acción para el programa de lealtad {loyalty_program.name}, caso o configuración inválida'
                })

        return {'results': results}
