
from odoo.http import Controller, route, request
import json

class PosLoyaltyController(Controller):
    @route('/pos/loyalty_data', type='json', auth='public')
    def load_loyalty_data(self):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        product_ids = data.get('product_ids', {})

        if not product_ids:
            return {'error': 'No product IDs provided'}

        # Buscar productos
        products = request.env['product.product'].browse(product_ids)
        if not products:
            return {'error': 'Invalid product IDs'}

        pos_session = request.env['pos.session']

        loyalty_program = request.env['loyalty.program'].search([
            '|',
            ('rule_ids.product_ids', 'in', product_ids),
            ('reward_ids.discount_product_ids', 'in', product_ids),
            ('pos_ok', '=', True),
            ('active', '=', True),
        ])

        if not loyalty_program:
            return {'error': 'No loyalty programs found for the provided products'}

        try:
            # Obtener datos de lealtad
            loyalty_programs = pos_session._get_pos_ui_loyalty_program({
                'search_params': {
                    'domain': [('id', 'in', loyalty_program.ids)],
                    'fields': [
                        'name', 'trigger', 'applies_on', 'program_type', 'pricelist_ids', 'date_from',
                        'date_to', 'limit_usage', 'max_usage', 'is_nominative', 'portal_visible',
                        'portal_point_name', 'trigger_product_ids', 'is_selection_promotion', 'mandatory_promotion',
                        'note_promotion', 'limit_for_order', 'applies_by_boxes', 'applies_to_the_second',
                        'max_boxes_limit'
                    ],
                },
            })

            loyalty_rules = pos_session._get_pos_ui_loyalty_rule({
                'search_params': {
                    'domain': [('program_id', 'in', loyalty_program.ids)],
                    'fields': ['program_id', 'valid_product_ids', 'any_product', 'currency_id',
                               'reward_point_amount', 'reward_point_split', 'reward_point_mode',
                               'minimum_qty', 'minimum_amount', 'minimum_amount_tax_mode', 'mode', 'code'],
                },
            })

            loyalty_rewards = pos_session._get_pos_ui_loyalty_reward({
                'search_params': {
                    'domain': [('program_id', 'in', loyalty_program.ids)],
                    'fields': ['description', 'program_id', 'reward_type', 'required_points', 'clear_wallet',
                               'currency_id',
                               'discount', 'discount_mode', 'discount_applicability', 'all_discount_product_ids',
                               'is_global_discount','discount_product_ids', 'date_from', 'date_to',
                               'discount_max_amount', 'discount_line_product_id',
                               'multi_product', 'reward_product_ids', 'reward_product_qty', 'reward_product_uom_id',
                               'reward_product_domain', 'is_main'],
                },
            })

            reward_product_ids = set()
            for reward in loyalty_rewards:
                if 'discount_line_product_id' in reward and reward['discount_line_product_id']:
                    reward_product_ids.add(reward['discount_line_product_id'][0])
                if 'discount_product_ids' in reward and reward['discount_product_ids']:
                    reward_product_ids.update(reward['discount_product_ids'])
                if 'reward_product_ids' in reward and reward['reward_product_ids']:
                    reward_product_ids.update(reward['reward_product_ids'])

            reward_products = []
            if reward_product_ids:
                # Obtener parámetros del loader
                loader_params = pos_session._loader_params_product_product()
                search_params = loader_params['search_params']
                context = loader_params.get('context', {})

                domain = [('id', 'in', list(reward_product_ids))]

                reward_products = request.env['product.product'].with_context(**context).search_read(
                    domain=domain,
                    fields=search_params['fields'],
                    order=search_params['order']
                )

                pos_session._process_pos_ui_product_product(reward_products)

            return {
                'loyalty_program': loyalty_programs,
                'loyalty_rule': loyalty_rules,
                'loyalty_reward': loyalty_rewards,
                'reward_products': reward_products,
            }

        except Exception as e:
            return {'error': str(e)}



    @route('/pos/general_coupons', type='json', auth='public')
    def load_general_coupons(self):
        """
        Carga cupones que aplican a todos los productos
        (sin product_ids específicos en las reglas)
        """
        try:
            pos_session = request.env['pos.session']

            # Buscar directamente cupones sin product_ids en sus reglas
            # Primero obtenemos las reglas que NO tienen productos específicos
            rules_without_products = request.env['loyalty.rule'].search([
                ('product_ids', '=', False)
            ])

            if not rules_without_products:
                return {'error': 'No se encontraron cupones que apliquen para todos los productos'}

            # Obtener los programas de esas reglas que sean cupones activos y para POS
            loyalty_programs = request.env['loyalty.program'].search([
                ('id', 'in', rules_without_products.mapped('program_id').ids),
                ('program_type', '=', 'coupons'),
                ('pos_ok', '=', True),
                ('active', '=', True),
            ])

            if not loyalty_programs:
                return {'error': 'No se encontraron cupones generales activos'}

            general_coupon_ids = loyalty_programs.ids

            # Obtener datos de los programas de lealtad
            loyalty_programs_data = pos_session._get_pos_ui_loyalty_program({
                'search_params': {
                    'domain': [('id', 'in', general_coupon_ids)],
                    'fields': [
                        'name', 'trigger', 'applies_on', 'program_type', 'pricelist_ids', 'date_from',
                        'date_to', 'limit_usage', 'max_usage', 'is_nominative', 'portal_visible',
                        'portal_point_name', 'trigger_product_ids', 'is_selection_promotion', 'mandatory_promotion',
                        'note_promotion', 'limit_for_order', 'applies_by_boxes', 'max_boxes_limit'
                    ],
                },
            })

            # Obtener reglas de lealtad
            loyalty_rules = pos_session._get_pos_ui_loyalty_rule({
                'search_params': {
                    'domain': [('program_id', 'in', general_coupon_ids)],
                    'fields': [
                        'program_id', 'valid_product_ids', 'any_product', 'currency_id',
                        'reward_point_amount', 'reward_point_split', 'reward_point_mode',
                        'minimum_qty', 'minimum_amount', 'minimum_amount_tax_mode', 'mode', 'code'
                    ],
                },
            })

            # Obtener recompensas
            loyalty_rewards = pos_session._get_pos_ui_loyalty_reward({
                'search_params': {
                    'domain': [('program_id', 'in', general_coupon_ids)],
                    'fields': [
                        'description', 'program_id', 'reward_type', 'required_points', 'clear_wallet',
                        'currency_id', 'discount', 'discount_mode', 'discount_applicability',
                        'all_discount_product_ids', 'is_global_discount', 'discount_product_ids',
                        'discount_max_amount', 'discount_line_product_id', 'multi_product',
                        'reward_product_ids', 'reward_product_qty', 'reward_product_uom_id',
                        'reward_product_domain', 'is_main'
                    ],
                },
            })

            # Recopilar IDs de productos de recompensa
            reward_product_ids = set()
            for reward in loyalty_rewards:
                if 'discount_line_product_id' in reward and reward['discount_line_product_id']:
                    reward_product_ids.add(reward['discount_line_product_id'][0])
                if 'discount_product_ids' in reward and reward['discount_product_ids']:
                    reward_product_ids.update(reward['discount_product_ids'])
                if 'reward_product_ids' in reward and reward['reward_product_ids']:
                    reward_product_ids.update(reward['reward_product_ids'])

            # Obtener productos de recompensa
            reward_products = []
            if reward_product_ids:
                loader_params = pos_session._loader_params_product_product()
                search_params = loader_params['search_params']
                context = loader_params.get('context', {})

                domain = [('id', 'in', list(reward_product_ids))]

                reward_products = request.env['product.product'].with_context(**context).search_read(
                    domain=domain,
                    fields=search_params['fields'],
                    order=search_params['order']
                )

                pos_session._process_pos_ui_product_product(reward_products)

            return {
                'loyalty_program': loyalty_programs_data,
                'loyalty_rule': loyalty_rules,
                'loyalty_reward': loyalty_rewards,
                'reward_products': reward_products,
                'total_coupons': len(general_coupon_ids)
            }

        except Exception as e:
            return {'error': f'Error al cargar cupones: {str(e)}'}