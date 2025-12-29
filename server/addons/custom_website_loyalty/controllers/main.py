import logging
from odoo import fields
from odoo.osv import expression
from odoo.addons.website_sale.controllers.main import WebsiteSale as WebsiteSaleBase
from odoo import http
from odoo.http import Controller, route, request
from werkzeug.exceptions import Forbidden
import json
from datetime import datetime


_logger = logging.getLogger(__name__)


class WebsiteLoyaltyController(Controller):
    @route('/website/loyalty_data', type='json', auth='public')
    def load_loyalty_data(self):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            products = data.get('products', [])
            if not products:
                return {'error': 'No product data provided'}
            product_prices = [
                str(p['product_id'])
                for p in products
            ]
            current_datetime = datetime.now()
            loyalty_programs = request.env['loyalty.program'].sudo().search([
                ('rule_ids.product_ids', 'in', product_prices),
                ('ecommerce_ok', '=', True),
                ('trigger', '=', 'auto'),
                '|', ('date_from', '=', False),
                ('date_from', '<=', current_datetime),
                '|', ('date_to', '=', False),
                ('date_to', '>=', current_datetime),
            ])
            if not loyalty_programs:
                return {
                    'error': 'No loyalty programs found for the provided products',
                    'status': '404'}
            rewards_data = []
            for program in loyalty_programs:
                if not self.validate_rules_and_rewards(program.rule_ids,
                                                       program.reward_ids):
                    continue
                for reward in program.reward_ids:
                    discount_product_id = str(
                        reward.discount_product_ids[:1].id)
                    product_id = request.env['product.product'].sudo().search(
                        [('id', '=', int(discount_product_id))],
                        limit=1
                    )

                    price_unit = product_id.list_price * product_id.uom_po_id.factor_inv if product_id.sale_uom_ecommerce else product_id.list_price
                    taxes = product_id.taxes_id.compute_all(
                        price_unit,
                        quantity=1,
                        product=product_id)
                    price_with_taxes = taxes['total_included']
                    original_price = price_with_taxes if product_id.sale_uom_ecommerce else product_id.list_price
                    discounted_price = price_with_taxes - ((reward.discount / 100) * price_with_taxes)
                    discounted_price_rounded = round(discounted_price,2)
                    original_price_rounded = round(original_price,2)

                    rewards_data.append({
                        'discount_product_id': int(discount_product_id),
                        'discounted_price':
                            discounted_price_rounded,
                        'original_price': original_price_rounded,
                        'reward': reward.discount_line_product_id.id
                    })

            if not rewards_data:
                return {'error': 'No rewards found for valid loyalty programs',
                        'status': '404'}
            return {'rewards': rewards_data}

        except Exception as e:
            _logger.error(f"Error processing loyalty data: {e}", exc_info=True)
            return {'error': f'An error occurred: {str(e)}'}


    @route('/website/loyalty_data/point-of-sale', type='json', auth='public')
    def load_loyalty_data_pos(self):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            products = data.get('products', [])

            if not products:
                return {'error': 'No product data provided'}

            product_prices = {
                str(p['product_id']): float(p['price'])
                for p in products
                if float(p['price']) >= 0
            }

            product_ids = list(product_prices.keys())

            current_datetime = datetime.now()
            loyalty_programs = request.env['loyalty.program'].sudo().search([
                ('rule_ids.product_ids', 'in', product_ids),
                ('pos_ok', '=', True),
                ('trigger', '=', 'auto'),
                '|', ('date_from', '=', False),
                ('date_from', '<=', current_datetime),
                '|', ('date_to', '=', False),
                ('date_to', '>=', current_datetime),
            ])

            if not loyalty_programs:
                return {
                    'error': 'No loyalty programs found for the provided products',
                    'status': '404'}

            rewards_data = []
            for program in loyalty_programs:
                if not self.validate_rules_and_rewards(program.rule_ids,
                                                       program.reward_ids):
                    continue

                for reward in program.reward_ids:
                    discount_product_id = str(
                        reward.discount_product_ids[:1].id)
                    original_price = product_prices.get(discount_product_id)

                    if original_price:
                        rewards_data.append({
                            'discounted_price': reward.discount,
                        })

            if not rewards_data:
                return {'error': 'No rewards found for valid loyalty programs',
                        'status': '404'}

            return {'rewards': rewards_data}

        except Exception as e:
            _logger.error(f"Error processing loyalty data: {e}", exc_info=True)
            return {'error': f'An error occurred: {str(e)}'}

    def validate_rules_and_rewards(self, rules, rewards):

        if len(rules) != 1 or len(rewards) != 1:
            return False

        rule = rules[0]
        reward = rewards[0]

        if rule.minimum_qty != 1 or rule.reward_point_amount != reward.required_points:
            return False

        if reward.discount_mode != "percent" or reward.reward_type != 'discount':
            return False

        if rule.product_ids and reward.discount_product_ids:
            if rule.product_ids[0].id != reward.discount_product_ids[0].id:
                return False

        return True

    @route('/api/product/cart/discount', type='json', auth='public', methods=['POST'])
    def get_product_discount(self, **kwargs):

        api = request.env['product.template'].sudo()
        data = json.loads(request.httprequest.data.decode('utf-8'))

        product_tmpl_id = data.get('product_tmpl_id', False)
        product_uom_qty = data.get('product_uom_qty', False)

        if not product_tmpl_id or not product_uom_qty:
            return {
                'success': False,
                'error': 'product_tmpl_id y product_uom_qty son requeridos'
            }

        result = api.get_product_template_and_discount_id(product_tmpl_id, product_uom_qty)

        return {
            'success': True,
            'result': result
        }

    @route('/api/product/cart/discount/name', type='json', auth='public', methods=['POST'])
    def get_product_discount_name(self, **kwargs):

        api = request.env['product.template'].sudo()
        data = json.loads(request.httprequest.data.decode('utf-8'))

        product_tmpl_id = data.get('product_tmpl_id', False)
        product_uom_qty = data.get('product_uom_qty', False)

        if not product_tmpl_id or not product_uom_qty:
            return {
                'success': False,
                'error': 'product_tmpl_id y product_uom_qty son requeridos'
            }

        result = api.get_product_template_and_discount(product_tmpl_id, product_uom_qty)

        return {
            'success': True,
            'result': result
        }


class WebsiteSale(WebsiteSaleBase):

    def _shop_lookup_products(self, attrib_set, options, post, search, website):
        # 1) Búsqueda base (sin límite)
        product_count, details, fuzzy_search_term = website._search_with_fuzzy(
            "products_only",
            search,
            limit=None,
            order=self._get_search_order(post),
            options=options,
        )
        Product = request.env['product.template'].with_context(bin_size=True)
        base_rs = details[0].get('results', Product)

        # 2) Filtro de precio "mixto" con nueva lógica de prioridad
        min_price = options.get('min_price') or 0.0
        max_price = options.get('max_price') or 0.0

        if (min_price or max_price) and base_rs:
            # Monedas
            website_currency = options.get('display_currency') or website.currency_id
            company_currency = website.company_id.sudo().currency_id
            rate = options.get('conversion_rate') or request.env['res.currency']._get_conversion_rate(
                company_currency, website_currency, website.company_id, fields.Date.today()
            )
            rev = 1.0 / (rate or 1.0)  # pasar de moneda sitio -> moneda compañía

            comp_min = (min_price * rev) if min_price else None
            comp_max = (max_price * rev) if max_price else None

            # Grupo 1: sale_uom_ecommerce = True
            # Prioridad: price_with_discount > 0 ? price_with_discount : price_with_tax
            g1_discount = [('sale_uom_ecommerce', '=', True), ('price_with_discount', '>', 0)]
            if comp_min is not None:
                g1_discount.append(('price_with_discount', '>=', comp_min))
            if comp_max is not None:
                g1_discount.append(('price_with_discount', '<=', comp_max))

            g1_tax = [('sale_uom_ecommerce', '=', True), ('price_with_discount', '=', 0)]
            if comp_min is not None:
                g1_tax.append(('price_with_tax', '>=', comp_min))
            if comp_max is not None:
                g1_tax.append(('price_with_tax', '<=', comp_max))

            # Grupo 2: sale_uom_ecommerce = False
            # Mismo comportamiento: price_with_discount > 0 ? price_with_discount : price_with_tax
            g2_discount = [('sale_uom_ecommerce', '=', False), ('price_with_discount', '>', 0)]
            if comp_min is not None:
                g2_discount.append(('price_with_discount', '>=', comp_min))
            if comp_max is not None:
                g2_discount.append(('price_with_discount', '<=', comp_max))

            g2_tax = [('sale_uom_ecommerce', '=', False), ('price_with_discount', '=', 0)]
            if comp_min is not None:
                g2_tax.append(('price_with_tax', '>=', comp_min))
            if comp_max is not None:
                g2_tax.append(('price_with_tax', '<=', comp_max))

            # Dominio final combinando todos los casos
            dom = expression.AND([
                [('id', 'in', base_rs.ids)],
                expression.OR([g1_discount, g1_tax, g2_discount, g2_tax]),
            ])

            # 3) Recalcular conteo y resultados (orden respetando el del shop)
            product_count = Product.search_count(dom)
            search_result = Product.search(dom, order=self._get_search_order(post)).with_context(bin_size=True)
        else:
            search_result = base_rs.with_context(bin_size=True)

        return fuzzy_search_term, product_count, search_result


    def _checkout_form_save(self, mode, checkout, all_values):
        Partner = request.env['res.partner']

        if mode[0] == 'new':
            partner_model = Partner.sudo().with_context(tracking_disable=True)

            partner_exist = None
            if checkout.get('vat'):
                partner_exist = partner_model.search([('vat', '=', checkout['vat'])], limit=1)

            # Crear o actualizar partner
            if partner_exist:
                partner_exist.write(checkout)
                partner_id = partner_exist.id
            else:
                partner_id = partner_model.create(checkout).id

        elif mode[0] == 'edit':
            partner_id = int(all_values.get('partner_id', 0))
            if partner_id:
                # double check
                order = request.website.sale_get_order()
                shippings = Partner.sudo().search([("id", "child_of", order.partner_id.commercial_partner_id.ids)])
                if partner_id not in shippings.mapped('id') and partner_id != order.partner_id.id:
                    return Forbidden()
                Partner.browse(partner_id).sudo().write(checkout)
        return partner_id

    def _get_search_order(self, post):
        # OrderBy will be parsed in orm and so no direct sql injection
        # id is added to be sure that order is a unique sort key
        order = post.get('order') or request.env['website'].get_current_website().shop_default_sort

        if 'list_price' in order:
            order = order.replace('list_price', 'price_with_tax')

        return 'is_published desc, %s, id desc' % order


    @http.route(['/shop/address'], type='http', auth="public",
                website=True, methods=['GET', 'POST'], csrf=False)
    def address(self, **post):
        # --- GET: mostrar formulario exactamente como el core ---
        if request.httprequest.method == 'GET':
            return super().address(**post)

        # --- POST: dejar que el core cree/edite la dirección de envio---
        super().address(**post)

        # --- NUEVO PROCESO: Asignar metodo de entrega de acuerdo a la direccion de envio---
        order = request.website.sale_get_order()
        if not order:
            return request.redirect('/shop/payment')
        order = order.sudo()

        if hasattr(order, '_get_delivery_methods'):
            carriers = order._get_delivery_methods()
        else:
            carriers = request.env['delivery.carrier'].sudo()
        if not carriers:
            return request.redirect('/shop/checkout?step=addresses')

        carrier = carriers.sorted('sequence')[0]

        if hasattr(order, '_remove_delivery_line'):
            order._remove_delivery_line()
        else:
            order.order_line.filtered('is_delivery').unlink()

        order.write({'carrier_id': carrier.id})

        rate = carrier.rate_shipment(order)
        if isinstance(rate, dict) and rate.get('success'):
            amount = rate.get('price', 0.0)
            order.set_delivery_line(carrier, amount)
        else:
            for alt in carriers.sorted('sequence')[1:]:
                order.write({'carrier_id': alt.id})
                rate = alt.rate_shipment(order)
                if isinstance(rate, dict) and rate.get('success'):
                    order.set_delivery_line(alt, rate.get('price', 0.0))
                    break
        return request.redirect('/shop/payment')