import requests

from odoo.http import request, _logger


class ProductUtils:
    @classmethod
    def _get_product_prices(cls, products, pricelist):
        """Calcula los precios de múltiples productos de una vez"""
        prices = {}
        price_rules = pricelist._compute_price_rule(products, 1)
        for product_id, rule_data in price_rules.items():
            prices[product_id] = "{:.2f}".format(round(rule_data[0], 2))
        return prices

    @classmethod
    def _prepare_product_data(cls, products, base_url, city_id=1413):
        product_data = []
        warehouse = request.env['stock.warehouse'].sudo().search([
            ('city_id', '=', city_id),
            ('app_mobile_warehouse', '=', True)
        ], limit=1)
        # Obtener todos los product.product relacionados en una sola consulta
        product_variants = request.env['product.product'].sudo().search([
            ('product_tmpl_id', 'in', products.ids)
        ])
        product_variant_map = {v.product_tmpl_id.id: v for v in product_variants}

        # Obtener todos los stock.quant en una sola consulta
        stock_quants = request.env['stock.quant'].sudo().search([
            ('product_id', 'in', product_variants.ids),
            ('location_id', 'child_of', warehouse.lot_stock_id.id),
            # ('quantity', '>', 0),
        ])
        quant_map = {}
        for q in stock_quants:
            #
            real_qty = q.quantity - q.reserved_quantity
            quant_map[q.product_id.id] = quant_map.get(q.product_id.id, 0.0) + real_qty
        # quant_map = {q.product_id.id: q.quantity for q in stock_quants}

        # Obtener todas las reglas de lealtad en una sola consulta
        loyalty_rules = request.env['loyalty.rule'].sudo().search([
            ('product_ids', 'in', product_variants.ids),
            ('program_id.active', '=', True),
            ('program_id.ecommerce_ok', '=', True),
        ])
        rewards = request.env['loyalty.reward'].sudo().search([
            ('program_id', 'in', loyalty_rules.mapped('program_id').ids)
        ])
        rewards_map = {}
        for rule in loyalty_rules:
            rewards_map[rule.id] = rewards.filtered(lambda r: r.program_id.id == rule.program_id.id)

        for product in products:

            product_id = product_variant_map.get(product.id)
            if not product_id:
                continue

            qty_available = quant_map.get(product_id.id, 0.0)
            # if qty_available <= 0:
            #     print(product_id)
            #     continue
            # Preparar promociones
            promotions = []
            product_rules = loyalty_rules.filtered(lambda r: product_id.id in r.product_ids.ids)
            for rule in product_rules:
                program = rule.program_id
                rewards_data = [{
                    'id': reward.id,
                    'name': reward.description,
                    'reward_type': reward.reward_type,
                    'reward_point_amount': rule.reward_point_amount,
                    'minimum_amount': rule.minimum_amount,
                    'reward_point_mode': rule.reward_point_mode,
                    'discount': reward.discount if reward.reward_type == 'discount' else None,
                    'product_id': reward.product_id.id if reward.reward_type == 'free_product' else None,
                    'required_points': reward.required_points
                } for reward in rewards_map.get(rule.id, [])]
                promotions.append({
                    'id': program.id,
                    'name': program.name,
                    'promotion_type': program.program_type,
                    'minimum_amount': rule.minimum_amount,
                    'minimum_qty': rule.minimum_qty,
                    'mode': rule.mode,
                    'rewards': rewards_data
                })

            # print(request.env['ir.attachment'].search([('res_model', '=', 'product.product')]))

            # Usar un campo de versión para imágenes
            image_version = product.write_date.strftime(
                "%Y%m%d%H%M%S") if product.write_date else 'default'
            if product.price_with_discount > 0:
                product_price_unit = product.price_with_discount
            else:
                product_price_unit = product.price_with_tax
            product_data.append({
                'id': product.id,
                'name': product.name,
                'uom': product.uom_po_id.name if product.sale_uom_ecommerce else product.uom_id.name,
                'qty_available': qty_available,
                'price_with_discount': product.price_with_discount,
                'price_with_tax': product.price_with_tax,
                'ecommerce_discount': product.ecommerce_discount,
                'discount_value': product.price_with_tax - product.price_with_discount,
                'list_price': round(product.list_price * product.uom_po_id.factor_inv,
                                    3) if product.sale_uom_ecommerce else product.list_price,
                'description_sale': product.description_sale or '',
                'description_ecommerce': product.description_ecommerce or '',
                'taxes': [{
                    'name': tax.display_name,
                    'amount_type': tax.amount_type,
                    'amount': tax.amount,
                } for tax in product.taxes_id],
                'category': [{
                    'id': category.id,
                    'name': category.name,
                    'parent_category_id': category.parent_id.id,
                    'parent_category_name': category.parent_id.name
                } for category in product.public_categ_ids],
                '128': f"{base_url}/web/image/product.product/{product_id.id}/image_128?version={image_version}",
                '256': f"{base_url}/web/image/product.product/{product_id.id}/image_256?version={image_version}",
                '512': f"{base_url}/web/image/product.product/{product_id.id}/image_512?version={image_version}",
                'promotions': promotions
            })

        product_data.sort(key=lambda x: x['name'])
        return product_data


class OrderUtils:
    @classmethod
    def format_data_response(cls, order):
        """Formatea los datos de la respuesta del pedido"""
        try:
            order_cancel_message = request.env['notification.message'].sudo().get_message_by_type(
                'order_canceled_text').body
        except:
            order_cancel_message = "Su pedido ha sido cancelado. Si tiene alguna pregunta, comuníquese con el soporte."

        items = []
        base_url = request.env['ir.config_parameter'].sudo().get_param(
            'web.base.url')
        address_delivery = None
        for line in order.order_line:
            product_id = request.env[
                'product.template'].sudo().search_read(
                [('id', '=', line.product_template_id.id)],
                ['id', 'name', 'ecommerce_discount', ])

            if line.reward_id.program_id.program_type == 'promotion':
                product_tmpl_ids = line.reward_id.program_id.rule_ids.mapped(
                    'valid_product_ids.product_tmpl_id.id') if line.reward_id and line.reward_id.program_id else []
            else:
                product_tmpl_ids = []
            items.append({
                'product_id': line.product_id.product_tmpl_id.id,
                'product_name': line.product_id.name if not line.is_global_discount else line.name,
                'description': line.name,
                'image_128': f"{base_url}/web/image/product.product/{line.product_id.id}/image_128" if line.product_id else None,
                'image_256': f"{base_url}/web/image/product.product/{line.product_id.id}/image_256" if line.product_id else None,
                'quantity': line.product_uom_qty,
                'price_unit': line.price_unit,
                'price_with_tax':line.product_id.price_with_tax,
                'is_reward_line': True if line.is_reward_line or line.is_global_discount else False,
                'ecommerce_discount': product_id[0][
                    'ecommerce_discount'] if product_id else 0,
                'discount': line.reward_id.discount,
                "reward_type": "discount" if line.is_global_discount else line.reward_id.reward_type,
                'product_uom': line.product_uom.name,
                'price_tax': line.price_tax,
                'total': line.price_total,
                'discount_value': line.discount or 0.0,
                'subtotal': line.price_subtotal,
                "reward_product_id": product_tmpl_ids[0] if product_tmpl_ids else None,
                'is_delivery_product': line.is_delivery_product,
                'is_claimed_reward': True if line.is_claimed_reward or line.is_global_discount else False,
                'taxes': [
                    {
                        'name': tax.display_name,
                        'amount_type': tax.amount_type,
                        'amount': tax.amount,
                    }
                    for tax in line.product_id.taxes_id
                ],
            })

        if order.partner_shipping_id:
            address_delivery = {
                'id': order.partner_shipping_id.id or None,
                'name': order.partner_shipping_id.name or None,
                'street': order.partner_shipping_id.street or None,
                'street2': order.partner_shipping_id.street2 or None,
                'mobile': order.partner_shipping_id.mobile or None,
                'partner_latitude': order.partner_shipping_id.partner_latitude or None,
                'partner_longitude': order.partner_shipping_id.partner_longitude or None,
                'ref': order.partner_shipping_id.ref or None,
            }
        order_state = order.check_order_payment_status(order.id)
        return {
            'status': 'success',
            'message': 'Producto agregado/actualizado en el carrito',
            "data": {
                'order_id': order.id,
                'order_status_text': order_state.get('payment_status'),
                'order_status': order.state,
                'order_cancel_message': order_cancel_message if order.state == 'sale' else None,
                'msg_status': order_state.get('msg_status'),
                'partner_id': order.partner_id.id,
                'subtotal': order.amount_untaxed,
                'total': order.amount_total,
                'tax': order.amount_tax,
                'currency': order.currency_id.name,
                'address_delivery': address_delivery,

                'address_invoice': {
                    'id': order.partner_invoice_id.id or None,
                    'vat': order.partner_invoice_id.vat or None,
                    'l10n_latam_identification_type_id': order.partner_invoice_id.l10n_latam_identification_type_id.id or None,
                    'l10n_latam_identification_type_name': order.partner_invoice_id.l10n_latam_identification_type_id.name or None,
                    'name': order.partner_invoice_id.name or None,
                    'street': order.partner_invoice_id.street or None,
                    'street2': order.partner_invoice_id.street2 or None,
                    'mobile': order.partner_invoice_id.mobile or None,
                    'email': order.partner_invoice_id.email or None,
                },
                'items': items
            }
        }

    @classmethod
    def apply_order_global_discount(cls, order, extra_percent=None):
        """
        Aplica (o revierte si extra_percent <= 0) un descuento adicional sobre
        el descuento ya presente en cada línea de la orden.
        - Borra la línea informativa si no existen líneas de producto.
        - Guarda el descuento original en `additional_original_discount`.
        - Marca `additional_discount_applied` para evitar reaplicar.
        """
        if not order:
            return

        institution_discount = request.env[
                                   'institution.client'].sudo().get_institution_discount_by_partner(
            order.partner_id.id
        ) or {}

        # si no se pasó explicitamente extra_percent, usar el valor institucional (si existe)
        if extra_percent is None:
            extra_percent = institution_discount.get('additional_discount_percentage', 0)

        try:
            percent = float(extra_percent or 0.0)
        except (TypeError, ValueError):
            percent = 0.0

        lines = order.order_line.filtered(
            lambda l: not l.is_global_discount
                      and not getattr(l, 'is_reward_line', False)
                      and not getattr(l, 'is_claimed_reward', False)
        )

        # Si no hay líneas de producto, eliminar cualquier línea informativa y salir
        if not lines:
            try:
                order.order_line.filtered(
                    lambda l: getattr(l, 'is_global_discount', False)).sudo().unlink()
            except Exception:
                pass
            return

        if percent <= 0.0:
            to_revert = lines.filtered(lambda l: getattr(l, 'additional_discount_applied', False))
            for line in to_revert:
                orig = float(getattr(line, 'additional_original_discount', 0.0) or 0.0)
                line.with_context(skip_global_discount_apply=True).sudo().write({
                    'discount': orig,
                    'additional_discount_applied': False,
                    'additional_discount_percent': 0.0,
                    'additional_original_discount': 0.0,
                })
            # además, eliminar cualquier línea informativa residual
            try:
                order.order_line.filtered(
                    lambda l: getattr(l, 'is_global_discount', False)).sudo().unlink()
            except Exception:
                pass
            return

        for line in lines:
            if getattr(line, 'additional_discount_applied', False):
                continue

            base_manual = float(line.discount or 0.0)

            tmpl = getattr(line.product_id, 'product_tmpl_id', None)
            mode = 'sequence'
            if tmpl:
                mode = getattr(tmpl, 'discount_combine_mode', 'sequence') or 'sequence'

            g = float(percent)
            if mode == 'add':
                final = base_manual + g
            else:  # sequence
                final = base_manual + g - (base_manual * g) / 100.0

            final = round(max(0.0, min(100.0, final)), 3)

            orig_discount = float(line.discount or 0.0)
            line.with_context(skip_global_discount_apply=True).sudo().write({
                'additional_original_discount': orig_discount,
                'discount': final,
                'additional_discount_applied': True,
                'additional_discount_percent': g,
            })

        # (El resto del código que crea la línea informativa permanece igual)
        try:
            product_tmpl = request.env['product.template'].sudo().search([
                ('default_code', '=', 'DESC-INST')
            ], limit=1)
            if not product_tmpl:
                product_tmpl = request.env['product.template'].sudo().create({
                    'name': "Desc. Institucional",
                    'type': 'service',
                    'default_code': 'DESC-INST',
                    'list_price': 0.0,
                    'standard_price': 0.0,
                    'sale_ok': True,
                    'id_database_old': '-999',
                    'purchase_ok': False,
                })

            try:
                prev_info_lines = order.order_line.filtered(
                    lambda
                        l: l.product_id and l.product_id.product_tmpl_id.id == product_tmpl.id and float(
                        l.price_unit or 0.0) == 0.0
                )
                if prev_info_lines:
                    prev_info_lines.sudo().unlink()
            except Exception:
                pass

            info_name = f"Desc. {institution_discount.get('institution_name', '')}  {percent}% Aplicado"
            request.env['sale.order.line'].sudo().create({
                'order_id': order.id,
                'name': info_name,
                'price_unit': 0.0,
                'product_uom_qty': 1,
                'product_uom': product_tmpl.uom_id.id,
                'product_id': product_tmpl.product_variant_id.id,
                'is_global_discount': True,
                'tax_id': [(6, 0, [10])],
            })
        except Exception as e:
            _logger.exception("Error al crear línea informativa de descuento institucional: %s", e)


    # creata a function to return country and state from coordinates
    @classmethod
    def get_country_state_from_coords(cls, lat, lon):
        mapbox_token = request.env['ir.config_parameter'].sudo().get_param(
            'mapbox_token')
        if not mapbox_token:
            return False
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json"
        params = {
            'access_token': mapbox_token,
            'types': 'country,region',
            'language': 'es'  # opcional
        }
        response = requests.get(url, params=params)
        data = response.json()

        country = None
        state = None

        for feature in data.get('features', []):
            if 'country' in feature['place_type']:
                country = feature['text']
            elif 'region' in feature['place_type']:
                state = feature['text']

        return {
            "country": country,
            "state": state
        }

    @classmethod
    def _point_in_polygon(cls, lon, lat, polygon):
        """Ray-casting algorithm: punto (lon,lat) en polígono (lista de (lon,lat))."""
        inside = False
        n = len(polygon)
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            # comprobar si el rayo cruza el segmento
            if ((y1 > lat) != (y2 > lat)) and (
                    lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-12) + x1):
                inside = not inside
        return inside

    @classmethod
    def is_point_in_ecuador(cls, lat, lon):
        """
        Devuelve True si (lat, lon) parece estar en Ecuador (continent + Galápagos),
        usando bounding box y polígonos simplificados.
        """
        # Quick bbox: si está muy fuera, devolver False rápido
        # Bbox que cubre continental + Galápagos con margen

        # Polígonos simplificados (coordenadas en (lon, lat)).
        # Atención: son aproximaciones para ejemplo, no fronteras oficiales.
        _ECUADOR_MAINLAND_POLY = [
            (-81.0, -4.8), (-80.5, -2.5), (-79.0, -1.5), (-78.0, 0.5),
            (-77.0, 1.4), (-76.0, 1.1), (-75.2, 1.2), (-75.2, 0.0),
            (-75.5, -1.5), (-76.5, -2.8), (-77.5, -4.0), (-78.9, -4.5),
            (-80.5, -5.0), (-81.0, -4.8)
        ]

        # Polígono amplio para Galápagos (aprox)
        _ECUADOR_GALAPAGOS_POLY = [
            (-92.5, 1.8), (-91.5, 1.8), (-90.5, 0.8), (-90.0, -1.8),
            (-91.5, -1.8), (-92.2, -0.5), (-92.5, 1.8)
        ]
        if not (-6.0 <= lat <= 3.0 and -93.0 <= lon <= -74.0):
            return False

        # Comprobar Galápagos bbox primero (rápido)
        if -92.8 <= lon <= -88.0 and -2.5 <= lat <= 2.5:
            if cls._point_in_polygon(lon, lat, _ECUADOR_GALAPAGOS_POLY):
                return True

        # Comprobar continente
        if -81.5 <= lon <= -75.0 and -6.0 <= lat <= 2.0:
            if cls._point_in_polygon(lon, lat, _ECUADOR_MAINLAND_POLY):
                return True

        return False
