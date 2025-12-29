from odoo import http
from odoo.http import request, Response
import json
from .api_security import validate_api_static_token
from .jwt import validate_jwt
from .utils import OrderUtils


class ShippingAddressesControllerCustom(http.Controller):

    @http.route('/api/store/shipping_addresses/create', type='http',
                auth='public', methods=['POST'],
                csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def shipping_addresses_create(self, **kwargs):
        """
        5 cedula 6 ruc y 7 pasaporte
        """
        data = json.loads(request.httprequest.data.decode('utf-8'))
        customer_data = data.get('customer', {})
        address_type = customer_data.get("type")

        partner_id = customer_data.get('partner_id')
        vat = customer_data.get('vat')
        l10n_type_base = customer_data.get('l10n_latam_identification_type_id')

        if not partner_id or not vat:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'Debes proporcionar partner_id y vat',
                        "data": None
                    }
                ),
                status=404,
                content_type='application/json'
            )

        Partner = request.env['res.partner'].sudo()

        existing_partner = Partner.search([('id', '=', partner_id)])
        if not existing_partner:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'Datos no encontrados',
                        "data": None
                    }
                ),
                status=404,
                content_type='application/json'
            )

        partner_vals = {
            'name': customer_data.get('name'),
            'vat': vat,
            'email': customer_data.get('email'),
            'phone': customer_data.get('phone'),
            'mobile': customer_data.get('mobile'),
            'street': customer_data.get('street'),
            'street2': customer_data.get('street2'),
            # 'l10n_latam_identification_type_id': l10n_type,
            'partner_latitude': customer_data.get('partner_latitude'),
            'partner_longitude': customer_data.get('partner_longitude'),
            'type': address_type,
            # 'parent_id': partner_id,
            # 'parent_reference_id': partner_id if address_type == 'delivery' else None,
            'country_id': 63
        }
        if address_type == 'delivery':
            partner_latitude = customer_data.get('partner_latitude')
            partner_longitude = customer_data.get('partner_longitude')

            # veriffy si tiene latitud y longitud
            # delivery_info = OrderUtils.get_country_state_from_coords(partner_latitude, partner_longitude)
            delivery_info = OrderUtils.is_point_in_ecuador(partner_latitude, partner_longitude)
            # if not delivery_info or delivery_info.get('country') != 'Ecuador':
            if not delivery_info:
                # order.sudo().write({'partner_shipping_id': False})
                return Response(json.dumps(
                    {
                        'status': 'error',
                        'message': 'La dirección de envío debe estar dentro de Ecuador y tener coordenadas válidas.',
                        'data': None
                    }
                ), status=400, content_type='application/json')

            if not partner_latitude or not partner_longitude:
                return Response(
                    json.dumps(
                        {
                            'status': 'error',
                            'message': 'Debes proporcionar latitud y longitud',
                            "data": None
                        }
                    ),
                    status=400,
                    content_type='application/json'
                )

            partner_vals.update({'ref': customer_data.get('ref', ''), 'parent_id': int(partner_id),
                                 'vat': existing_partner.vat,
                                 'l10n_latam_identification_type_id': existing_partner.l10n_latam_identification_type_id.id, })
            partner = Partner.create(partner_vals)
            return Response(
                json.dumps(
                    {
                        'status': 'success',
                        'message': 'Dirección de envío agregada correctamente',
                        'data': {
                            'id': partner.id,
                            **partner_vals
                        }
                    }
                ),
                status=201,
                content_type='application/json'
            )

        else:
            #5 cedula 6 ruc y 7 pasaporte
            # print(l10n_type_base)
            # if int(l10n_type_base) == 7:
            #     l10n_type = 6
            # elif int(l10n_type_base) == 6:
            #     l10n_type = 4
            # else:
            #     l10n_type = l10n_type_base

            domain = [
                ('type', '=', 'invoice'),
                ('vat', '=', vat),
                # ('l10n_latam_identification_type_id', '=', l10n_type)
            ]
            partner_invoice = Partner.search(domain)
            if not partner_invoice:
                partner_vals.update({
                    'l10n_latam_identification_type_id': l10n_type_base,
                })
                partner = Partner.create(partner_vals)
                partner.sudo().write({
                    'type': 'invoice',
                    'commercial_partner_id': partner.id,
                    'parent_id': False,
                    'parent_reference_id': existing_partner.id,
                })

                return Response(
                    json.dumps(
                        {
                            'status': 'success',
                            'message': 'Dirección de facturación agregada correctamente',
                            'data': {
                                'id': partner.id,
                                **partner_vals
                            }
                        }
                    ),
                    status=201,
                    content_type='application/json'
                )
            else:

                return Response(
                    json.dumps(
                        {
                            'status': 'success',
                            'message': 'Ya esxiste una dirección de facturación con este VAT',
                            'data': partner_vals
                        }
                    ),
                    status=400,
                    content_type='application/json'
                )

    @http.route('/api/store/shipping_addresses/list/',
                type='http', auth='public', methods=['GET'],
                csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def shipping_addresses_read(self, **kwargs):
        partner_id = kwargs.get('partner_id')
        address_type = kwargs.get('type')
        partner = request.env['res.partner'].sudo().browse(int(partner_id))

        if not partner_id or not partner:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'partner_id es requerido',
                        "data": None

                    }
                ),
                status=400,
                content_type='application/json'
            )
        Partner = request.env['res.partner'].sudo()
        domain = []
        if address_type == 'invoice':
            domain.append(('type', 'in', ['invoice', 'contact']))
            domain.append(('active', '=', True))
            domain.append(('parent_reference_id', '=', int(partner_id)))
        else:
            domain.append(('type', '=', 'delivery',))
            domain.append(('active', '=', True))
            domain.append(('parent_id', '=', int(partner_id)))

        addresses = Partner.search(domain)

        # CREATE
        # INDEX
        # res_partner_parent_reference_id_idx
        # ON
        # res_partner(parent_reference_id);

        result = [{
            'id': addr.id,
            'name': addr.name,
            'type': addr.type,
            'street': addr.street,
            'street2': addr.street2,
            'email': addr.email,
            'phone': addr.phone,
            'mobile': addr.mobile,
            'vat': addr.vat,
            'l10n_latam_identification_type_id': addr.l10n_latam_identification_type_id.id,
            'partner_latitude': addr.partner_latitude,
            'partner_longitude': addr.partner_longitude,
            'ref': addr.ref,
        } for addr in addresses]
        if address_type == 'invoice':
            # agregar la direccion principal si no tiene direcciones de facturacion
            result.append({
                'id': partner.id,
                'name': partner.name,
                'type': 'invoice',
                'street': partner.street,
                'street2': partner.street2,
                'email': partner.email,
                'phone': partner.phone,
                'mobile': partner.mobile,
                'vat': partner.vat,
                'l10n_latam_identification_type_id': partner.l10n_latam_identification_type_id.id,
            })


        return Response(
            json.dumps(
                {
                    'status': 'success',
                    'message': 'Direcciones obtenidas correctamente',
                    'data': result
                }
            ),
            status=200,
            content_type='application/json'
        )

    @http.route('/api/store/shipping_addresses/edit', type='http',
                auth='public', methods=['POST'],
                csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def shipping_addresses_edit(self, **post):
        """
                5 cedula 6 ruc y 7 pasaporte
                """
        data = json.loads(request.httprequest.data.decode('utf-8'))
        address_id = data.get('id')
        address_type = data.get('type')
        if not address_id or not address_type:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'id y type son requeridos', "data": None,
                    }
                ),
                status=400,
                content_type='application/json'
            )
        Partner = request.env['res.partner'].sudo()
        address = Partner.browse(int(address_id))
        if not address.exists():
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'Dirección no encontrada',
                        'data': None
                    }
                ),
                status=404,
                content_type='application/json'
            )
        if address_type == 'delivery':
            updatable_fields = [
                'name', 'street', 'street2', 'email', 'phone', 'mobile', 'ref',
                'partner_latitude',
                'partner_longitude'
            ]
        else:
            updatable_fields = [
                'name', 'street', 'street2', 'email', 'phone', 'mobile',
            ]
        vals = {field: data[field] for field in updatable_fields if
                field in data}

        address.write(vals)
        #verificar si existe alguna orden con esa dirccion y desmarcarla
        try:
            order = request.env['sale.order'].sudo().search([
                ('is_order_app', '=', True),
                ('partner_shipping_id', '=', address.id),
                ('state', 'in', ['draft', 'sent'])
            ], limit=1)
            if order:

                order.sudo().write({'partner_shipping_id': False})
                shipping_product = request.env['product.product'].sudo().search(
                    [('default_code', '=', 'ENVIOSAPPMOVIL'),
                     ('detailed_type', '=', 'service')], limit=1
                )
                if shipping_product.exists():
                    shipping_line = request.env['sale.order.line'].sudo().search([
                        ('order_id', '=', order.id),
                        ('product_id', '=', shipping_product.id),
                    ], limit=1)
                    if shipping_line.exists():
                        shipping_line.unlink()
        except Exception as e:
            pass

        return Response(
            json.dumps(
                {
                    'status': 'success',
                    'message': 'Dirección actualizada correctamente',
                    'data': vals
                }
            ),
            status=200,
            content_type='application/json'
        )

    @http.route(
        '/api/store/shipping_addresses/delete/<int:shipping_address_id>',
        type='http', auth='public', methods=['POST'], csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def shipping_addresses_delete(self, shipping_address_id):
        partner = request.env['res.partner'].sudo().browse(shipping_address_id)

        if not partner.exists():
            return request.make_response(
                json.dumps(
                    {
                        "status": "error",
                        'message': 'Shipping address not found',
                        "data": None
                    }
                ),
                status=404,
                content_type='application/json'
            )

        try:
            partner.unlink()
            return request.make_response(
                json.dumps(
                    {
                        "status": "success",
                        'message': 'Dirección eliminada correctamente',
                        "data": None
                    }
                ),
                status=200,
                content_type='application/json'
            )
        except Exception as e:
            return request.make_response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "Error al eliminar la dirección:" + str(
                            e),
                        "data": None
                    }),
                status=500,
                content_type='application/json'
            )
