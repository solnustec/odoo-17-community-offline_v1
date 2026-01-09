from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class LoyaltyProgram(models.Model):
    _name = 'loyalty.program'
    _inherit = ['loyalty.program', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char(tracking=True)
    applies_on = fields.Selection(tracking=True)
    available_on = fields.Boolean(tracking=True)
    create_uid = fields.Many2one(tracking=True)
    currency_id = fields.Many2one(tracking=True)
    date_from = fields.Date(tracking=True)
    date_to = fields.Date(tracking=True)
    mandatory_promotion = fields.Boolean(string="Promoción obligatoria", default=True, tracking=True)
    is_selection_promotion = fields.Boolean(string="Promoción Seleccionable", tracking=True)
    note_promotion = fields.Text("Nota de Promoción", tracking=True)
    limit_for_order = fields.Integer(
        string="Límite de aplicaciones del cupón por pedido",
        help="Cantidad máxima de productos con descuento permitidos por pedido. 0 indica sin límite.",
        default=0,
        tracking=True
    )
    applies_by_boxes = fields.Boolean(
        string="Aplicar por cajas",
        help="Si está activado, se calcula por cantidad de cajas en el pedido.",
        default=False,
        tracking=True
    )

    max_boxes_limit = fields.Integer(
        string="Límite máximo de cajas",
        help="Cantidad máxima de cajas permitidas. Dejar en 0 para sin límite.",
        default=0,
        tracking=True
    )

    ecommerce_ok = fields.Boolean(tracking=True)
    pos_ok = fields.Boolean(tracking=True)
    sale_ok = fields.Boolean(tracking=True)

    # Campo para rastrear desactivación automática del POS por productos dados de baja
    pos_auto_disabled_by_product_ids = fields.Many2many(
        'product.product',
        'loyalty_program_pos_disabled_product_rel',
        'program_id',
        'product_id',
        string="POS desactivado automáticamente por",
        help="Productos dados de baja que causaron la desactivación de este programa en POS. "
             "Se usa para reactivación automática cuando el producto vuelve a estar disponible."
    )

    reward_ids = fields.One2many(tracking=True)
    rule_ids = fields.One2many(tracking=True)
    program_type = fields.Selection(
        selection='_get_new_program_type',
        default='promotion', required=True,
        tracking=True
    )
    # Computed fields for reward calculation
    reward_discount = fields.Float(
        string="Descuento %",
        compute="_compute_reward_discount",
        store=False
    )

    reward_product_description = fields.Char(
        string="Producto gratis",
        compute="_compute_reward_product_description",
        store=False
    )
    is_auto_apply = fields.Boolean(
        string="Aplicar cupón Automáticamente",
        help="Si está activado, el cupón no se aplicará automáticamente en la orden, si esta desactivado, el cupón se debe registrar manualmente en la orden.",
        default=False,
        tracking=True
    )

    applies_to_the_second = fields.Boolean(
        string="Aplica al segundo ítem",
        help="Activa esta opción si la promoción debe aplicarse al segundo producto o línea.",
        default=False,
        tracking=True
    )

    @api.model
    def _get_new_program_type(self):
        selection = [
            ('coupons', 'Cupones'),
            ('gift_card', 'Tarjeta de regalo'),
            ('loyalty', 'Tarjetas de lealtad'),
            ('promotion', 'Promociones')
        ]
        return selection

    @api.model
    def create(self, values):
        record = super().create(values)
        self._check_dates_if_rewards_exist(record)

        return record

    def write(self, values):
        if 'active' in values:
            return super().write(values)

        result = super().write(values)

        for record in self:
            self._check_dates_if_rewards_exist(record)

        return result

    def _check_dates_if_rewards_exist(self, record):
        if not record.active:
            return
        rewards_with_product_type = record.reward_ids.filtered(lambda r: r.reward_type == 'product' and r.active)
        for reward_product in rewards_with_product_type:
            if reward_product and (not reward_product.date_from or not reward_product.date_to):
                raise ValidationError(
                    "Es obligatorio establecer los campos 'Fecha de inicio' y 'Fecha final' "
                    "cuando se incluyen recompensas con el tipo 'Producto Gratis'."
                )

    @api.depends('reward_ids.reward_type', 'reward_ids.discount')
    def _compute_reward_discount(self):
        for program in self:
            discount_rewards = program.reward_ids.filtered(
                lambda r: r.reward_type == 'discount')
            if discount_rewards:
                # Si hay varios descuentos, tomamos el mayor, o puedes ajustar la lógica
                program.reward_discount = max(
                    discount_rewards.mapped('discount'))
            else:
                program.reward_discount = 0.0

    @api.depends('reward_ids.reward_type', 'reward_ids.required_points',
                 'reward_ids.reward_product_qty')
    def _compute_reward_product_description(self):
        for program in self:
            product_rewards = program.reward_ids.filtered(
                lambda r: r.reward_type == 'product')
            if product_rewards:

                reward = product_rewards[0]
                program.reward_product_description = f"{int(reward.required_points)} x {int(reward.reward_product_qty)}"
            else:

                program.reward_product_description = ""

    # @api.onchange('applies_to_the_second', 'mandatory_promotion', 'is_selection_promotion')
    # def _onchange_promotion_flags(self):
    #     for record in self:
    #         prev = record._origin or record
    #
    #         # --- Caso 1: aplica al segundo ---
    #         if record.applies_to_the_second and not prev.applies_to_the_second:
    #             record.mandatory_promotion = True
    #             record.is_selection_promotion = False
    #             continue  # prioridad total
    #
    #         # --- Caso 2: seleccionable ---
    #         if record.is_selection_promotion and not prev.is_selection_promotion:
    #             record.mandatory_promotion = False
    #             record.applies_to_the_second = False
    #             continue  # prioridad total
    #
    #         # --- Caso 3: obligatoria ---
    #         if record.mandatory_promotion and not prev.mandatory_promotion:
    #             record.is_selection_promotion = False
    #             # no tocamos applies_to_the_second porque puede estar forzado por negocio
    #             continue
    #
    #         # --- Caso 4: ningún flag activo ---
    #         if (
    #                 not record.applies_to_the_second
    #                 and not record.mandatory_promotion
    #                 and not record.is_selection_promotion
    #         ):
    #             record.mandatory_promotion = True

    @api.model
    def get_coupon_promotions_for_product(self, product_id):
        """
        Devuelve las promociones de cupones activas y sus cupones generados no usados aplicables a un producto específico.
        Args:
            product_id (int): ID del producto.
        Returns:
            list: Lista de diccionarios con detalles de las promociones y sus cupones no usados.
            dict: Diccionario con un mensaje de error si no se encuentran promociones o hay un problema.
        """
        # Validar que se proporcione un product_id
        if not product_id or not isinstance(product_id, int):
            return {
                'error': 'El ID del producto es requerido y debe ser un entero'}

        # Buscar el producto para validar su existencia
        product = self.env['product.product'].browse(product_id).exists()
        if not product:
            return {'error': f'El producto con ID {product_id} no existe'}

        #buscar la regla que tenga el producto
        rule = self.env['loyalty.rule'].search([('product_ids', 'in', [product.id])])
        if not rule:
            return {'error': f'No se encontraron reglas de lealtad asociadas al producto con ID {product_id}'}
        #buscar el programa asociado a la regla que sea de cupones y este activo
        cuopons_programs = []
        for r in rule:
            if r.program_id.program_type == 'coupons' and r.program_id.active:
                cuopons_programs.append(r.program_id.id)

        promotions = []
        for program in cuopons_programs:

            coupons = self.env['loyalty.card'].search([
                ('program_id', '=', program),
                ('is_used', '=', False),  # Filtrar solo cupones no usados
            ], limit=1)
            program_id = self.env['loyalty.program'].browse(program)

            if program_id.applies_by_boxes:
                qty_min = product.uom_po_factor_inv
            else:
                qty_min = 1



            promotion_data = {
                'id': program_id.id,
                'name': program_id.name,
                'program_type': program_id.program_type,
                'qty_min': qty_min,
                'max_boxes_limit': program_id.max_boxes_limit if program_id.max_boxes_limit else 'Sin Límite',
                'reward_ids': [
                    {
                        'id': reward.id,
                        'description': reward.description or 'Sin descripción',
                    }
                    for reward in program_id.reward_ids
                ],
                'applies_on': program_id.applies_on,
                'coupons': [
                    {
                        'id': coupon.id,
                        'is_auto_apply': program_id.is_auto_apply,
                        'code': coupon.code,
                        # Código del cupón (por ejemplo, 044C-0F8F-4C6B)
                        'points': coupon.points,
                        # Puntos totales del cupón
                        'is_used': coupon.is_used,  # Estado de uso
                        'expiration_date': str(
                            coupon.expiration_date) if coupon.expiration_date else None,
                        'partner_id': coupon.partner_id.id if coupon.partner_id else None,
                        'partner_name': coupon.partner_id.name if coupon.partner_id else None,
                    }
                    for coupon in coupons
                ],
            }
            promotions.append(promotion_data)

        # Devolver resultado
        if promotions:
            return promotions
        else:
            return {
                'error': f'No se encontraron promociones de cupones para el producto con ID {product_id}'}

    @api.model
    def get_coupon_promotions_by_program(self, program_id):
        """
        Devuelve los detalles de un programa de cupones y sus cupones no usados.
        Args:
            program_id (int): ID del programa de lealtad.
        Returns:
            dict: Diccionario con detalles de la promoción y sus cupones no usados.
            dict: Diccionario con un mensaje de error si no se encuentra el programa o hay un problema.
        """
        # Validar que se proporcione un program_id
        if not program_id or not isinstance(program_id, int):
            return {'error': 'El ID del programa es requerido y debe ser un entero'}

        # Buscar el programa para validar su existencia
        program = self.env['loyalty.program'].browse(program_id).exists()
        if not program:
            return {'error': f'El programa con ID {program_id} no existe'}

        # Validar que sea un programa de cupones y esté activo
        if program.program_type != 'coupons':
            return {'error': f'El programa con ID {program_id} no es de tipo cupones'}

        if not program.active:
            return {'error': f'El programa con ID {program_id} no está activo'}

        # Buscar cupones no usados del programa
        coupons = self.env['loyalty.card'].search([
            ('program_id', '=', program_id),
            ('is_used', '=', False),
        ], limit=1)

        if not coupons:
            return {'error': f'No se encontraron cupones no usados para el programa con ID {program_id}'}

        # Construir la respuesta
        promotion_data = {
            'id': program.id,
            'name': program.name,
            'program_type': program.program_type,
            'applies_by_boxes': program.applies_by_boxes,
            'max_boxes_limit': program.max_boxes_limit if program.max_boxes_limit else 'Sin Límite',
            'reward_ids': [
                {
                    'id': reward.id,
                    'description': reward.description or 'Sin descripción',
                }
                for reward in program.reward_ids
            ],
            'applies_on': program.applies_on,
            'coupons': [
                {
                    'id': coupon.id,
                    'is_auto_apply': program.is_auto_apply,
                    'code': coupon.code,
                    'points': coupon.points,
                    'is_used': coupon.is_used,
                    'expiration_date': str(coupon.expiration_date) if coupon.expiration_date else None,
                    'partner_id': coupon.partner_id.id if coupon.partner_id else None,
                    'partner_name': coupon.partner_id.name if coupon.partner_id else None,
                }
                for coupon in coupons
            ],
        }

        return promotion_data


class LoyaltyReward(models.Model):
    _inherit = 'loyalty.reward'
    _kanban_edit = True

    is_main = fields.Boolean(string="Promoción principal")
    is_main_chat_bot = fields.Boolean(string="Promoción principal Chat-Bot")
    limit_quanty = fields.Integer(
        string="Límite de cantidad recompensada",
        compute="_compute_limit_quanty",
        store=True,
        readonly=False,
        default=1,
    )
    frecuency_sale = fields.Selection(
        [
            ('day', 'Día'),
            ('week', 'Semana'),
            ('month', 'Mes'),
            ('year', 'Año'),
            ('limit_none', 'Sin Límite'),
        ],
        string="Frecuencia del Límite",
        default='week',
    )

    discount_applicability = fields.Selection(
        selection='_get_new_discount_applicability',
        default='order',
    )

    discount_product_domain = fields.Char(default='[("type", "in", ["consu", "product"])]')

    date_from = fields.Date(tracking=True, string="Desde")
    date_to = fields.Date(tracking=True, string="Hasta")

    _sql_constraints = [
        ('required_points_positive',
         'CHECK (required_points > 0)',
         'The required points for a reward must be strictly positive.'),
        ('product_qty_positive',
         "CHECK (reward_type != 'product' OR reward_product_qty > 0)",
         'The reward product quantity must be strictly positive.'),
        ('discount_positive',
         "CHECK (reward_type != 'discount' OR discount > 0)",
         'The discount must be strictly positive.'),
    ]

    @api.model
    def _get_new_discount_applicability(self):
        selection = [
            ('order', 'Orden'),
            ('specific', 'Productos específicos')
        ]
        return selection

    @api.constrains('discount_product_ids', 'product_ids', 'reward_product_id')
    def _check_single_product_selection(self):
        for record in self:
            if len(record.discount_product_ids) > 1:
                raise ValidationError("Solo puedes seleccionar un producto con descuento en 'Recompensas'.")
            if len(record.reward_product_id) > 1:
                raise ValidationError("Solo puedes seleccionar un producto de gratis  por cada 'Recompensa'.")

    @api.model
    def create(self, vals):
        if vals.get("is_main"):
            self._update_other_mains(vals.get('program_id'), False)
        program_id = vals.get('program_id')
        if program_id:
            program = self.env['loyalty.program'].browse(program_id)
            vals['is_main_chat_bot'] = program.ecommerce_ok
        return super(LoyaltyReward, self).create(vals)

    def write(self, vals):
        if vals.get("is_main"):
            self._update_other_mains(self.program_id.id, self.id)
        return super(LoyaltyReward, self).write(vals)

    def _update_other_mains(self, program_id, current_id):
        self.env.cr.execute("""
                            UPDATE loyalty_reward
                            SET is_main = FALSE
                            WHERE is_main = TRUE
                              AND program_id = %s
                              AND id != %s
                            """, (program_id, current_id or 0))

    @api.depends('reward_product_qty', 'frecuency_sale')
    def _compute_limit_quanty(self):
        for rec in self:
            if rec.frecuency_sale == 'limit_none':
                rec.limit_quanty = 0
            else:
                rec.limit_quanty = max(rec.limit_quanty, 1)

    @api.model
    def check_promotion_limit(self, partner_id, product_id, reward, context_channel=None):
        reward_rec = self.browse(reward)
        if not reward_rec:
            return {'remaining': 0, 'message': 'Promoción no encontrada.'}

        # — Sólo chat-bot: ignorar recompensas no marcadas —
        if context_channel == 'chatbot' and not reward_rec.is_main_chat_bot:
            return {'remaining': 0, 'message': 'No aplica para Chat-Bot.'}

        if reward_rec.reward_type != 'product':
            return {'remaining': 0, 'message': 'La recompensa no es de tipo producto.'}

        limit_quanty = reward_rec.limit_quanty
        frecuency_sale = reward_rec.frecuency_sale
        limit_local = reward_rec.reward_product_qty
        unlimited = (frecuency_sale == 'limit_none')

        today = fields.Date.today()
        start_date = today
        if not unlimited:
            date_rules = {
                'day': today,
                'week': today - timedelta(days=today.weekday()),
                'month': today.replace(day=1),
                'year': today.replace(month=1, day=1),
            }
            start_date = date_rules.get(frecuency_sale, today)

        lines = self.env['pos.order.line'].search([
            ('order_id.partner_id', '=', partner_id),
            ('product_id', '=', product_id),
            ('is_reward_line', '=', True),
            ('reward_id', '=', reward_rec.id),
            ('create_date', '>=', start_date),
            ('refunded_orderline_id', '=', False),
        ])
        count = sum(lines.mapped('qty'))
        if count >= limit_quanty:
            return {
                'limit': 0,
                'limit_local': 0,
                'limit_items': 0,
                'unlimited': unlimited,
                'message': 'Límite alcanzado.'
            }
        remaining = limit_quanty - count
        return {
            'limit': remaining,
            'limit_local': limit_local,
            'limit_items': remaining * limit_local,
            'unlimited': unlimited,
            'message': f'Restantes: {remaining}'
        }

    def _get_discount_product_values(self):
        # ctx = self.env.context.get('channel')
        """
        Crea productos virtuales para las recompensas de tipo descuento.
        Estos productos no son vendibles ni comprables y tienen un precio de 0.
        Se asignan los impuestos del producto original en el producto de la recompensa.
        """

        return [{
            'name': reward.description,
            'type': 'service',
            'is_reward_product': True,
            'sale_ok': False,
            'purchase_ok': False,
            'lst_price': 0,
            'taxes_id': [(6, 0, (reward.discount_product_ids[:1].taxes_id.ids or []))],
        } for reward in self]

        # return [{
        #     'name': rw.description,
        #     'is_reward_product': True,
        #     'type': 'service',
        #     'sale_ok': False,
        #     'purchase_ok': False,
        #     'taxes_id': [(6, 0, [self.product_id.taxes_id[0].id])],
        #     'lst_price': 0.0,
        # } for rw in self if not (ctx == 'chatbot' and not rw.is_main_chat_bot)]

    def _create_missing_discount_line_products(self):
        # Make sure we create the product that will be used for our discounts
        rewards = self.filtered(lambda r: not r.discount_line_product_id)
        products = self.env['product.product'].create(rewards._get_discount_product_values())
        for reward, product in zip(rewards, products):
            base_taxes_ids = reward.discount_product_ids[:1].taxes_id.ids if reward.discount_product_ids else []

            tmpl = product.product_tmpl_id
            tmpl.write({
                'taxes_id': [(6, 0, base_taxes_ids)],
            })
            reward.discount_line_product_id = product


class LoyaltyCard(models.Model):
    _inherit = 'loyalty.card'

    is_used = fields.Boolean(
        string="Usado",
        default=False,
        help="Indicates whether the coupon has been used."
    )

    @api.depends('points')
    def _compute_is_used(self):
        """
        Automatically set is_used to True if the coupon has no remaining points.
        """
        for coupon in self:
            if coupon.points <= 0:
                coupon.is_used = True
            else:
                coupon.is_used = False

    # Sobrescribir el método write para actualizar is_used cuando cambien los puntos
    def write(self, vals):
        res = super(LoyaltyCard, self).write(vals)
        if 'points' in vals:
            self._compute_is_used()
        return res

    # Sobrescribir el método create para asegurarnos de que is_used se compute al crear
    @api.model_create_multi
    def create(self, vals_list):
        coupons = super(LoyaltyCard, self).create(vals_list)
        coupons._compute_is_used()
        return coupons

    @api.model
    def mark_coupon_as_used(self, coupon_code, value=True):
        """
        Busca un cupón por su código y actualiza el campo is_used a True.
        Args:
            coupon_code (str): Código del cupón a marcar como usado.
        Returns:
            dict: Respuesta con el estado de la operación.
        """

        if not coupon_code:
            return {'error': 'El código del cupón es requerido'}

        coupon = self.search([('code', '=', coupon_code)], limit=1)
        if not coupon:
            return {
                'error': f'No se encontró un cupón con el código {coupon_code}'}

        try:
            coupon.write({'is_used': value})
            return {
                'success': True,
                'message': f'El cupón con código {coupon_code} ha sido marcado {value}',
                'coupon_id': coupon.id,
            }
        except Exception as e:
            return {'error': f'Error al marcar el cupón como usado: {str(e)}'}


class LoyaltyRule(models.Model):
    _inherit = 'loyalty.rule'

    product_domain = fields.Char(default='[("type", "in", ["consu", "product"])]')

    @api.constrains('discount_product_ids', 'product_ids', 'reward_product_id')
    def _check_single_product_selection(self):
        for record in self:
            if len(record.product_ids) > 1:
                raise ValidationError("Solo puedes seleccionar un producto en 'Reglas'.")
