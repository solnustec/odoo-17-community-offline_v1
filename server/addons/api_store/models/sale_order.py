import itertools
import math
from collections import defaultdict

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression


from odoo.addons.sale_loyalty.models.sale_order import SaleOrder as SaleLoyaltySaleOrder

class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_order_app = fields.Boolean(string="Es una order del App", default=False)
    distance_delivery = fields.Float(
        string="Distancia de envió para el app",
        digits="Distancia Delivery Product",
        default=0.0
    )
    in_payment_process = fields.Boolean(
        string="En proceso de pago",
        default=False,
        help="Indica si la orden está en proceso de pago desde la app móvil."
    )
    # is_loyalty_error = fields.Boolean(
    #     string="Error de lealtad",
    #     default=False,
    #     help="Indica si hubo un error al aplicar recompensas de lealtad."
    # )
    partner_shipping_id = fields.Many2one(
        comodel_name='res.partner',
        string="Delivery Address",
        compute='_compute_partner_shipping_id',
        store=True, readonly=False, required=False, precompute=True,
        check_company=True,
        index='btree_not_null')
    address_delivery_calculate = fields.Char('Dirección de Envío')

    @api.model
    def _prepare_invoice(self):
        """Sobrescribe el metodo para asegurar que el partner de facturación sea el correcto en órdenes de la app móvil."""
        res = super(SaleOrder, self)._prepare_invoice()
        if self.is_order_app:
            res['partner_id'] = self.partner_invoice_id.id or self.partner_id.id
            if self.partner_invoice_id and self.partner_invoice_id.vat != self.partner_id.vat:
                pass  # No es necesario si el partner_id es correcto
        return res

    @api.model
    def check_order_payment_status(self, order_id):
        """
        Verifica si una orden de venta está pagada.
        :param order_id: ID de la orden de venta
        :return: Diccionario con el nombre de la orden y el estado de pago
        """
        order = self.env['sale.order'].browse(order_id)
        if not order.exists():
            return {'order_name': False, 'payment_status': 'Order not found'}

        # Busca transacciones de pago asociadas
        transactions = self.env['payment.transaction'].search([
            ('sale_order_ids', 'in', order.id),
            ('state', '=', 'done')
        ])

        payment_status = 'Pagada' if transactions else 'Tienes una orden pendiente de pago,'
        try:
            message = self.env['notification.message'].sudo().get_message_by_type('cart_confirmed')
            cart_message = message.body
        except Exception as e:
            cart_message = 'Tienes una orden pendiente de pago. Para agregar nuevos artículos al carrito, primero debes completar el pago de tu orden actual o cancelarla.'
            pass
        return {
            'order_name': order.name,
            'payment_status': payment_status,
            'msg_status': cart_message if not transactions else '',
        }

    state = fields.Selection(
        selection_add=[
            ('shipped', 'Enviado')
        ],
        string='Status',
        ondelete={
            'shipped': 'set default'
        },
        help="Estado de la orden de venta, incluyendo etapas personalizadas."
    )

    # def action_confirm(self):
    #     for order in self:
    #         all_coupons = order.applied_coupon_ids | order.coupon_point_ids.coupon_id | order.order_line.coupon_id
    #         if any(order._get_real_points_for_coupon(coupon) < 0 for coupon in all_coupons):
    #             raise ValidationError(_('One or more rewards on the sale order is invalid. Please check them.'))
    #         order._update_programs_and_rewards()
    #
    #     # Remove any coupon from 'current' program that don't claim any reward.
    #     # This is to avoid ghost coupons that are lost forever.
    #     # Claiming a reward for that program will require either an automated check or a manual input again.
    #     reward_coupons = self.order_line.coupon_id
    #
    #     self.coupon_point_ids.filtered(
    #         lambda pe: pe.coupon_id.program_id.applies_on == 'current' and pe.coupon_id not in reward_coupons
    #     ).coupon_id.sudo().unlink()
    #     # Add/remove the points to our coupons
    #     for coupon, change in self.filtered(lambda s: s.state != 'sale')._get_point_changes().items():
    #
    #         coupon.points += change
    #     res = super().action_confirm()
    #     self._send_reward_coupon_mail()
    #     return res

    def action_set_sent(self):
        """Acción para establecer el estado como 'Enviada'."""
        for order in self:
            if order.state != 'sale':
                raise UserError(
                    'Solo se puede marcar como "Enviada", cuando la orden este completada "Venta".'
                )
            # creat notification
            try:
                user_id = self.env['res.users'].sudo().search(
                    [('partner_id', '=', order.partner_id.id)], limit=1)
                message_record = self.env[
                    'notification.message'].sudo().get_message_by_type(
                    'order_shipped')
                self.env['user.notification'].sudo().create({
                    'name': message_record.title,
                    'user_id': user_id.id,
                    'message': f"{message_record.body}",
                })
                self.env['firebase.service']._send_single_push_notification(user_id=user_id.id,
                                                                            title=message_record.title,
                                                                            body=message_record.body)
            except Exception as e:
                pass

            # order.state = 'shipped'

    @api.depends('partner_id')
    def _compute_partner_shipping_id(self):
        for order in self:
            if not order.is_order_app:
                order.partner_shipping_id = \
                    order.partner_id.address_get(['delivery'])[
                        'delivery'] if order.partner_id else False

    def action_open_reward_wizard(self):
        self.ensure_one()
        self._update_programs_and_rewards()
        claimable_rewards = self._get_claimable_rewards()
        # Filtra las recompensas que no sean de tipo loyalty
        filtered_rewards = {
            coupon: [r for r in rewards if r.program_type != 'loyalty']
            for coupon, rewards in claimable_rewards.items()
        }
        # Elimina cupones sin recompensas tras el filtro
        filtered_rewards = {c: r for c, r in filtered_rewards.items() if r}

        if not filtered_rewards:
            return True

        needs_wizard = False
        for coupon, rewards in filtered_rewards.items():
            for r in rewards:
                # Si la recompensa necesita selección de productos, no la aplicamos aquí
                if r.multi_product:
                    needs_wizard = True
                    continue
                try:
                    # manejo especial para envío
                    if r.reward_type == 'shipping':
                        try:
                            self.remove_shipping_product_line(self.order_line)
                        except Exception:
                            pass
                    self._apply_program_reward(r, coupon)
                except Exception:
                    # silenciar errores individuales para seguir aplicando las demás
                    pass

        return not needs_wizard

    # def action_open_reward_wizard(self):
    #     self.ensure_one()
    #     self._update_programs_and_rewards()
    #     claimable_rewards = self._get_claimable_rewards()
    #     # Filtra las recompensas que no sean de tipo loyalty
    #     filtered_rewards = {
    #         coupon: [r for r in rewards if r.program_type != 'loyalty']
    #         for coupon, rewards in claimable_rewards.items()
    #     }
    #     # Elimina cupones sin recompensas tras el filtro
    #     filtered_rewards = {c: r for c, r in filtered_rewards.items() if r}
    #     if len(filtered_rewards) == 1:
    #         coupon = next(iter(filtered_rewards))
    #         rewards = filtered_rewards[coupon]
    #         if len(rewards) == 1 and not rewards[0].multi_product:
    #             self._apply_program_reward(rewards[0], coupon)
    #             return True
    #     elif not filtered_rewards:
    #         return True
    #     return False
    # Si hay loyalty, deja que el wizard lo gestione
    # return self.env['ir.actions.actions']._for_xml_id('sale_loyalty.sale_loyalty_reward_wizard_action')

    def apply_app_mobile_promotions(self):
        self.action_open_reward_wizard()
        # self.ensure_one()
        # self._update_programs_and_rewards()
        # claimable_rewards = self._get_claimable_rewards()
        # claimable_rewards = {
        #     coupon: [r for r in rewards if r.program_type != 'loyalty']
        #     for coupon, rewards in self._get_claimable_rewards().items()
        # }
        #
        # if not claimable_rewards:
        #     return True
        # coupon = next(iter(claimable_rewards))
        # rewards = claimable_rewards[coupon]
        #
        # # Filtra las recompensas que no sean de tipo loyalty
        # rewards_to_apply = [r for r in rewards if r.program_type != 'loyalty']
        #
        # if rewards_to_apply:
        #     for r in rewards_to_apply:
        #         if r.reward_type == 'shipping':
        #             try:
        #                 self.remove_shipping_product_line(self[0].order_line)
        #             except Exception:
        #                 pass
        #             self._apply_program_reward(r, coupon)
        #         else:
        #             self._apply_program_reward(r, coupon)
        # else:
        #     # Si solo hay loyalty, puedes dejarlo pasar o mostrar un mensaje
        #     pass
        # def apply_app_mobile_promotions(self):

    #
    #     self.ensure_one()
    #     self._update_programs_and_rewards()
    #     claimable_rewards = self._get_claimable_rewards()
    #
    #     if not claimable_rewards:
    #         return True
    #     coupon = next(iter(claimable_rewards))
    #     rewards = claimable_rewards[coupon]
    #
    #     if rewards and len(rewards) >= 1 and not rewards[0].multi_product:
    #         for r in rewards:
    #
    #             if r.reward_type == 'shipping':
    #                 # si el programa es de envío se elimina el producto de evio
    #                 try:
    #                     self.remove_shipping_product_line(self[0].order_line)
    #                 except Exception as e:
    #                     pass
    #                 self._apply_program_reward(r, coupon)
    #
    #             # sino se cimple ninguna de las anteriores se ejecutan las recompensas con normalidad
    #             #     self._apply_program_reward(r, coupon)
    #             elif r.program_type == 'loyalty':
    #                 # si el programa es de tarjetas de lealtad no se aplica
    #                 # self._apply_program_reward(r, coupon)
    #                 continue
    #             else:
    #                 self._apply_program_reward(r, coupon)

    def remove_shipping_product_line(self, order_lines):
        self.ensure_one()
        for line in order_lines:
            if line.product_id.default_code == 'ENVIOSAPPMOVIL':
                line.unlink()

    def has_lines(self):

        non_reward_lines = self.order_line.filtered(lambda line: not line.is_claimed_reward)
        return len(non_reward_lines)

    def has_claimed_reward_line(self):
        """
        Verifica si al menos una línea tiene is_claimed_reward = True

        Returns:
            bool: True si existe mínimo una línea con recompensa reclamada
        """
        return any(line.is_claimed_reward for line in self.order_line)

    def calculate_delivery_price(self, distancia_km):
        if distancia_km < 0:
            return {"price": False, "delivery_name": False}
        ICP = self.env['ir.config_parameter'].sudo()

        base_price = float(
            ICP.get_param('delivery.price.fixed_1km', default='1.75'))
        base_3km = float(
            ICP.get_param('delivery.price.base_over_3km', default='2'))
        extra_km_cost = float(
            ICP.get_param('delivery.price.per_km_over_3', default='0.40'))
        octavo_cost = float(
            ICP.get_param('delivery.price.per_0.125km', default='0.005'))
        delivery_name = ''
        if distancia_km <= 3:
            # delivery name
            delivery_name = 'CLIP'
            return {"price": base_price, "delivery_name": delivery_name}

        else:
            extra_distance = distancia_km - 3
            # toal distancia extra de los 3 km
            distance_km = int(extra_distance)
            total_extra_distance_km = distance_km * extra_km_cost
            fraction_km = extra_distance - distance_km
            increments = math.ceil(fraction_km / 0.125)
            increments_price = increments * octavo_cost
            price = base_3km + total_extra_distance_km + increments_price
            return {"price": round(price, 2), "delivery_name": delivery_name}

    # remove discount prodct if lines of products are 0
    # def remove_discount_product_if_no_lines(self):
    #     self.ensure_one()
    #     discount_product = self.env['product.product'].sudo().search([
    #         ('default_code', '=', 'DESC-INST')
    #     ], limit=1)
    #     if not discount_product:
    #         return
    #     # Filtra líneas que NO sean de descuento y NO sean recompensa/promo
    #     product_or_promo_lines = self.order_line.filtered(
    #         lambda l: l.product_id.id != discount_product.id and not l.is_claimed_reward
    #     )
    #     # Si no hay líneas de producto ni de promo, elimina la de descuento
    #     if not product_or_promo_lines:
    #         discount_line = self.order_line.filtered(lambda l: l.product_id.id == discount_product.id)
    #         discount_line.unlink()

    # def unlink(self):
    #     for order in self:
    #         if order.is_order_app:
    #             order.remove_discount_product_if_no_lines()
    #     res = super().unlink()
    #     return res


    # def action_confirm(self):
    #     # Si ya procesamos los cupones, no lo hacemos de nuevo
    #     if not self.env.context.get('loyalty_coupons_processed'):
    #         for order in self:
    #             existing_points = order.coupon_point_ids.filtered(lambda p: p.coupon_id.exists())
    #             all_coupons = order.applied_coupon_ids.exists() | existing_points.coupon_id | order.order_line.coupon_id.exists()
    #
    #             if any(order._get_real_points_for_coupon(coupon) < 0 for coupon in all_coupons):
    #                 raise ValidationError(_('One or more rewards on the sale order is invalid. Please check them.'))
    #             order._update_programs_and_rewards()
    #
    #         reward_coupons = self.order_line.coupon_id
    #
    #         points_to_delete = self.coupon_point_ids.filtered(
    #             lambda
    #                 pe: pe.coupon_id.exists() and pe.coupon_id.program_id.applies_on == 'current' and pe.coupon_id not in reward_coupons
    #         )
    #
    #         if points_to_delete:
    #             points_to_delete.coupon_id.sudo().unlink()
    #
    #         # Add/remove points
    #         for coupon, change in self.filtered(lambda s: s.state != 'sale')._get_point_changes().items():
    #             if coupon.exists():
    #                 coupon.points += change
    #
    #         self._send_reward_coupon_mail()
    #
    #     # Llamar al super CON el flag para que sale_loyalty no re-ejecute
    #     if not all(order._can_be_confirmed() for order in self):
    #         raise UserError(_(
    #             "The following orders are not in a state requiring confirmation: %s",
    #             ", ".join(self.mapped('display_name')),
    #         ))
    #
    #     self.order_line._validate_analytic_distribution()
    #
    #     for order in self:
    #         order.validate_taxes_on_sales_order()
    #         if order.partner_id in order.message_partner_ids:
    #             continue
    #         order.message_subscribe([order.partner_id.id])
    #
    #     self.write(self._prepare_confirmation_values())
    #
    #     # Context key 'default_name' is sometimes propagated up to here.
    #     # We don't need it and it creates issues in the creation of linked records.
    #     context = self._context.copy()
    #     context.pop('default_name', None)
    #     context.pop('default_user_id', None)
    #
    #     self.with_context(context)._action_confirm()
    #
    #     self.filtered(lambda so: so._should_be_locked()).action_lock()
    #
    #     if self.env.context.get('send_email'):
    #         self._send_order_confirmation_mail()
    #
    #     return True


    def _update_programs_and_rewards(self):
        """
        Updates applied programs's given points with the current state of the order.
        Checks automatic programs for applicability.
        Updates applied rewards using the new points and the current state of the order (for example with % discounts).
        """
        self.ensure_one()

        # +===================================================+
        # |       STEP 1: Retrieve all applicable programs    |
        # +===================================================+

        # Automatically load in eWallet and loyalty cards coupons with previously received points
        if self._allow_nominative_programs():
            loyalty_card = self.env['loyalty.card'].search([
                ('id', 'not in', self.applied_coupon_ids.ids),
                ('partner_id', '=', self.partner_id.id),
                ('points', '>', 0),
                '|', ('program_id.program_type', '=', 'ewallet'),
                     '&', ('program_id.program_type', '=', 'loyalty'),
                          ('program_id.applies_on', '!=', 'current'),
            ])

            if loyalty_card:
                self.applied_coupon_ids += loyalty_card

        # Programs that are applied to the order and count points
        points_programs = self._get_points_programs()
        # Coupon programs that require the program's rules to match but do not count for points
        coupon_programs = self.applied_coupon_ids.program_id
        # Programs that are automatic and not yet applied
        program_domain = self._get_program_domain()

        domain = expression.AND([program_domain, [('id', 'not in', points_programs.ids), ('trigger', '=', 'auto'), ('rule_ids.mode', '=', 'auto')]])
        automatic_programs = self.env['loyalty.program'].search(domain).filtered(lambda p:
            not p.limit_usage or p.total_order_count < p.max_usage)

        all_programs_to_check = points_programs | coupon_programs | automatic_programs
        all_coupons = self.coupon_point_ids.coupon_id | self.applied_coupon_ids
        # First basic check using the program_domain -> for example if a program gets archived mid quotation
        domain_matching_programs = all_programs_to_check.filtered_domain(program_domain)
        all_programs_status = {p: {'error': 'error'} for p in all_programs_to_check - domain_matching_programs}

        # Compute applicability and points given for all programs that passed the domain check
        # Note that points are computed with reward lines present
        all_programs_status.update(self._program_check_compute_points(domain_matching_programs))
        # Delay any unlink to the end of the function since they cause a full cache invalidation
        lines_to_unlink = self.env['sale.order.line']
        coupons_to_unlink = self.env['loyalty.card']


        point_entries_to_unlink = self.env['sale.order.coupon.points']
        # Remove any coupons that are expired
        self.applied_coupon_ids = self.applied_coupon_ids.filtered(lambda c:
            (not c.expiration_date or c.expiration_date >= fields.Date.today())
        )

        point_ids_per_program = defaultdict(lambda: self.env['sale.order.coupon.points'])

        point_ids = self.coupon_point_ids.filtered('points')

        # Filtrar solo los que tienen cupón válido (existe en BD)
        valid_point_ids = point_ids.filtered(lambda p: p.coupon_id.exists())

        # Actualizar para mantener solo los válidos
        self.coupon_point_ids = valid_point_ids

        for pe in self.coupon_point_ids:

            if not pe.coupon_id.exists():
                continue
                # Remove any point entry for a coupon that does not belong to the customer
            if pe.coupon_id.partner_id and pe.coupon_id.partner_id != self.partner_id:
                pe.points = 0
                point_entries_to_unlink |= pe
            else:
                point_ids_per_program[pe.coupon_id.program_id] |= pe

        # +==========================================+
        # |       STEP 2: Update applied programs    |
        # +==========================================+

        # Programs that were not applied via a coupon
        for program in points_programs:
            status = all_programs_status[program]
            program_point_entries = point_ids_per_program[program]
            if 'error' in status:
                # Program is not applicable anymore
                coupons_from_order = program_point_entries.coupon_id.filtered(lambda c: c.order_id == self)
                all_coupons -= coupons_from_order

                # Invalidate those lines so that they don't impact anything further down the line
                program_reward_lines = self.order_line.filtered(lambda l: l.coupon_id in coupons_from_order)
                program_reward_lines._reset_loyalty(True)
                lines_to_unlink |= program_reward_lines
                # Delete coupon created by this order for this program if it is not nominative
                if not program.is_nominative:
                    coupons_to_unlink |= coupons_from_order
                else:
                    # Only remove the coupon_point_id
                    point_entries_to_unlink |= program_point_entries
                    point_entries_to_unlink.points = 0
                # Remove the code activated rules
                self.code_enabled_rule_ids -= program.rule_ids
            else:
                # Program stays applicable, update our points
                all_point_changes = [p for p in status['points'] if p]
                if not all_point_changes and program.is_nominative:
                    all_point_changes = [0]
                for pe, points in zip(program_point_entries.sudo(), all_point_changes):
                    pe.points = points

                if len(program_point_entries) < len(all_point_changes):
                    new_coupon_points = all_point_changes[len(program_point_entries):]
                    # NOTE: Maybe we could batch the creation of coupons across multiple programs but this really only applies to gift cards
                    new_coupons = self.env['loyalty.card'].with_context(loyalty_no_mail=True, tracking_disable=True).create([{
                        'program_id': program.id,
                        'partner_id': False,
                        'points': 0,
                        'order_id': self.id,
                    } for _ in new_coupon_points])
                    self._add_points_for_coupon({coupon: x for coupon, x in zip(new_coupons, new_coupon_points)})
                elif len(program_point_entries) > len(all_point_changes):
                    point_ids_to_unlink = program_point_entries[len(all_point_changes):]
                    all_coupons -= point_ids_to_unlink.coupon_id
                    coupons_to_unlink |= point_ids_to_unlink.coupon_id
                    point_ids_to_unlink.points = 0

        # Programs applied using a coupon
        applied_coupon_per_program = defaultdict(lambda: self.env['loyalty.card'])
        for coupon in self.applied_coupon_ids:
            applied_coupon_per_program[coupon.program_id] |= coupon
        for program in coupon_programs:
            if program not in domain_matching_programs or\
                (program.applies_on == 'current' and 'error' in all_programs_status[program]):
                program_reward_lines = self.order_line.filtered(lambda l: l.coupon_id in applied_coupon_per_program[program])
                program_reward_lines._reset_loyalty(True)
                lines_to_unlink |= program_reward_lines
                self.applied_coupon_ids -= applied_coupon_per_program[program]
                all_coupons -= applied_coupon_per_program[program]

        # +==========================================+
        # |       STEP 3: Update reward lines        |
        # +==========================================+

        # We will reuse these lines as much as possible, this resets the order in a reward-less state
        reward_line_pool = self.order_line.filtered(lambda l: l.reward_id and l.coupon_id)._reset_loyalty()
        seen_rewards = set()
        line_rewards = []
        payment_rewards = [] # gift_card and ewallet are considered as payments and should always be applied last
        for line in self.order_line:
            if line.reward_identifier_code in seen_rewards or not line.reward_id or\
                not line.coupon_id:
                continue
            seen_rewards.add(line.reward_identifier_code)
            if line.reward_id.program_id.is_payment_program:
                payment_rewards.append((line.reward_id, line.coupon_id, line.reward_identifier_code, line.product_id))
            else:
                line_rewards.append((line.reward_id, line.coupon_id, line.reward_identifier_code, line.product_id))

        for reward_key in itertools.chain(line_rewards, payment_rewards):
            coupon = reward_key[1]
            reward = reward_key[0]
            program = reward.program_id
            points = self._get_real_points_for_coupon(coupon)
            if coupon not in all_coupons or points < reward.required_points or program not in domain_matching_programs:
                # Reward is not applicable anymore, the reward lines will simply be removed at the end of this function
                continue
            try:
                values_list = self._get_reward_line_values(reward, coupon, product=reward_key[3])
            except UserError:
                # It could happen that we have nothing to discount after changing the order.
                values_list = []
            reward_line_pool = self._write_vals_from_reward_vals(values_list, reward_line_pool, delete=False)

        lines_to_unlink |= reward_line_pool

        # +==========================================+
        # |       STEP 4: Apply new programs         |
        # +==========================================+
        for program in automatic_programs:
            program_status = all_programs_status[program]
            if 'error' in program_status:
                continue
            self.__try_apply_program(program, False, program_status)

        # +==========================================+
        # |       STEP 5: Cleanup                    |
        # +==========================================+

        order_line_update = [(Command.DELETE, line.id) for line in lines_to_unlink]

        if order_line_update:
            self.write({'order_line': order_line_update})
        if coupons_to_unlink:
            coupons_to_unlink.sudo().unlink()
        if point_entries_to_unlink:
            point_entries_to_unlink.sudo().unlink()

        self._get_points_programs()


    def action_confirm(self):
        for order in self:
            all_coupons = order.applied_coupon_ids | order.coupon_point_ids.coupon_id | order.order_line.coupon_id
            if any(order._get_real_points_for_coupon(coupon) < 0 for coupon in all_coupons):
                raise ValidationError(_('One or more rewards on the sale order is invalid. Please check them.'))
            order._update_programs_and_rewards()

        # Remove any coupon from 'current' program that don't claim any reward.
        # This is to avoid ghost coupons that are lost forever.
        # Claiming a reward for that program will require either an automated check or a manual input again.
        reward_coupons = self.order_line.coupon_id.exists()
        self.coupon_point_ids.filtered(
            lambda pe: pe.coupon_id.program_id.applies_on == 'current' and pe.coupon_id.exists() not in reward_coupons
        ).coupon_id.sudo().unlink()
        # Add/remove the points to our coupons
        for coupon, change in self.filtered(lambda s: s.state != 'sale')._get_point_changes().items():
            coupon.points += change
        res = super(SaleLoyaltySaleOrder, self).action_confirm()
        self._send_reward_coupon_mail()
        return res

    # def action_confirm(self):
    #     for order in self:
    #         # Las líneas de recompensa fueron integradas como descuentos
    #         # Limpiar los cupones que ya no tienen propósito
    #         reward_coupons = order.order_line.coupon_id
    #         orphan_points = order.coupon_point_ids.filtered(
    #             lambda pe: pe.coupon_id.program_id.applies_on == 'current' and
    #                        pe.coupon_id not in reward_coupons
    #         )
    #         orphan_coupons = orphan_points.coupon_id.sudo()
    #         orphan_points.unlink()
    #         orphan_coupons.filtered(lambda c: not c.use_count).unlink()
    #
    #         # Persistir cambios
    #         order.flush_recordset()
    #         order.invalidate_recordset()
    #
    #     # Tu lógica adicional
    #     self._send_reward_coupon_mail()
    #     self._get_points_programs()
    #
    #     # Ahora el super NO intentará borrar lo que ya borramos
    #     res = super(SaleLoyaltySaleOrder, self).action_confirm()
    #     return res

    def _action_cancel(self):
        previously_confirmed = self.filtered(lambda s: s.state == 'sale')

        # Add/remove the points to our coupons
        for coupon, changes in previously_confirmed.filtered(
                lambda s: s.state != 'sale'
        )._get_point_changes().items():
            coupon.points -= changes

        # Borrar líneas de recompensa
        self.order_line.filtered(lambda l: l.is_reward_line).unlink()

        # Borrar cupones que cumplen condiciones
        self.coupon_point_ids.coupon_id.sudo().filtered(
            lambda c: not c.program_id.is_nominative and c.order_id in self and not c.use_count
        ).unlink()

        # Borrar todos los coupon_point_ids restantes
        self.coupon_point_ids.unlink()

        # IMPORTANTE: Forzar escritura a BD y limpiar caché
        self.env.cr.flush()
        self.invalidate_recordset(['order_line', 'coupon_point_ids'])

        res = super()._action_cancel()
        return res

    def _get_points_programs(self):
        """
        Returns all programs that give points on the current order.
        Also updates coupon_point_ids removing orphan records.
        """
        self.ensure_one()

        # Verificar qué coupon_points realmente existen
        valid_coupon_points = self.coupon_point_ids.exists()

        # Actualizar si hay coupon_points huérfanos
        if len(valid_coupon_points) != len(self.coupon_point_ids):
            self.coupon_point_ids = valid_coupon_points

        # Filtrar solo los que tienen coupon_id válido (que existe)
        coupon_points_with_valid_coupon = valid_coupon_points.filtered(
            lambda cp: cp.coupon_id.exists()
        )

        # Actualizar si hay coupon_points con coupon_id huérfano
        if len(coupon_points_with_valid_coupon) != len(valid_coupon_points):
            self.coupon_point_ids = coupon_points_with_valid_coupon

        # Filtrar los que tienen puntos
        coupon_points_with_points = coupon_points_with_valid_coupon.filtered('points')

        if not coupon_points_with_points:
            return self.env['loyalty.program']

        # Retornar programas válidos
        valid_coupons = coupon_points_with_points.coupon_id.exists()

        if not valid_coupons:
            return self.env['loyalty.program']

        return valid_coupons.program_id.exists()