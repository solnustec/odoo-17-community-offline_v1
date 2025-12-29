import base64

import pytz

from .api_security import validate_api_static_token
from odoo import http
from odoo.http import request, Response
import json
from datetime import datetime, date

from .jwt import validate_jwt


class PurchaseOrderControllerCustom(http.Controller):

    @http.route("/api/store/orders", type="http",
                auth="public",
                methods=["GET"], cors="*")
    @validate_api_static_token
    def get_orders_history(self, **kwargs):
        partner_id = kwargs.get("partner_id")
        sale_orders = request.env['sale.order'].sudo().search([
            ('partner_id', '=', int(partner_id)),
            ('state', 'in', ['sale','shipped']), ('is_order_app', '=', True)
        ])


        if not sale_orders:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "No se encontraron órdenes para este cliente",
                    "data": []
                }),
                content_type='application/json', status=400)
        base_url = request.env['ir.config_parameter'].sudo().get_param(
            'web.base.url')
        sale_orders_list = []
        for sale_order in sale_orders:
            payment= sale_order.check_order_payment_status(sale_order.id)
            sale_orders_list.append({
                'id': sale_order.id,
                'name': sale_order.name,
                'amount_tax': sale_order.amount_tax,
                'state': sale_order.state,
                'amount_untaxed': sale_order.amount_untaxed,
                'amount_total': sale_order.amount_total,
                'create_date': sale_order.create_date.strftime(
                    '%Y-%m-%d %H:%M:%S'),
                'pdf': f"{base_url}{sale_order.access_url}",
                "payment_status": payment.get('payment_status', 'En proceso'),
                "delivery_status": "Entregado a Motorizado" if sale_order.state == 'shipped' else "Pendiente de Envío",
            })

        return Response(
            json.dumps(
                {
                    "status": "success",
                    "message": "Orders retrieved successfully",
                    "data": sale_orders_list
                }
            ),
            status=200,
            content_type='application/json'
        )

    # def action_generate_open_invoice_url(self,order,base_url):
    #     # self.ensure_one()
    #     invoice = request.env['account.move'].sudo().search([
    #         ('invoice_origin', '=', order.name),
    #         ('move_type', 'in', ['out_invoice', 'out_refund']),
    #         ('state', '!=', 'cancel')
    #     ], limit=1)
    #
    #     if invoice:
    #         invoice._compute_access_url()
    #         return f"{base_url}{invoice.access_url}"
    #     else:
    #         raise f"{base_url}"

    @http.route("/api/store/order/<int:order_id>", type="http",
                auth="public",
                methods=["GET"], cors="*")
    @validate_api_static_token
    def get_order_by_id(self, order_id):

        sale_order = request.env['sale.order'].sudo().browse(order_id)

        if not sale_order.exists():
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "No se encontró la orden",
                    "data": []
                }),
                status=404,
                content_type='application/json'
            )

        sale_order_lines = request.env['sale.order.line'].sudo().search([
            ('order_id', '=', sale_order.id)
        ])

        product_ids = sale_order_lines.mapped('product_id').ids

        products = request.env['product.product'].sudo().search_read(
            [('id', 'in', product_ids)],
            ['id', 'name', 'image_1920']
        )

        product_data = {product['id']: product for product in products}

        base_url = request.env['ir.config_parameter'].sudo().get_param(
            'web.base.url')

        invoice_url = request.env['account.move'].sudo().search_read(
            [('invoice_origin', '=', sale_order.name)],
            ['id', 'access_token', 'state'], limit=1
        )

        url_for_invoice = ''
        url_for_invoice_download = ''
        state = ''

        if invoice_url:
            first_result = invoice_url[0]
            invoice_id = str(first_result['id'])
            invoice_token = first_result['access_token']
            state = first_result['state']
            url_for_invoice = (
                f"{base_url}/my/invoices/{invoice_id}?access_token={invoice_token}"
            )
            url_for_invoice_download = (
                f"{base_url}/my/invoices/{invoice_id}?access_token={invoice_token}"
                "&report_type=pdf&download=true"
            )

        list_products = [{
            'id': line.id,
            'product_id': line.product_id.id,
            'product_name': line.product_id.name,
            'product_qty': line.product_uom_qty,
            'price_unit': line.price_unit,
            'subtotal': line.price_subtotal,
            'tax': line.price_tax,
            'total': line.price_total,
            'image_128': f"{base_url}/web/image/product.product/{product_data[line.product_id.id]['id']}/image_128" if line.product_id.id in product_data else None,
            'image_256': f"{base_url}/web/image/product.product/{product_data[line.product_id.id]['id']}/image_256" if line.product_id.id in product_data else None,
        } for line in sale_order_lines]

        #order_payment
        payment_transactions = request.env['payment.transaction'].sudo().search([
            ('sale_order_ids', 'in', sale_order.id)
        ])
        payment_inf =[]
        for p in payment_transactions:
            payment_inf.append({
                'id': p.id,
                'amount': p.amount,
                'currency_id': p.currency_id.name,
                'payment_method_id': p.payment_method_id.name,
                'reference': p.reference,
                'state': p.state,
                'date': p.create_date.strftime('%Y-%m-%d %H:%M:%S'),
            })


        sale_orders_list = [{
            'id': sale_order.id,
            'name': sale_order.name,
            'amount_tax': sale_order.amount_tax,
            'amount_untaxed': sale_order.amount_untaxed,
            'amount_total': sale_order.amount_total,
            'partner_id': {
                'id': sale_order.partner_id.id,
                'name': sale_order.partner_id.name,
                'vat': sale_order.partner_id.vat or '',
                'type_vat': sale_order.partner_id.l10n_latam_identification_type_id.name
                if sale_order.partner_id.l10n_latam_identification_type_id else None,
                'email': sale_order.partner_id.email or '',
                'phone': sale_order.partner_id.phone or '',
                'mobile': sale_order.partner_id.mobile or '',
                'address': f"{sale_order.partner_id.street or ''}, {sale_order.partner_id.city or ''}, {sale_order.partner_id.state_id.name or ''}, {sale_order.partner_id.zip or ''}".strip(
                    ', '),
                'partner_latitude': f"{sale_order.partner_id.partner_latitude or ''}",
                'partner_longitude': f"{sale_order.partner_id.partner_longitude or ''}",
                'street': f"{sale_order.partner_id.street or ''}",
                'street2': f"{sale_order.partner_id.street2 or ''}",
                'contact_address': f"{sale_order.partner_id.contact_address or ''}",
                'ref': f"{sale_order.partner_id.ref or ''}",
            },
            'note': sale_order.note,
            'carrier_id': sale_order.carrier_id.id if sale_order.carrier_id else None,
            'create_date': sale_order.create_date.strftime(
                '%Y-%m-%d %H:%M:%S'),
            'list_products': list_products,
            'state_invoice': state,
            'url_for_invoice': url_for_invoice if state != 'cancel' else '',
            'url_for_invoice_download': url_for_invoice_download if state != 'cancel' else '',
            'payment_status': sale_order.check_order_payment_status(sale_order.id).get(
                'payment_status', 'En Proceso'),
            'delivery_status': "Entregado a Motorizado" if sale_order.state == 'shipped' else "Proceso de Envío",
            'payment_info':payment_inf
        }]

        return Response(
            json.dumps({
                "status": "success",
                "message": "Detalle de la orden recuperado exitosamente",
                "data": sale_orders_list
            }),

            status=200,
            content_type='application/json'
        )

    @http.route('/api/store/order/mark_paid', type='http', auth='public',
                methods=['POST'], csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def mark_order_paid(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        order_id = data.get('order_id')
        amount = float(data.get('amount', 0.0))
        payment_data = data.get('payment_data', {})

        order = request.env['sale.order'].sudo().browse(order_id)
        order.action_confirm()
        partner_id = order.partner_invoice_id.id
        partner = request.env['res.partner'].sudo().browse(partner_id)
        partner.sudo().write({
            'country_id': 63,  # Ecuador
        })

        # Generar factura
        invoice_id = order._create_invoices()

        # Crear factura en modo borrador
        sri_payment_method = request.env[
            'l10n_ec.sri.payment'].sudo().search(
            [('code', '=', 20)], limit=1).id

        # Configurar zona horaria de Ecuador
        ecuador_tz = pytz.timezone('America/Guayaquil')
        # Obtener la fecha actual en Ecuador
        invoice_date = datetime.now(ecuador_tz).date()
        update_vals = {
            'invoice_date': invoice_date,  # Fecha contable
            'l10n_ec_sri_payment_id': sri_payment_method,
        }
        invoice_id.sudo().write(update_vals)

        invoice_id.action_post()  # Validar la factura

        payment_provider_id = request.env['payment.provider'].sudo().search(
            [('name', '=', 'Paymentez')], limit=1)

        payment_method_id = request.env['payment.method'].sudo().search(
            [('code', '=', 'card'), ('active', '=', True)],
            limit=1).id

        payment_method_line = request.env[
            'account.payment.method.line'].sudo().search([
            ('journal_id', '=', payment_provider_id.journal_id.id),
            ('name', '=', 'Paymentez'),
        ], limit=1)

        payment_register = request.env[
            'account.payment.register'].with_context(
            active_model='account.move',
            active_ids=[invoice_id.id]
        ).sudo().create({
            'amount': amount,
            'payment_date': invoice_date,
            'journal_id': payment_provider_id.journal_id.id,
            'payment_method_line_id': payment_method_line.id,  # Método de pago
            'partner_id': order.partner_id.id,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'communication': invoice_id.name,  # Referencia de la factura
        })
        # Crear y validar el pago
        payment = payment_register._create_payments()

        # Crear transacción de pago
        request.env['payment.transaction'].sudo().create(
            {
                'amount': amount,
                'currency_id': order.currency_id.id,
                'payment_id': payment.id,
                'partner_id': order.partner_id.id,
                'payment_method_id': payment_method_id,
                'reference': order.name,
                'sale_order_ids': [(6, 0, [order.id])],
                'provider_id': payment_provider_id.id,
                "payment_json_data": json.dumps(payment_data),
                'state': 'done',
            })

        # Generar el access_token si no existe
        if not order.access_token:
            order._portal_ensure_token()

        # Construir la URL del PDF de la orden
        base_url = request.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', 'http://localhost:8069')
        pdf_url = f"{base_url}/my/orders/{order.id}?access_token={order.access_token}&report_type=pdf"
        # loyalty_program = request.env['loyalty.program'].sudo().search([],limit=1)
        # Opcional: Generar el PDF en base64 como respaldo
        # points = 0

        # if loyalty_program and hasattr(loyalty_program, 'compute_points'):
        #     points = loyalty_program.compute_points(order.amount_total)
        #     order.partner_id.loyalty_points += points

        try:
            jwt_data = getattr(request, '_jwt_data', {})
            user_id = jwt_data.get('user_id')
            request.env['user.notification'].sudo().create({
                'name': 'Orden Completada',
                'user_id': user_id,
                'message': f"Tu orden {order.name} ha sido pagada.",
            })
            request.env['user.notification'].sudo().create({
                'name': 'Puntos de Recompensa',
                'user_id': user_id,
                'message': f"Se te han asignado  puntos de recompensa.",
            })
            # enviar notificacion Firebase

            device = request.env['push.device'].find_by_user(user_id)
            request.env['firebase.service'].send_push_notification(
                registration_token=device.register_id,
                title="Orden Completada",
                body="Felicitaciones, Tu orden ha sido completada"
            )

        except Exception as e:
            print(e)
            pass

        return Response(
            json.dumps({
                "status": "success",
                "message": "Order pagada y puntos de recompensa asignados",
                "data": [
                    {
                        'order_id': order.id,
                        'points_awarded': 1,
                        'pdf_url': pdf_url
                    }
                ]
            }),
            status=200,
            content_type='application/json'
        )
