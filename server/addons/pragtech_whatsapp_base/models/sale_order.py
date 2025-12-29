from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from decimal import Decimal, ROUND_HALF_UP
import requests
import logging
import json
from odoo import models, fields, api
import re
from ..templates.meta_api import MetaAPi
from ..utils.user_session import UserSession
from odoo.tools import float_is_zero
from collections import defaultdict

_logger = logging.getLogger(__name__)


class SaleOrderChatbot(models.Model):
    _inherit = 'sale.order'

    # dev_reference = fields.Char(string='Referencia Comercial')

    is_order_chatbot = fields.Boolean(
        string="Es una orden del Chatbot",
        help="Se marca automáticamente si x_channel='canal digital' y digital_media='chatbot'."
    )

    x_channel = fields.Char(string="Canal ", required=False)
    digital_media = fields.Char(string='Medio digital', index=True)

    x_modo_compra = fields.Selection(
        [
            ('compra_asesor', 'Compra asistida'),
            ('compra_auto', 'Compra automática'),
        ],
        string="Modo de compra",
        required=False,
        default=False,
    )

    x_numero_chatbot = fields.Char(string="Número usuario", required=False)

    x_tipo_pago = fields.Selection(
        [
            ('Ahorita!', 'Ahorita!'),
            ('Deuna!', 'Deuna!'),
            ('Tarjeta', 'Tarjeta'),
            ('Efectivo', 'Efectivo'),
            ('Transferencia', 'Transferencia'),
            ('CHEQUE/TRANSF', 'CHEQUE/TRANSF')
        ],
        string="Tipo de pago", required=False, default=False,
    )

    x_tipo_entrega = fields.Selection(
        [
            ('Domicilio', 'Domicilio'),
            ('Retiro local', 'Retiro local'),
        ],
        string='Tipo de entrega',
        help="Tipo de entrega para la orden del chatbot",
    )

    x_direccion_entrega = fields.Char(string="Dirección de entrega desde el chatbot", required=False)
    ubication_url = fields.Char(string="Dirección envío en url", required=False)

    type_delivery = fields.Selection(
        [
            ('clipp', 'Clipp'),
            ('express', 'Express'),
        ],
        string='Empresa de motorizado',
        help="Tipo de motorizado para la orden del chatbot"
    )

    # card_info = fields.Text(string='Información de la tarjeta',
    # help='Aquí se almacena TODO el JSON recibido desde la pasarela')

    pay_deuna_id = fields.Char(
        string='ID Pago Deuna',
        help="ID del pago realizado a través de Deuna",
        index=True
    )

    pay_ahorita_id = fields.Char(
        string='ID Pago Ahorita',
        help="ID del pago realizado a través de Ahorita",
        index=True
    )

    transaction_id = fields.Char(string='ID Transacción', required=False, index=True)

    def action_summary_chatbot(self):
        self.ensure_one()

        if not self.x_numero_chatbot:
            return self._notify_error("No hay número de WhatsApp en la orden")

        numero_limpio = re.sub(r'\D', '', self.x_numero_chatbot)
        chatbot_session = self.env['whatsapp.chatbot'].sudo().search([
            ('number', '=', numero_limpio)
        ], limit=1, order='id DESC')

        sale_order = request.env['sale.order'].sudo().browse(self.id)

        if not chatbot_session:
            return self._notify_error(f"No hay sesión activa para {numero_limpio}")

        numero = chatbot_session.number.replace('+', '').replace(' ', '')

        try:
            orden_data = json.loads(chatbot_session.orden) if chatbot_session.orden else {}
        except json.JSONDecodeError:
            orden_data = {}
        if not sale_order.exists():
            MetaAPi.enviar_mensaje_texto(numero, "⚠️ Orden no encontrada.")
            return

        partner = sale_order.partner_id
        tipo_envio = sale_order.x_tipo_entrega
        tipo_pago = sale_order.x_tipo_pago
        direccion_factura = partner.street or ""
        documento = partner.vat or ""
        tipo_documento = "Cédula" if len(documento) == 10 else "RUC"

        # Construir mensaje
        mensaje = (
            f"*Resumen de tu Orden*\n\n"
            f"*Cliente:* {partner.name}\n"
            f"*Documento:* {tipo_documento} {documento}\n"
            f"*Email:* {partner.email or '—'}\n"
            f"*Dirección Facturación:* {direccion_factura}\n\n"
            f"*Método de Pago:* {tipo_pago}\n"
            f"*Tipo de Envío:* {tipo_envio}\n"
        )

        if tipo_envio.lower() == "domicilio":
            link = ""
            if chatbot_session and chatbot_session.orden:
                try:
                    link = orden_data.get('link_direccion_gps', '')
                except Exception as e:
                    _logger.error(f"Error leyendo link_direccion_gps del chatbot: {str(e)}")

            if link:
                mensaje += f"*Dirección de Entrega:* {link}\n"

        mensaje += "\n*Productos:*\n"
        descuentos_totales = 0.0

        tipo_compra = sale_order.x_modo_compra or ''

        if tipo_compra == "compra_auto":
            for line in sale_order.order_line.filtered(lambda l: l.product_id and not l.is_delivery):
                tmpl = line.product_id.product_tmpl_id
                subtotal_linea = tmpl.price_with_tax or 0.0
                subtotal_linea_desc = tmpl.price_with_discount or 0.0
                descuento = line.discount or 0
                if line.price_subtotal > 0:
                    if descuento > 0 and descuento < 100:
                        mensaje += f"➡ {int(line.product_uom_qty)}x {line.product_id.name}: ~${subtotal_linea:.2f}~ → ${subtotal_linea_desc:.2f}\n"
                    else:
                        mensaje += f"➡ {int(line.product_uom_qty)}x {line.product_id.name}: ${subtotal_linea:.2f}\n"
                if descuento == 100:
                    mensaje += f"➡ {int(line.product_uom_qty)}x {line.product_id.name} _(Producto Gratis)_\n"
                else:
                    descuentos_totales += line.price_subtotal
        elif tipo_compra == "compra_asesor":
            lines = sale_order.order_line.filtered(
                lambda l: not getattr(l, 'is_delivery', False) and not l.display_type
            )
            currency = sale_order.currency_id
            prec = currency.rounding

            def keyify(s):
                s = re.sub(r'\[.*?\]\s*', '', s or '')
                return ' '.join(s.lower().strip().split())

            base_lines, promo_lines = [], []
            for l in lines:
                is_reward = (
                        getattr(l, 'is_reward_line', False)
                        or float_is_zero(l.price_total, precision_rounding=prec)
                        or float_is_zero(l.price_unit, precision_rounding=prec)
                        or l.price_unit < 0.0
                        or l.price_total < 0.0
                )
                (promo_lines if is_reward else base_lines).append(l)

            base_index = []
            for b in base_lines:
                keys = {
                    keyify(b.product_id.name),
                    keyify(b.product_id.display_name or ''),
                    keyify((b.name or '').splitlines()[0]),
                }
                base_index.append((b, {k for k in keys if k}))

            def find_base_for(text):
                t = keyify(text)
                best = None
                for b, keys in base_index:
                    for k in keys:
                        if k and (k in t or t in k):
                            if not best or len(k) > best[0]:
                                best = (len(k), b)
                return best[1] if best else None

            discounts_total = defaultdict(float)
            freebies = defaultdict(list)

            for p in promo_lines:
                name = p.name or ''
                nl = name.lower()
                target = name
                if 'producto gratis -' in nl:
                    target = name.split('-', 1)[-1].strip()
                elif ' en ' in nl:  # "22% en NOMBRE"
                    target = name.split(' en ', 1)[-1].strip()

                base = find_base_for(target)

                is_free = (
                        float_is_zero(p.price_total, precision_rounding=prec)
                        or float_is_zero(p.price_unit, precision_rounding=prec)
                        or (p.discount == 100)
                )

                if is_free:
                    nm = (p.product_id.name or target).strip()
                    (freebies[base.id] if base else freebies[0]).append((int(p.product_uom_qty), nm))
                else:
                    discount_line = discounts_total[base.id] if base else discounts_total[0]
                    discount_line += p.price_total  # negativo
                    if base:
                        discounts_total[base.id] = discount_line
                    else:
                        discounts_total[0] = discount_line

            for b in base_lines:
                base_total = b.price_total  # con IVA
                disc = discounts_total.get(b.id, 0.0)
                if not float_is_zero(disc, precision_rounding=prec):
                    nuevo_total = base_total + disc
                    mensaje += (
                        f"➡ {int(b.product_uom_qty)}x {b.product_id.name}: "
                        f"~${base_total:.2f}~ → ${nuevo_total:.2f}\n"
                    )

                else:
                    mensaje += f"➡ {int(b.product_uom_qty)}x {b.product_id.name}: ${base_total:.2f}\n"

                for qty, nm in freebies.get(b.id, []):
                    mensaje += f"➡ {qty}x {nm}\n"

            for qty, nm in freebies.get(0, []):
                mensaje += f"➡ {qty}x {nm}\n"

        envio_line = sale_order.order_line.filtered(lambda l: l.is_delivery)
        if envio_line:
            mensaje += f"\n*Precio envío:* ${envio_line.price_subtotal:.2f}"

        # subtotales
        mensaje += (
            f"\n*Subtotal:* ${sale_order.amount_untaxed:.2f}"
        )

        # Totales
        mensaje += (
            f"\n*IVA:* ${sale_order.amount_tax:.2f}\n"
            f"*Total a Pagar:* *${sale_order.amount_total:.2f}*"
        )

        # Enviar
        MetaAPi.enviar_mensaje_texto(numero, mensaje)
        UserSession(request.env).update_session(numero, state="confirmar_orden_factura")
        MetaAPi.botones_confirmar_compra(numero)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Enviado!',
                'message': 'Resumen enviado correctamente por WhatsApp',
                'type': 'success',
                'sticky': False,
            }
        }

    def _notify_error(self, msg):
        self.message_post(body=f"Error WhatsApp: {msg}")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Error',
                'message': msg,
                'type': 'danger',
                'sticky': True,
            }
        }

    def action_dispatch_chatbot(self):
        self.ensure_one()

        numero_limpio = re.sub(r'\D', '', self.x_numero_chatbot)

        MetaAPi.enviar_mensaje_texto(numero_limpio, "Su pedido esta en camino, Gracias por preferirnos 😊.")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Enviado!',
                'message': 'Mensaje de despacho enviado correctamente por WhatsApp',
                'type': 'success',
                'sticky': False,
            }
        }

    def send_message_whatsapp(self, id, number):
        self.ensure_one()
        sale_order_id = id
        numero_chatbot = number
        chatbot_session = request.env['whatsapp.chatbot'].sudo().search([('number', '=', numero_chatbot)], limit=1)

        if chatbot_session:
            orden_data = json.loads(chatbot_session.orden or "{}")
            orden_data["sale_order_id"] = sale_order_id
            chatbot_session.update({
                'orden': json.dumps(orden_data)
            })

        # ConversationFlow.handle_order_by_asesor(self, numero_chatbot, sale_order_id)
        # Import local para evitar ciclo models <-> templates
        from ..templates.conversation_flow import ConversationFlow
        ConversationFlow.handle_order_by_asesor(self, numero_chatbot, sale_order_id)
        return {'id': sale_order_id, 'numero_chatbot': numero_chatbot}

    def action_confirm(self):
        """ Confirm the given quotation(s) and set their confirmation date.

        If the corresponding setting is enabled, also locks the Sale Order.

        :return: True
        :rtype: bool
        :raise: UserError if trying to confirm cancelled SO's
        """
        res = True

        for order in self:
            if not order.is_order_chatbot:
                res = super().action_confirm()

        self.order_line._validate_analytic_distribution()

        for order in self:
            order.validate_taxes_on_sales_order()
            if order.partner_id in order.message_partner_ids:
                continue
            order.message_subscribe([order.partner_id.id])

            # Validate coupons and rewards
            all_coupons = order.applied_coupon_ids | order.coupon_point_ids.coupon_id | order.order_line.coupon_id
            if any(order._get_real_points_for_coupon(coupon) < 0 for coupon in all_coupons):
                raise ValidationError(_('One or more rewards on the sale order is invalid. Please check them.'))

            # Skip reward updates if context flag is set or free product promotion is detected
            skip_rewards_update = self.env.context.get('skip_rewards_update', False)
            if not skip_rewards_update and not order.is_order_chatbot:
                # Optionally, add check for free product promotion
                is_free_product_promo = any(line.is_reward_line for line in order.order_line)
                if not is_free_product_promo:
                    order._update_programs_and_rewards()

        self.write(self._prepare_confirmation_values())

        # Context key 'default_name' is sometimes propagated up to here.
        # We don't need it and it creates issues in the creation of linked records.
        context = self._context.copy()
        context.pop('default_name', None)

        self.with_context(context)._action_confirm()

        self.filtered(lambda so: so._should_be_locked()).action_lock()

        if self.env.context.get('send_email'):
            self._send_order_confirmation_mail()

        return res

    def write(self, vals):
        result = super().write(vals)

        if 'type_delivery' in vals:
            for order in self:
                # Buscar el registro de log relacionado
                log = self.env['chatbot_message.delivery'].sudo().search([
                    ('sale_order_id', '=', order.id)
                ], limit=1)
                if log:
                    log.write({'type_delivery': vals['type_delivery']})
        return result

    @api.model
    def create(self, vals):
        website = self.env['website'].get_current_website()
        if website and vals.get('website_id') == website.id:
            vals.setdefault('x_tipo_pago', 'Tarjeta')
            vals.setdefault('x_channel', 'canal digital')
            vals.setdefault('digital_media', 'web')
        return super(SaleOrderChatbot, self).create(vals)

    @classmethod
    def get_data_order(cls, sale_order_id):
        sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
        if not sale_order.exists():
            return {'error': 'Orden no encontrada'}

        total = Decimal(sale_order.amount_total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        warehouse = sale_order.warehouse_id

        # Obtener el ID de la bodega que representa el punto de venta digital
        point_of_sale_id = warehouse.id_digital_payment if warehouse else None

        if not point_of_sale_id:
            return {'error': 'No se ha configurado un punto de venta digital para esta orden'}

        payload = {
            'amount': float(total),
            'point_of_sale_id': point_of_sale_id,
        }

        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        endpoint = f"{base_url}/deuna/canal_digital/payment/request"

        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers
            )

            response_data = response.json()

            if response_data.get('result', {}).get('status') == '1':
                if 'transactionId' in response_data.get('result', {}):
                    sale_order.write({
                        'pay_deuna_id': response_data['result']['transactionId']})
                return response_data['result']
            else:
                error_msg = response_data.get('error', response.text)
                _logger.error(f"Error en la API Deuna: {error_msg}")
                return {'error': error_msg}

        except Exception as e:
            _logger.error(f"Error al conectar con la API Deuna: {str(e)}")
            return {'error': str(e)}

    def change_salesperson(self, new_user_id):
        """
        Permite cambiar el vendedor (user_id) de una orden.

        Este método puede ser usado por:
        - Usuarios internos con el grupo 'Cambiar Vendedor en Órdenes'
        - Usuarios portal (para sus propias órdenes)

        Solo permite modificar el campo user_id por seguridad.

        :param new_user_id: ID del nuevo usuario/vendedor
        :return: dict con resultado de la operación
        """
        self.ensure_one()

        # Verificar que el usuario actual tiene permisos
        current_user = self.env.user
        has_change_salesperson_group = current_user.has_group('pragtech_whatsapp_base.group_change_salesperson')
        is_portal = current_user.has_group('base.group_portal')
        is_sales_user = current_user.has_group('sales_team.group_sale_salesman')

        if not (has_change_salesperson_group or is_portal or is_sales_user):
            return {
                'success': False,
                'error': 'No tiene permisos para cambiar el vendedor'
            }

        # Validar que el usuario destino existe y es un vendedor válido
        new_user = self.env['res.users'].sudo().browse(new_user_id)
        if not new_user.exists():
            return {
                'success': False,
                'error': 'El usuario especificado no existe'
            }

        # Verificar que el usuario destino tiene permisos de venta
        sales_group = self.env.ref('sales_team.group_sale_salesman', raise_if_not_found=False)
        if sales_group and sales_group not in new_user.groups_id:
            return {
                'success': False,
                'error': 'El usuario especificado no tiene permisos de vendedor'
            }

        try:
            # Usar sudo() para permitir la escritura
            self.sudo().write({'user_id': new_user_id})


            return {
                'success': True,
                'message': f'Vendedor cambiado a {new_user.name}',
                'order_id': self.id,
                'new_user_id': new_user_id,
                'new_user_name': new_user.name
            }
        except Exception as e:
            _logger.error(f"Error al cambiar vendedor de orden {self.name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    # Alias para compatibilidad con código existente
    def portal_change_salesperson(self, new_user_id):
        """Alias de change_salesperson para compatibilidad."""
        return self.change_salesperson(new_user_id)

    @api.model
    def get_available_salespersons(self):
        """
        Retorna lista de vendedores disponibles para usuarios portal.

        :return: lista de dicts con id y name de cada vendedor
        """
        sales_group = self.env.ref('sales_team.group_sale_salesman', raise_if_not_found=False)

        if sales_group:
            users = self.env['res.users'].sudo().search([
                ('groups_id', 'in', [sales_group.id]),
                ('active', '=', True)
            ])
        else:
            # Fallback: usuarios internos activos
            users = self.env['res.users'].sudo().search([
                ('share', '=', False),
                ('active', '=', True)
            ])

        return [{'id': u.id, 'name': u.name} for u in users]
