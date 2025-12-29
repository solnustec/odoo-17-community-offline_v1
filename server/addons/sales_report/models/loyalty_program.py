import json
from odoo import models, fields, api
from odoo.http import Response
from odoo.exceptions import UserError
from datetime import date
from typing import Tuple, Optional
import logging

_logger = logging.getLogger(__name__)


class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    archived_discount_reward_info = fields.Char(
        string="Recompensa de descuento archivada",
        help="Guarda el ID y el valor del descuento de la recompensa de descuento normal archivada"
    )

    archived_temporary_discount_reward_info = fields.Char(
        string="Recompensa de descuento temporal archivada",
        help="Guarda el ID y el valor del descuento de la recompensa de descuento temporal archivada"
    )

    archived_second_discount_reward_info = fields.Char(
        string="Segunda recompensa de descuento archivada",
        help="Guarda el ID y el valor del descuento de la segunda recompensa de descuento archivada"
    )

    archived_product_reward_info = fields.Char(
        string="Recompensa de producto archivada",
        help="Guarda el ID, la base y la promocion de la recompensa de producto archivada"
    )

    def write(self, vals):
        res = super().write(vals)

        if 'active' in vals:
            new_active = bool(vals['active'])

            # Solo cuando se ARCHIVA el programa
            if not new_active:
                programs = self.with_context(active_test=False)
                rules = programs.mapped('rule_ids').with_context(active_test=False)
                rewards = programs.mapped('reward_ids').with_context(active_test=False)

                if rules:
                    rules.sudo().write({'active': False})
                if rewards:
                    rewards.sudo().write({'active': False})
        return res

    def archive_program(self):
        self.ensure_one()
        self.sudo().write({'active': False})

    @api.model
    def restore_last_archived_program(self, product_id, program_type):
        """
        Restaura (active=True) el último programa archivado de acuerdo al
        tipo de programa (`program_type`) y al producto (M2M `trigger_product_ids`).
        """
        Program = self.env['loyalty.program'].with_context(active_test=False)
        domain = [
            ('active', '=', False),
            ('trigger_product_ids', 'in', [product_id]),
            ('program_type', '=', program_type),
        ]
        prog = Program.search(domain, order='write_date desc, id desc', limit=1)
        if not prog:
            return Program.browse()

        #default_date_from = date(2025, 1, 1)
        #default_date_to = date(2026, 1, 1)

        if program_type == 'coupons':
            trigger = 'with_code'
        else:
            trigger = 'auto'

        prog.sudo().write({
            'active': True,
            'pos_ok': True,
            'ecommerce_ok': False,
            #'date_from': default_date_from,
            #'date_to': default_date_to,
            'trigger': trigger,
        })

        return prog

    def preprocess_unarchived_program(self, product_id, reward_info):
        self.ensure_one()

        rules = self.with_context(active_test=False).rule_ids
        rewards = self.with_context(active_test=False).reward_ids
        product_rewards = rewards.filtered(lambda r: r.reward_type == 'product')
        discount_rewards = rewards.filtered(lambda r: r.reward_type == 'discount')

        if rules:
            rules_sorted = rules.sorted(lambda r: r.create_date, reverse=True)
            default_rule = rules_sorted[0]
            default_rule.sudo().write({
                'minimum_qty': 1,
                'minimum_amount': 0,
                'reward_point_amount': 1,
                'product_ids': [(6, 0, [product_id])],
                'reward_point_mode': 'unit',
            })
        else:
            default_rule = self.env['loyalty.rule'].sudo().create({
                'program_id': self.id,
                'minimum_qty': 1,
                'minimum_amount': 0,
                'reward_point_amount': 1,
                'product_ids': [(6, 0, [product_id])],
                'reward_point_mode': 'unit',
            })

        parse_info = self.parse_info(reward_info)
        reward_id = int(parse_info[0]) if parse_info[0] is not None else None
        discount = float(parse_info[1]) if parse_info[1] is not None else 10
        default_reward_discount = None

        if discount_rewards:
            default_reward_discount = discount_rewards.sudo().browse(reward_id)

        if default_reward_discount:
            default_reward_discount.sudo().write({
                'discount': discount,
                'discount_applicability': 'specific',
                'required_points': 1,
                'discount_product_ids': [(6, 0, [product_id])],
                'is_temporary': False,
            })
        else:
            default_reward_discount = self.env['loyalty.reward'].sudo().create({
                'program_id': self.id,
                'reward_type': 'discount',
                'discount': 10,
                'discount_applicability': 'specific',
                'required_points': 1,
                'discount_product_ids': [(6, 0, [product_id])],
                'is_temporary': False,
            })

        rules_to_archive = (rules - default_rule)
        product_rewards_to_archive = product_rewards
        discount_rewards_to_archive = (discount_rewards - default_reward_discount)

        rules_to_archive.sudo().write({'active': False})
        product_rewards_to_archive.sudo().write({'active': False})
        discount_rewards_to_archive.sudo().write({'active': False})

        default_rule.sudo().write({'active': True})
        default_reward_discount.sudo().write({'active': True})

        default_reward_discount_id = default_reward_discount.id

        return default_reward_discount_id

    def obtain_char_id_and_values(self, reward_id, reward_type):
        reward_to_archive = self.env['loyalty.reward'].sudo().browse(reward_id)
        discount = 0
        reward_product_qty = 0
        required_points = 0

        if reward_type == 'discount':
            if reward_to_archive:
                discount = reward_to_archive.discount
            return f"{reward_id},{discount}"
        elif reward_type == 'product':
            if reward_to_archive:
                reward_product_qty = int(reward_to_archive.reward_product_qty)
                required_points = int(reward_to_archive.required_points)
            return f"{reward_id},{reward_product_qty},{required_points}"
        else:
            return ""

    def parse_info(self, info_string: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if not info_string:
            return None, None, None

        parts = info_string.split(",")
        p0 = parts[0] if len(parts) > 0 else None
        p1 = parts[1] if len(parts) > 1 else None
        p2 = parts[2] if len(parts) > 2 else None

        return p0, p1, p2

    def restore_archived_reward_by_id(self, reward_info, reward_type, product_id):
        """
        Restaura el reward de acuerdo al ID almacenado en el programa
        """

        self.ensure_one()

        if not reward_info:
            return self.env['loyalty.reward'].browse()

        parse_info = self.parse_info(reward_info)
        reward_id = int(parse_info[0]) if parse_info[0] is not None else None

        Reward = self.env['loyalty.reward'].with_context(active_test=False)
        domain = [
            ('active', '=', False),
            ('id', '=', reward_id),
            ('program_id', '=', self.id),
            ('reward_type', '=', reward_type),
        ]

        reward = Reward.search(domain, limit=1)
        if not reward:
            return Reward.browse()

        if reward_type=='discount':
            discount = float(parse_info[1]) if parse_info[1] is not None else 10
            reward.sudo().write({
                'active': True,
                'discount': discount,
                'discount_applicability': 'specific',
                'required_points': 1,
                'discount_product_ids': [(6, 0, [product_id])],
            })
        elif reward_type=='product':
            reward_product_qty = int(parse_info[1]) if parse_info[1] is not None else 1
            required_points = int(parse_info[2]) if parse_info[2] is not None else 1
            reward.sudo().write({
                'active': True,
                'reward_product_qty': reward_product_qty,
                'required_points': required_points,
                'reward_product_id': product_id,
                'is_main': True,
            })
        return reward

    def _build_sync_payload_from_program(self, product, discount_reward=None):
        self.ensure_one()

        Reward = self.env['loyalty.reward'].with_context(active_test=False)

        # =========================
        # Recompensa de producto gratis
        # =========================
        product_reward = Reward.search([
            ('program_id', '=', self.id),
            ('reward_type', '=', 'product'),
            ('active', '=', True),
        ], limit=1)

        # =========================
        # Cupón (si existe)
        # =========================
        coupon_program = self.env['loyalty.program'].search([
            ('trigger_product_ids', 'in', [product.id]),
            ('program_type', '=', 'coupons'),
            ('active', '=', True),
        ], limit=1)

        coupon_reward = Reward.search([
            ('program_id', '=', coupon_program.id),
            ('reward_type', '=', 'discount'),
            ('active', '=', True),
        ], limit=1) if coupon_program else None

        # =========================
        # Segunda recompensa de descuento (2do producto)
        # =========================
        second_discount_reward = Reward.search([
            ('program_id', '=', self.id),
            ('reward_type', '=', 'discount'),
            ('is_main', '=', True),
            ('is_temporary', '=', False),
            ('active', '=', True),
        ], limit=1)

        # =========================
        # Resolver coupon_discount, coupon_date_from y coupon_date_to con prioridad
        # =========================
        coupon_discount = 0
        coupon_date_from = None
        coupon_date_to = None
        if coupon_reward:
            coupon_discount = coupon_reward.discount
            coupon_date_from = coupon_reward.date_from
            coupon_date_to = coupon_reward.date_to
        elif second_discount_reward:
            coupon_discount = second_discount_reward.discount
            coupon_date_from = second_discount_reward.date_from
            coupon_date_to = second_discount_reward.date_to

        return [{
            "product_id": product.id,
            "desc_esp": discount_reward.discount if discount_reward else 0,
            "obligatory_promotion": self.mandatory_promotion,
            "date_from": product_reward.date_from if product_reward else None,
            "date_to": product_reward.date_to if product_reward else None,
            "base_cant": int(product_reward.required_points) if product_reward else 0,
            "promo_cant": int(product_reward.reward_product_qty) if product_reward else 0,
            "program_note": self.note_promotion or "",
            "coupon_discount": coupon_discount,
            "obligatory_coupon": coupon_program.mandatory_promotion if coupon_program else False,
            "coupon_date_from": coupon_date_from,
            "coupon_date_to": coupon_date_to,
            "acumulable": self.program_type == 'loyalty',
            "coupon": product.coupon or 0,
        }]

    def _safe_sync(self, program, product, payload):
        try:
            self.env['loyalty.sync'].sudo().sync_loyalty_programs(payload)
            self.env.cr.commit()
        except Exception:
            self.env.cr.rollback()
            _logger.exception(
                "Error sincronizando loyalty (cron) | program=%s | product=%s",
                program.id, product.id
            )

    @api.model
    def _cron_expire_temporary_discount_rewards(self):
        today = fields.Date.today()

        Program = self.with_context(active_test=False)
        Reward = self.env['loyalty.reward'].with_context(active_test=False)
        Product = self.env['product.product'].sudo()

        # Solo programas activos de promoción o loyalty
        programs = Program.search([
            ('active', '=', True),
            ('program_type', 'in', ['promotion', 'loyalty']),
        ])

        for program in programs:
            # Recompensas de descuento temporales vencidas
            temporary_rewards = Reward.search([
                ('program_id', '=', program.id),
                ('reward_type', '=', 'discount'),
                ('is_temporary', '=', True),
                ('active', '=', True),
                ('date_to', '!=', False),
                ('date_to', '<', today),
            ])

            for temp_reward in temporary_rewards:
                product_id = temp_reward.discount_product_ids[:1].id
                if not product_id:
                    continue

                # Guardar info y archivar recompensa temporal
                archived_temp_info = program.obtain_char_id_and_values(
                    reward_id=temp_reward.id,
                    reward_type='discount'
                )
                program.sudo().write({
                    'archived_temporary_discount_reward_info': archived_temp_info
                })
                temp_reward.sudo().write({'active': False})

                # Restaurar recompensa normal
                archived_normal_info = program.archived_discount_reward_info
                if not archived_normal_info:
                    Reward = self.env['loyalty.reward']
                    second_discount_reward = Reward.search([
                        ('program_id', '=', program.id),
                        ('reward_type', '=', 'discount'),
                        ('is_main', '=', True),
                        ('is_temporary', '=', False),
                        ('active', '=', True),
                    ], limit=1)
                    product_reward = Reward.search([
                        ('program_id', '=', program.id),
                        ('reward_type', '=', 'product'),
                        ('active', '=', True),
                    ], limit=1)

                    if not second_discount_reward and not product_reward:
                        program.archive_program()

                    product = Product.browse(product_id)
                    product.write({'discount': 0})

                    payload = program._build_sync_payload_from_program(
                        product=product,
                        discount_reward=None
                    )

                    # Crear registro para sincronizar la nueva informacion de recompensas con el visual
                    self._safe_sync(program, product, payload)

                    continue

                normal_reward = program.restore_archived_reward_by_id(
                    reward_info=archived_normal_info,
                    reward_type='discount',
                    product_id=product_id
                )

                if not normal_reward:
                    product = Product.browse(product_id)
                    product.write({'discount': 0})

                    payload = program._build_sync_payload_from_program(
                        product=product,
                        discount_reward=None
                    )

                    # Crear registro para sincronizar la nueva informacion de recompensas con el visual
                    self._safe_sync(program, product, payload)

                    continue

                # Forzar flags correctos
                normal_reward.sudo().write({
                    'is_temporary': False,
                    'active': True,
                })

                # Sincronizar descuento del producto
                product = Product.browse(product_id)
                product.write({'discount': normal_reward.discount})

                payload = program._build_sync_payload_from_program(
                    product=product,
                    discount_reward=normal_reward
                )

                # Crear registro para sincronizar la nueva informacion de recompensas con el visual
                self._safe_sync(program, product, payload)

    @api.model
    def create_loyalty_program(self, product_id, product_name, units_per_box,
                               mandatory_promotion,
                               discount_date_from, discount_date_to, product_date_from, product_date_to,
                               coupon_discount_date_from, coupon_discount_date_to,
                               discount, temporary_discount, coupon_discount,
                               reward_product_qty, required_points,
                               note_promotion,
                               coupon,
                               loyalty_card,
                               ):
        """
            Crea un programa de lealtad para un producto específico.

            :param product_id: ID del product.product para el cual se crea el programa de lealtad.
            :param product_name: Nombre del producto para el programa de lealtad.
            :param units_per_box: Numero de unidades por caja del producto.
            :param mandatory_promotion: Indica si la promoción/cupones es obligatoria/o.
            :param discount_date_from: Fecha de inicio de la recompensa de descuento del programa (opcional).
            :param discount_date_to: Fecha de fin de la recompensa de descuento del programa (opcional).
            :param product_date_from: Fecha de inicio de la recompensa de producto gratis del programa (opcional).
            :param product_date_to: Fecha de fin de la recompensa de producto gratis del programa (opcional).
            :param coupon_discount_date_from: Fecha de inicio de la recompensa de descuento del programa de cupones (opcional).
            :param coupon_discount_date_to: Fecha de fin de la recompensa de descuento del programa de cupones (opcional).
            :param discount: Valor del descuento (0 si no aplica).
            :param temporary_discount: Valor del descuento temporal (0 si no aplica).
            :param coupon_discount: Valor del descuento para el programa de cupones (0 si no aplica).
            :param reward_product_qty: Cantidad de productos para la recompensa (0 si no aplica).
            :param required_points: Puntos requeridos para la recompensa de producto (0 si no aplica).
            :param note_promotion: Nota de la promoción (opcional).
            :param coupon: Cupon (opcional): Tipo de cupon
            :param loyalty_card: Programa de tipo Tarjeta de Lealtad (opcional)
            :return: ID del programa de lealtad creado o Response con error.
            """

        loyalty_program = False
        coupon_loyalty_program = False

        ####### Crear programa de promociones o de tarjeta de lealtad #######
        if coupon is None or coupon==3:
            # Variable para seleccionar entre programa de tipo Promociones o Tarjeta de Lealtad
            if not loyalty_card:
                name = f"POS-{product_name}"
                program_type = 'promotion'
                applies_on = 'current'
            else:
                name = f"POS-TARJETA-LEALTAD-{product_name}"
                program_type = 'loyalty'
                applies_on = 'both'

            # Variables para la recompensa de descuento
            discount = float(discount or 0)
            temporary_discount = float(temporary_discount or 0)
            is_temporary = False
            if temporary_discount > 0:
                discount = 0
                is_temporary = True
            coupon_discount = float(coupon_discount or 0)
            # Variables para la recompensa de producto
            reward_product_qty = int(reward_product_qty or 0)
            required_points = int(required_points or 0)

            ### Crear programa de promociones ###
            if coupon is None:
                # verificar si solo se debe crear la promo de descuento
                if (discount > 0 or temporary_discount > 0) and (reward_product_qty == 0 or required_points == 0):
                    loyalty_program = self.env['loyalty.program'].sudo().create({
                        'name': name,
                        'program_type': program_type,
                        'pos_ok': True,
                        'ecommerce_ok': False,
                        'trigger': 'auto',
                        'mandatory_promotion': mandatory_promotion,
                        'is_selection_promotion': not mandatory_promotion,
                        'note_promotion': note_promotion,
                        'applies_on': applies_on,
                    })
                    # Crear la recompensa de descuento
                    self.env['loyalty.reward'].sudo().create({
                        'program_id': loyalty_program.id,
                        'reward_type': 'discount',
                        'discount': discount if (discount > 0) else temporary_discount,
                        'discount_applicability': 'specific',
                        'required_points': 1,
                        'discount_product_ids': [(6, 0, [product_id])],
                        'date_from': discount_date_from,
                        'date_to': discount_date_to,
                        'is_temporary': is_temporary,
                    })
                    self.env['loyalty.rule'].sudo().create({
                        'program_id': loyalty_program.id,
                        'minimum_qty': 1,
                        'minimum_amount': 0,
                        'reward_point_amount': 1,
                        'product_ids': [(6, 0, [product_id])],
                        'reward_point_mode': 'unit',
                    })
                    # actulizar el campo discount del producto
                    product = self.env['product.product'].sudo().browse(product_id)
                    # TODO revisar si el producto tiene otras recompensas de descuento
                    product.sudo().write({'discount': discount if (discount > 0) else temporary_discount})
                # verificar si solo se debe crear la promo de producto gratis
                if (reward_product_qty > 0 and required_points > 0) and (discount == 0 and temporary_discount == 0):
                    loyalty_program = self.env['loyalty.program'].sudo().create({
                        'name': name,
                        'program_type': program_type,
                        'pos_ok': True,
                        'ecommerce_ok': False,
                        'trigger': 'auto',
                        'mandatory_promotion': mandatory_promotion,
                        'is_selection_promotion': not mandatory_promotion,
                        'note_promotion': note_promotion,
                        #'date_from': date_from,
                        #'date_to': date_to,
                        'applies_on': applies_on,
                    })
                    self.env['loyalty.reward'].sudo().create({
                        'program_id': loyalty_program.id,
                        'reward_type': 'product',
                        'reward_product_qty': reward_product_qty,
                        'required_points': required_points,
                        'reward_product_id': product_id,
                        'is_main': True,
                        'date_from': product_date_from,
                        'date_to': product_date_to,
                        'is_temporary': False,
                    })
                    self.env['loyalty.rule'].sudo().create({
                        'program_id': loyalty_program.id,
                        'minimum_qty': 1,
                        'minimum_amount': 0,
                        'reward_point_amount': 1,
                        'product_ids': [(6, 0, [product_id])],
                        'reward_point_mode': 'unit',
                    })
                # verificar si se debe crear promo de descuento y de producto gratis
                if (discount > 0 or temporary_discount > 0) and (reward_product_qty > 0 and required_points > 0):
                    loyalty_program = self.env['loyalty.program'].sudo().create({
                        'name': name,
                        'program_type': program_type,
                        'pos_ok': True,
                        'ecommerce_ok': False,
                        'trigger': 'auto',
                        'mandatory_promotion': mandatory_promotion,
                        'is_selection_promotion': not mandatory_promotion,
                        'note_promotion': note_promotion,
                        #'date_from': date_from,
                        #'date_to': date_to,
                        'applies_on': applies_on,
                    })
                    self.env['loyalty.reward'].sudo().create({
                        'program_id': loyalty_program.id,
                        'reward_type': 'discount',
                        'discount': discount if (discount > 0) else temporary_discount,
                        'discount_applicability': 'specific',
                        'required_points': 0 if mandatory_promotion else 1,
                        'discount_product_ids': [(6, 0, [product_id])],
                        'date_from': discount_date_from,
                        'date_to': discount_date_to,
                        'is_temporary': is_temporary,
                    })
                    self.env['loyalty.reward'].sudo().create({
                        'program_id': loyalty_program.id,
                        'reward_type': 'product',
                        'reward_product_qty': reward_product_qty,
                        'required_points': required_points,
                        'reward_product_id': product_id,
                        'is_main': True,
                        'date_from': product_date_from,
                        'date_to': product_date_to,
                        'is_temporary': False,
                    })
                    self.env['loyalty.rule'].sudo().create({
                        'program_id': loyalty_program.id,
                        'minimum_qty': 1,
                        'minimum_amount': 0,
                        'reward_point_amount': 1,
                        'product_ids': [(6, 0, [product_id])],
                        'reward_point_mode': 'unit',
                    })
                    # actulizar el campo discount del producto
                    product = self.env['product.product'].sudo().browse(product_id)
                    # TODO revisar si el producto tiene otras recompensas de descuento
                    product.sudo().write({'discount': discount if (discount > 0) else temporary_discount})

            ### Crear programa de promociones de segundo producto de descuento ###
            elif coupon == 3:
                ## Crear programa
                loyalty_program = self.env['loyalty.program'].sudo().create({
                    'name': name,
                    'program_type': program_type,
                    'pos_ok': True,
                    'ecommerce_ok': False,
                    'trigger': 'auto',
                    'mandatory_promotion': True,
                    'is_selection_promotion': False,
                    #'note_promotion': note_promotion,
                    'applies_to_the_second': True,
                    'applies_by_boxes': True,
                    #'date_from': coupon_date_from,
                    #'date_to': coupon_date_to,
                    'applies_on': applies_on,
                })
                ## Crear regla
                self.env['loyalty.rule'].sudo().create({
                    'program_id': loyalty_program.id,
                    'minimum_qty': 1,
                    'minimum_amount': 0,
                    'reward_point_amount': 1,
                    'product_ids': [(6, 0, [product_id])],
                    'reward_point_mode': 'unit',
                })
                ## Crear recompensa de descuento para el primer producto
                if (discount > 0 or temporary_discount > 0):
                    self.env['loyalty.reward'].sudo().create({
                        'program_id': loyalty_program.id,
                        'reward_type': 'discount',
                        'discount': discount if (discount > 0) else temporary_discount,
                        'discount_applicability': 'specific',
                        'required_points': 1,
                        'discount_product_ids': [(6, 0, [product_id])],
                        'date_from': discount_date_from,
                        'date_to': discount_date_to,
                        'is_temporary': is_temporary,
                    })
                ## Crear recompensa de descuento para el segundo producto
                if coupon_discount > 0:
                    self.env['loyalty.reward'].sudo().create({
                        'program_id': loyalty_program.id,
                        'reward_type': 'discount',
                        'discount': coupon_discount,
                        'discount_applicability': 'specific',
                        'required_points': units_per_box * 2,
                        'discount_product_ids': [(6, 0, [product_id])],
                        'is_main': True,
                        'date_from': coupon_discount_date_from,
                        'date_to': coupon_discount_date_to,
                        'is_temporary': False,
                    })
                product = self.env['product.product'].sudo().browse(product_id)
                # TODO revisar si el producto tiene otras recompensas de descuento
                product.sudo().write({'discount': discount})

            if loyalty_program:
                return loyalty_program.id
            else:
                return False

        ####### Crear programa de cupones #######
        else:
            ## Variables para la recompensa de descuento ##
            discount = float(discount or 0)
            coupon_discount = float(coupon_discount or 0)

            ## Crear programa de cupones para la opcion 1: por unidad ##
            if coupon == 1:
                # Crear programa
                coupon_loyalty_program = self.env['loyalty.program'].sudo().create({
                    'name': f"CUPON-POR-UNIDAD-{product_name}",
                    'program_type': 'coupons',
                    'pos_ok': True,
                    'ecommerce_ok': False,
                    'trigger': 'with_code',
                    'mandatory_promotion': True,
                    'is_selection_promotion': False,
                    #'note_promotion': note_promotion,
                    'applies_by_boxes': False,
                    'is_auto_apply': True,
                    #'date_from': coupon_date_from,
                    #'date_to': coupon_date_to,
                })
                # Crear regla
                self.env['loyalty.rule'].sudo().create({
                    'program_id': coupon_loyalty_program.id,
                    'minimum_qty': 1,
                    'minimum_amount': 0,
                    'reward_point_amount': 1,
                    'product_ids': [(6, 0, [product_id])],
                    'reward_point_mode': 'unit',
                })
                # Crear la recompensa de descuento y actualizar el descuento del producto
                if coupon_discount > 0:
                    self.env['loyalty.reward'].sudo().create({
                        'program_id': coupon_loyalty_program.id,
                        'reward_type': 'discount',
                        'discount': coupon_discount,
                        'discount_applicability': 'specific',
                        'required_points': 1,
                        'discount_product_ids': [(6, 0, [product_id])],
                        'date_from': coupon_discount_date_from,
                        'date_to': coupon_discount_date_to,
                        'is_temporary': False,
                    })
                    product = self.env['product.product'].sudo().browse(product_id)
                    product.sudo().write({'discount': discount})
                # Crear cupones
                wiz = self.env['loyalty.generate.wizard'].sudo().create({
                    'program_id': coupon_loyalty_program.id,
                    'coupon_qty': 500,
                    'display_name': f"CUPON-POR-UNIDAD-{product_name}",
                    'create_date': coupon_discount_date_from,
                    'valid_until': coupon_discount_date_to,
                })
                wiz.generate_coupons()
                # Actualizar nuevamente el descuento para el modal
                product = self.env['product.product'].sudo().browse(product_id)
                product.sudo().write({'discount': discount})

            ## Crear programa de cupones para la opcion 2: por caja ##
            if coupon == 2:
                # Crear programa
                coupon_loyalty_program = self.env['loyalty.program'].sudo().create({
                    'name': f"CUPON-POR-CAJA-{product_name}",
                    'program_type': 'coupons',
                    'pos_ok': True,
                    'ecommerce_ok': False,
                    'trigger': 'with_code',
                    'mandatory_promotion': True,
                    'is_selection_promotion': False,
                    #'note_promotion': note_promotion,
                    'applies_by_boxes': True,
                    'is_auto_apply': True,
                    #'date_from': coupon_date_from,
                    #'date_to': coupon_date_to,
                })
                # Crear la regla
                self.env['loyalty.rule'].sudo().create({
                    'program_id': coupon_loyalty_program.id,
                    'minimum_qty': 1,
                    'minimum_amount': 0,
                    'reward_point_amount': 1,
                    'product_ids': [(6, 0, [product_id])],
                    'reward_point_mode': 'unit',
                })
                # Crear la recompensa de descuento y actualizar el descuento del producto
                if coupon_discount > 0:
                    self.env['loyalty.reward'].sudo().create({
                        'program_id': coupon_loyalty_program.id,
                        'reward_type': 'discount',
                        'discount': coupon_discount,
                        'discount_applicability': 'specific',
                        'required_points': 1,
                        'discount_product_ids': [(6, 0, [product_id])],
                        'date_from': coupon_discount_date_from,
                        'date_to': coupon_discount_date_to,
                        'is_temporary': False,
                    })
                    product = self.env['product.product'].sudo().browse(product_id)
                    product.sudo().write({'discount': discount})
                # Crear cupones
                wiz = self.env['loyalty.generate.wizard'].sudo().create({
                    'program_id': coupon_loyalty_program.id,
                    'coupon_qty': 500,
                    'display_name': f"CUPON-POR-UNIDAD-{product_name}",
                    'create_date': coupon_discount_date_from,
                    'valid_until': coupon_discount_date_to,
                })
                wiz.generate_coupons()
                # Actualizar nuevamente el descuento para el modal
                product = self.env['product.product'].sudo().browse(product_id)
                product.sudo().write({'discount': discount})

            return coupon_loyalty_program.id
            # if coupon_loyalty_program:
            #    return coupon_loyalty_program.id
            # else:
            #    return False

    @api.model
    def save_product_info_and_loyalty_data(self, data):
        """
        Guarda la información del producto y los datos del programa de lealtad.

        :param data: Diccionario con la información del producto y los datos del programa de lealtad.
        :return: Respuesta HTTP indicando el éxito o fracaso de la operación.


        """

        try:
            product_info = data[0].get('product_info', {})
            product_id = product_info.get('product_id')
            product_name = product_info.get('name')
            laboratory_id = product_info.get('laboratory_id')
            brand_id = product_info.get('brand_id')
            loyalty_info = data[0].get('loyalty_info')
            mandatory_promotion = loyalty_info.get('mandatory_promotion')
            note_promotion = loyalty_info.get('note_promotion')
            coupon = loyalty_info.get('coupon', 0)
            loyalty_card = loyalty_info.get('loyalty_card', 0)
            product = self.env['product.product'].sudo().browse(int(product_id))
            if not product:
                return Response(
                    json.dumps({'error': 'Producto no encontrado'}),
                    status=404,
                    content_type='application/json'
                )

            # Actualizar información básica del producto
            product_template_vals = {
                'name': product_name if len(product_name) > 0 else product.product_tmpl_id.name,
                # 'list_price': product_info.get('list_price'),
                'coupon': coupon,
                'laboratory_id': laboratory_id,
                'brand_id': brand_id,
            }
            product.product_tmpl_id.sudo().with_context(skip_update_form_product_api=True).write(product_template_vals)

            # Unidades por caja del producto
            units_per_box = product.product_tmpl_id.uom_po_id.factor_inv

            ######## Actualizar/crear programa de tipo promociones o tarjeta de lealtad ########

            ### Variables para el tipo de programa (promoción o tarjeta de lealtad)
            loyalty_program = False
            program_id = loyalty_info.get('program_id')
            if program_id:
                loyalty_program = self.env['loyalty.program'].sudo().browse(program_id)
            loyalty_card_program = False
            loyalty_card_program_id = loyalty_info.get('loyalty_card_program_id')
            if loyalty_card_program_id:
                loyalty_card_program = self.env['loyalty.program'].sudo().browse(loyalty_card_program_id)

            ### Variables en común para recompensa de descuento ###
            reward_discount_value = float(loyalty_info.get('discount') or 0)
            temporary_reward_discount_value = float(loyalty_info.get('temporary_discount') or 0)
            is_temporary = False
            if temporary_reward_discount_value > 0:
                reward_discount_value = 0
                is_temporary = True

            coupon_reward_discount_value = float(loyalty_info.get('coupon_discount') or 0)

            ### Variables en común para recompensa de producto gratis ###
            reward_product_qty = int(loyalty_info.get('product_reward_qty') or 0)
            required_points = int(loyalty_info.get('product_reward_required_points') or 0)

            ### Variables (ids) para recompensa de descuento y producto gratis para el programa de tipo Promociones ###
            reward_discount_id = loyalty_info.get('discount_reward_id')
            temporary_reward_discount_id = loyalty_info.get('temporary_discount_reward_id')
            reward_discount_id_2 = loyalty_info.get('discount_reward_id_2')
            reward_product_id = loyalty_info.get('product_reward_id')

            ### Variables (ids) para recompensa de descuento y producto gratis para el programa de tipo Tarjeta de Lealtad ###
            loyalty_card_reward_discount_id = loyalty_info.get('loyalty_card_discount_reward_id')
            loyalty_card_temporary_reward_discount_id = loyalty_info.get('loyalty_card_temporary_discount_reward_id')
            loyalty_card_reward_discount_id_2 = loyalty_info.get('loyalty_card_discount_reward_id_2')
            loyalty_card_reward_product_id = loyalty_info.get('loyalty_card_product_reward_id')

            ### Verificar si existen programas archivados de tipo Promociones, y desarchivar si loyalty_card es False
            if not loyalty_program and not loyalty_card_program and not loyalty_card:
                loyalty_program = self.env['loyalty.program'].restore_last_archived_program(product_id=product_id, program_type='promotion')
                if loyalty_program:
                    # Preprocesar programa de Tipo Promociones desarchivado
                    archived_discount_reward_info = loyalty_program.archived_discount_reward_info
                    reward_discount_id = loyalty_program.preprocess_unarchived_program(product_id=product_id, reward_info=archived_discount_reward_info)

            ### Verificar si existen programas archivados de tipo Tarjeta de Lealtad, y desarchivar si loyalty_card es True
            if not loyalty_program and not loyalty_card_program and loyalty_card:
                loyalty_card_program = self.env['loyalty.program'].restore_last_archived_program(product_id=product_id, program_type='loyalty')
                if loyalty_card_program:
                    # Preprocesar programa de Tipo Tarjeta de Lealtad desarchivado
                    archived_discount_reward_info = loyalty_card_program.archived_discount_reward_info
                    loyalty_card_reward_discount_id = loyalty_card_program.preprocess_unarchived_program(product_id=product_id, reward_info=archived_discount_reward_info)

            ### Funcion para actualizar programa de tipo promociones o tarjeta de lealtad ###
            def update_promotion_or_loyalty_card(loyalty_program,
                                                 reward_discount_id, temporary_reward_discount_id, reward_discount_id_2, reward_product_id,
                                                 reward_discount_value, temporary_reward_discount_value, coupon_reward_discount_value,
                                                 reward_product_qty, required_points, coupon):
                ### Variable de acuerdo al tipo de programa de Promociones y Tarjeta de Lealtad
                if not loyalty_card:
                    name = f"POS-{product_name}"
                    applies_on = 'current'
                else:
                    name = f"POS-TARJETA-LEALTAD-{product_name}"
                    applies_on = 'both'

                ### Actualizar programa de promociones ###
                if coupon is None:
                    # Archivar programa en caso de que se envie el descuento y la base o promocion en cero
                    if (reward_discount_value==0 and temporary_reward_discount_value==0) and (reward_product_qty==0 or required_points==0):
                        # Guardar ID y descuento para recompensa de descuento normal
                        if reward_discount_id:
                            archived_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id, reward_type="discount")
                            loyalty_program.sudo().write({
                                'archived_discount_reward_info': archived_discount_reward_info
                            })
                        # Guardar ID y descuento para recompensa de descuento temporal
                        if temporary_reward_discount_id:
                            archived_temporary_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=temporary_reward_discount_id, reward_type="discount")
                            loyalty_program.sudo().write({
                                'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                            })

                        # Archivar programa, y las reglas y recompensas
                        loyalty_program.archive_program()

                        # Actualizar descuento en el producto
                        product.sudo().write({'discount': 0})

                    # Caso contrario actualizar programa
                    else:
                        # actualizar programa
                        loyalty_program.sudo().write({
                            'name': name,
                            'mandatory_promotion': mandatory_promotion,
                            'is_selection_promotion': not mandatory_promotion,
                            'note_promotion': note_promotion,
                            'applies_to_the_second': False,
                            'applies_by_boxes': False,
                            'applies_on': applies_on,
                        })

                        # Archivar recompensa de descuento al segundo producto en caso de existir
                        if reward_discount_id_2:
                            # Guardar ID y descuento de la recompensa en el programa
                            archived_second_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id_2, reward_type="discount")
                            loyalty_program.sudo().write({
                                'archived_second_discount_reward_info': archived_second_discount_reward_info
                            })
                            # Archivar recompensa
                            discount_reward_2 = self.env['loyalty.reward'].sudo().browse(reward_discount_id_2)
                            if discount_reward_2:
                                discount_reward_2.sudo().write({
                                    'active': False,
                                })

                        # Inicializar variable flag para eliminar recompensa de descuento
                        flag_to_delete_discount_reward = False

                        # Archivar recompensa normal, si el descuento temporal es mayor a cero
                        if reward_discount_id and temporary_reward_discount_value > 0:
                            # Archivar recompensa normal
                            discount_reward = self.env['loyalty.reward'].sudo().browse(reward_discount_id)
                            if discount_reward:
                                # Guardar ID y descuento de la recompensa en el programa
                                archived_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id, reward_type="discount")
                                loyalty_program.sudo().write({
                                    'archived_discount_reward_info': archived_discount_reward_info
                                })
                                # Archivar recompensa
                                discount_reward.sudo().write({
                                    'active': False,
                                })

                        # Archivar recompensa temporal, si el descuento normal es mayor a cero
                        if temporary_reward_discount_id and reward_discount_value > 0:
                            discount_reward = self.env['loyalty.reward'].sudo().browse(temporary_reward_discount_id)
                            # Archivar recompensa temporal
                            if discount_reward:
                                # Guardar ID y descuento de la recompensa en el programa
                                archived_temporary_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=temporary_reward_discount_id, reward_type="discount")
                                loyalty_program.sudo().write({
                                    'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                                })
                                # Archivar recompensa
                                discount_reward.sudo().write({
                                    'active': False,
                                })

                        # Desarchivar recompensa de descuento normal en caso de existir, si el descuento normal es mayor a cero. Y archivar la recompensa temporal
                        if not reward_discount_id and reward_discount_value > 0:
                            archived_discount_reward_info = loyalty_program.archived_discount_reward_info
                            reward_discount_id = loyalty_program.restore_archived_reward_by_id(reward_info=archived_discount_reward_info, reward_type='discount', product_id=product_id).id
                            # Archivar recompensa temporal
                            if temporary_reward_discount_id:
                                discount_reward = self.env['loyalty.reward'].sudo().browse(temporary_reward_discount_id)
                                if discount_reward:
                                    # Guardar ID y descuento de la recompensa en el programa
                                    archived_temporary_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=temporary_reward_discount_id, reward_type="discount")
                                    loyalty_program.sudo().write({
                                        'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                                    })
                                    # Archivar recompensa
                                    discount_reward.sudo().write({
                                        'active': False,
                                    })

                        # Desarchivar recompensa de descuento temporal en caso de existir, si el descuento temporal es mayor a cero. Y archivar la recompensa normal
                        if not temporary_reward_discount_id and temporary_reward_discount_value > 0:
                            archived_temporary_discount_reward_info = loyalty_program.archived_temporary_discount_reward_info
                            temporary_reward_discount_id = loyalty_program.restore_archived_reward_by_id(reward_info=archived_temporary_discount_reward_info, reward_type='discount', product_id=product_id).id
                            # Archivar recompensa normal
                            if reward_discount_id:
                                discount_reward = self.env['loyalty.reward'].sudo().browse(reward_discount_id)
                                if discount_reward:
                                    # Guardar ID y descuento de la recompensa en el programa
                                    archived_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id, reward_type="discount")
                                    loyalty_program.sudo().write({
                                        'archived_discount_reward_info': archived_discount_reward_info
                                    })
                                    # Archivar recompensa
                                    discount_reward.sudo().write({
                                        'active': False,
                                    })

                        # Desarchivar recompensa de producto en caso de existir, y si la base y promocion son mayores a cero
                        if not reward_product_id and (reward_product_qty > 0 and required_points > 0):
                            archived_product_reward_info = loyalty_program.archived_product_reward_info
                            reward_product_id = loyalty_program.restore_archived_reward_by_id(reward_info=archived_product_reward_info, reward_type='product', product_id=product_id).id

                        # Actualizar recompensa de descuento si no existe la de producto
                        if (reward_discount_id and reward_discount_value > 0) or (temporary_reward_discount_id and temporary_reward_discount_value > 0) and not reward_product_id:
                            discount_reward = None
                            # Recompensa de descuento normal
                            if reward_discount_id and reward_discount_value > 0:
                                discount_reward = self.env['loyalty.reward'].sudo().browse(reward_discount_id)
                            # Recompensa de descuento temporal
                            elif temporary_reward_discount_id and temporary_reward_discount_value > 0:
                                discount_reward = self.env['loyalty.reward'].sudo().browse(temporary_reward_discount_id)
                            # Actualizar descuento
                            if discount_reward:
                                discount_reward.sudo().write({
                                    'is_main': False,
                                    'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value,
                                    'required_points': 1,
                                    'date_from': loyalty_info.get('discount_date_from') or None,
                                    'date_to': loyalty_info.get('discount_date_to') or None,
                                    'is_temporary': is_temporary,
                                })
                                # TODO revisar si el producto tiene otras recompensas de descuento
                                product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})

                        # Actualizar recompensa de descuento si existe la de producto
                        elif (reward_discount_id and reward_discount_value > 0) or (temporary_reward_discount_id and temporary_reward_discount_value > 0) and reward_product_id:
                            discount_reward = None
                            # Recompensa de descuento normal
                            if reward_discount_id and reward_discount_value > 0:
                                discount_reward = self.env['loyalty.reward'].sudo().browse(reward_discount_id)
                            # Recompensa de descuento temporal
                            elif temporary_reward_discount_id and temporary_reward_discount_value > 0:
                                discount_reward = self.env['loyalty.reward'].sudo().browse(temporary_reward_discount_id)
                            # Actualizar recompensa de descuento
                            if discount_reward:
                                discount_reward.sudo().write({
                                    'is_main': False,
                                    'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value,
                                    'required_points': 0 if mandatory_promotion else 1,
                                    'date_from': loyalty_info.get('discount_date_from') or None,
                                    'date_to': loyalty_info.get('discount_date_to') or None,
                                    'is_temporary': is_temporary,
                                })
                                # TODO revisar si el producto tiene otras recompensas de descuento
                                product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})

                        # Archivar la recompensa de descuento si el valor es 0, y ademas existe producto gratis para evitar error de programa sin recompensas
                        if (reward_discount_id and reward_discount_value == 0) or (temporary_reward_discount_id and temporary_reward_discount_value == 0):
                            discount_reward = None
                            # Recompensa de descuento normal
                            if reward_discount_id and reward_discount_value == 0:
                                discount_reward = self.env['loyalty.reward'].sudo().browse(reward_discount_id)
                            # Recompensa de descuento temporal
                            elif temporary_reward_discount_id and temporary_reward_discount_value == 0:
                                discount_reward = self.env['loyalty.reward'].sudo().browse(temporary_reward_discount_id)
                            # Archivar recompensa
                            if discount_reward:
                                if reward_product_id:
                                    product_reward = self.env['loyalty.reward'].sudo().browse(reward_product_id)
                                    if product_reward:
                                        if reward_discount_id:
                                            archived_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id, reward_type="discount")
                                            loyalty_program.sudo().write({
                                                'archived_discount_reward_info': archived_discount_reward_info
                                            })
                                        elif temporary_reward_discount_id:
                                            archived_temporary_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=temporary_reward_discount_id, reward_type="discount")
                                            loyalty_program.sudo().write({
                                                'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                                            })
                                        discount_reward.sudo().write({
                                            'active': False,
                                        })
                                        # TODO revisar si el producto tiene otras recompensas de descuento
                                        product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                                else:
                                    flag_to_delete_discount_reward = True
                        # Crear la recompensa de descuento si no existe, y si el descuento es mayor a cero
                        if (not reward_discount_id and reward_discount_value > 0) or (not temporary_reward_discount_id and temporary_reward_discount_value > 0):
                            self.env['loyalty.reward'].sudo().create({
                                'program_id': loyalty_program.id,
                                'reward_type': 'discount',
                                'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value,
                                'discount_applicability': 'specific',
                                'required_points': 0 if mandatory_promotion else 1,
                                'discount_product_ids': [(6, 0, [product.id])],
                                'date_from': loyalty_info.get('discount_date_from') or None,
                                'date_to': loyalty_info.get('discount_date_to') or None,
                                'is_temporary': is_temporary,
                            })
                            # TODO revisar si el producto tiene otras recompensas de descuento
                            product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})

                        # Actualizar recompensa de producto gratis
                        # Si tiene recompesa de producto y la cantidad y puntos son mayores a 0, se actualiza
                        if reward_product_id and (reward_product_qty > 0 and required_points > 0):
                            product_reward = self.env['loyalty.reward'].sudo().browse(reward_product_id)
                            if product_reward:
                                product_reward.sudo().write({
                                    'reward_product_qty': reward_product_qty if (reward_product_qty > 0) else 1,
                                    'required_points': required_points if (required_points > 0) else 1,
                                    'is_main': True,
                                    'date_from': loyalty_info.get('product_date_from') or None,
                                    'date_to': loyalty_info.get('product_date_to') or None,
                                    'is_temporary': False,
                                })

                        # Archivar la recompensa de producto si la cantidad o puntos son 0
                        elif reward_product_id and (reward_product_qty == 0 or required_points == 0):
                            product_reward = self.env['loyalty.reward'].sudo().browse(reward_product_id)
                            if product_reward:
                                # Guardar ID, base y promocion de la recompensa en el programa
                                archived_product_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_product_id, reward_type="product")
                                loyalty_program.sudo().write({
                                    'archived_product_reward_info': archived_product_reward_info
                                })
                                # Archivar recompensa de producto
                                product_reward.sudo().write({
                                    'active': False,
                                })

                        # Crear la recompensa de producto si no tiene y la cantidad y puntos son mayores a 0
                        elif not reward_product_id and (reward_product_qty > 0 and required_points > 0):
                            self.env['loyalty.reward'].sudo().create({
                                'program_id': loyalty_program.id,
                                'reward_type': 'product',
                                'reward_product_qty': reward_product_qty if (reward_product_qty > 0) else 1,
                                'required_points': required_points if (required_points > 0) else 1,
                                'reward_product_id': product.id,
                                'is_main': True,
                                'date_from': loyalty_info.get('product_date_from') or None,
                                'date_to': loyalty_info.get('product_date_to') or None,
                                'is_temporary': False,
                            })
                            if flag_to_delete_discount_reward:
                                discount_reward = None
                                # Recompensa de descuento normal
                                if reward_discount_id and reward_discount_value == 0:
                                    discount_reward = self.env['loyalty.reward'].sudo().browse(reward_discount_id)
                                # Recompensa de descuento temporal
                                elif temporary_reward_discount_id and temporary_reward_discount_value == 0:
                                    discount_reward = self.env['loyalty.reward'].sudo().browse(temporary_reward_discount_id)
                                if discount_reward:
                                    if reward_discount_id:
                                        archived_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id, reward_type="discount")
                                        loyalty_program.sudo().write({
                                            'archived_discount_reward_info': archived_discount_reward_info
                                        })
                                    elif temporary_reward_discount_id:
                                        archived_temporary_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=temporary_reward_discount_id, reward_type="discount")
                                        loyalty_program.sudo().write({
                                            'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                                        })
                                    discount_reward.sudo().write({
                                        'active': False,
                                    })
                                    # TODO revisar si el producto tiene otras recompensas de descuento
                                    product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})

                        # Actualizar required_points
                        Reward = self.env['loyalty.reward']
                        discount_reward_result = Reward.search([('program_id', '=', loyalty_program.id), ('reward_type', '=', 'discount')], limit=1)
                        product_reward_result = Reward.search([('program_id', '=', loyalty_program.id), ('reward_type', '=', 'product')], limit=1)
                        if discount_reward_result and product_reward_result:
                            discount_reward_result.sudo().write({
                                'required_points': 0 if mandatory_promotion else 1,
                            })
                        elif discount_reward_result and not product_reward_result:
                            discount_reward_result.sudo().write({
                                'required_points': 1,
                            })
                        # Actualizar descuento nuevamente para el modal
                        product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})

                ### Actualizar programa de promociones para el descuento al segundo producto ###
                elif coupon==3:
                    ## Variables de fecha
                    discount_date_from = loyalty_info.get('discount_date_from') or None
                    discount_date_to = loyalty_info.get('discount_date_to') or None
                    coupon_discount_date_from = loyalty_info.get('coupon_discount_date_from') or None
                    coupon_discount_date_to = loyalty_info.get('coupon_discount_date_to') or None

                    ## Actualizar programa
                    loyalty_program.sudo().write({
                        'name': name,
                        'mandatory_promotion': True,
                        'is_selection_promotion': False,
                        'note_promotion': '',
                        'applies_to_the_second': True,
                        'applies_by_boxes': True,
                        #'date_from': coupon_date_from,
                        #'date_to': coupon_date_to,
                        'applies_on': applies_on,
                    })

                    ## Archivar recompensa de producto gratis en caso de existir
                    if reward_product_id:
                        reward_product = self.env['loyalty.reward'].sudo().browse(reward_product_id)
                        if reward_product:
                            # Guardar ID, base y promocion de la recompensa en el programa
                            archived_product_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_product_id, reward_type="product")
                            loyalty_program.sudo().write({
                                'archived_product_reward_info': archived_product_reward_info
                            })
                            # Archivar recompensa de producto
                            reward_product.sudo().write({
                                'active': False,
                            })

                    # Archivar recompensa normal, si el descuento temporal es mayor a cero
                    if reward_discount_id and temporary_reward_discount_value > 0:
                        # Archivar recompensa normal
                        discount_reward = self.env['loyalty.reward'].sudo().browse(reward_discount_id)
                        if discount_reward:
                            # Guardar ID y descuento de la recompensa en el programa
                            archived_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id, reward_type="discount")
                            loyalty_program.sudo().write({
                                'archived_discount_reward_info': archived_discount_reward_info
                            })
                            # Archivar recompensa
                            discount_reward.sudo().write({
                                'active': False,
                            })

                    # Archivar recompensa temporal, si el descuento normal es mayor a cero
                    if temporary_reward_discount_id and reward_discount_value > 0:
                        discount_reward = self.env['loyalty.reward'].sudo().browse(temporary_reward_discount_id)
                        # Archivar recompensa temporal
                        if discount_reward:
                            # Guardar ID y descuento de la recompensa en el programa
                            archived_temporary_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=temporary_reward_discount_id, reward_type="discount")
                            loyalty_program.sudo().write({
                                'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                            })
                            # Archivar recompensa
                            discount_reward.sudo().write({
                                'active': False,
                            })

                    # Desarchivar recompensa de descuento normal en caso de existir, si el descuento normal es mayor a cero. Y archivar la recompensa temporal
                    if not reward_discount_id and reward_discount_value > 0:
                        archived_discount_reward_info = loyalty_program.archived_discount_reward_info
                        reward_discount_id = loyalty_program.restore_archived_reward_by_id(reward_info=archived_discount_reward_info, reward_type='discount', product_id=product_id).id
                        # Archivar recompensa temporal
                        if temporary_reward_discount_id:
                            discount_reward = self.env['loyalty.reward'].sudo().browse(temporary_reward_discount_id)
                            if discount_reward:
                                # Guardar ID y descuento de la recompensa en el programa
                                archived_temporary_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=temporary_reward_discount_id, reward_type="discount")
                                loyalty_program.sudo().write({
                                    'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                                })
                                # Archivar recompensa
                                discount_reward.sudo().write({
                                    'active': False,
                                })

                    # Desarchivar recompensa de descuento temporal en caso de existir, si el descuento temporal es mayor a cero. Y archivar la recompensa normal
                    if not temporary_reward_discount_id and temporary_reward_discount_value > 0:
                        archived_temporary_discount_reward_info = loyalty_program.archived_temporary_discount_reward_info
                        temporary_reward_discount_id = loyalty_program.restore_archived_reward_by_id(reward_info=archived_temporary_discount_reward_info, reward_type='discount', product_id=product_id).id
                        # Archivar recompensa normal
                        if reward_discount_id:
                            discount_reward = self.env['loyalty.reward'].sudo().browse(reward_discount_id)
                            if discount_reward:
                                # Guardar ID y descuento de la recompensa en el programa
                                archived_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id, reward_type="discount")
                                loyalty_program.sudo().write({
                                    'archived_discount_reward_info': archived_discount_reward_info
                                })
                                # Archivar recompensa
                                discount_reward.sudo().write({
                                    'active': False,
                                })

                    # Desarchivar segunda recompensa de descuento en caso de existir, y si el descuento de cupones es mayor a cero
                    if not reward_discount_id_2 and coupon_reward_discount_value > 0:
                        archived_second_discount_reward_info = loyalty_program.archived_second_discount_reward_info
                        reward_discount_id_2 = loyalty_program.restore_archived_reward_by_id(reward_info=archived_second_discount_reward_info, reward_type='discount', product_id=product_id).id

                    # Actualizar la recompensa de descuento normal del primer producto
                    if reward_discount_id:
                        discount_reward = self.env['loyalty.reward'].sudo().browse(reward_discount_id)
                        if discount_reward:
                            if reward_discount_value > 0:
                                discount_reward.sudo().write({
                                    'is_main': False,
                                    'discount': reward_discount_value,
                                    'required_points': 1,
                                    'date_from': discount_date_from,
                                    'date_to': discount_date_to,
                                    'is_temporary': False,
                                })
                                product.sudo().write({'discount': reward_discount_value})
                            else:
                                archived_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id, reward_type="discount")
                                loyalty_program.sudo().write({
                                    'archived_discount_reward_info': archived_discount_reward_info
                                })
                                discount_reward.sudo().write({
                                    'active': False,
                                })
                                product.sudo().write({'discount': reward_discount_value})
                    else:
                        if reward_discount_value > 0:
                            self.env['loyalty.reward'].sudo().create({
                                'program_id': loyalty_program.id,
                                'reward_type': 'discount',
                                'discount': reward_discount_value,
                                'discount_applicability': 'specific',
                                'required_points': 1,
                                'discount_product_ids': [(6, 0, [product_id])],
                                'date_from': discount_date_from,
                                'date_to': discount_date_to,
                                'is_temporary': False,
                            })
                            product.sudo().write({'discount': reward_discount_value})

                    # Actualizar la recompensa de descuento temporal del primer producto
                    if temporary_reward_discount_id:
                        temporary_discount_reward = self.env['loyalty.reward'].sudo().browse(temporary_reward_discount_id)
                        if temporary_discount_reward:
                            if temporary_reward_discount_value > 0:
                                temporary_discount_reward.sudo().write({
                                    'is_main': False,
                                    'discount': temporary_reward_discount_value,
                                    'required_points': 1,
                                    'date_from': discount_date_from,
                                    'date_to': discount_date_to,
                                    'is_temporary': True,
                                })
                                product.sudo().write({'discount': temporary_reward_discount_value})
                            else:
                                archived_temporary_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=temporary_reward_discount_id, reward_type="discount")
                                loyalty_program.sudo().write({
                                    'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                                })
                                temporary_discount_reward.sudo().write({
                                    'active': False,
                                })
                                product.sudo().write({'discount': temporary_reward_discount_value})
                    else:
                        if temporary_reward_discount_value > 0:
                            self.env['loyalty.reward'].sudo().create({
                                'program_id': loyalty_program.id,
                                'reward_type': 'discount',
                                'discount': temporary_reward_discount_value,
                                'discount_applicability': 'specific',
                                'required_points': 1,
                                'discount_product_ids': [(6, 0, [product_id])],
                                'date_from': discount_date_from,
                                'date_to': discount_date_to,
                                'is_temporary': True,
                            })
                            product.sudo().write({'discount': temporary_reward_discount_value})

                    # Actualizar la recompensa de descuento del segundo producto
                    if reward_discount_id_2:
                        discount_reward_2 = self.env['loyalty.reward'].sudo().browse(reward_discount_id_2)
                        if discount_reward_2:
                            if coupon_reward_discount_value > 0:
                                discount_reward_2.sudo().write({
                                    'is_main': True,
                                    'discount': coupon_reward_discount_value,
                                    'required_points': units_per_box * 2,
                                    'date_from': coupon_discount_date_from,
                                    'date_to': coupon_discount_date_to,
                                    'is_temporary': False,
                                })
                                product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                            else:
                                archived_second_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id_2, reward_type="discount")
                                loyalty_program.sudo().write({
                                    'archived_second_discount_reward_info': archived_second_discount_reward_info
                                })
                                discount_reward_2.sudo().write({
                                    'active': False,
                                })
                                product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                    else:
                        if coupon_reward_discount_value > 0:
                            self.env['loyalty.reward'].sudo().create({
                                'program_id': loyalty_program.id,
                                'reward_type': 'discount',
                                'discount': coupon_reward_discount_value,
                                'discount_applicability': 'specific',
                                'required_points': units_per_box * 2,
                                'discount_product_ids': [(6, 0, [product_id])],
                                'is_main': True,
                                'date_from': coupon_discount_date_from,
                                'date_to': coupon_discount_date_to,
                                'is_temporary': False,
                            })
                            product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})

                    # Actualizar descuento nuevamente para el modal
                    product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})

            ### Actualizar programa de tipo Promociones o crear programa de tipo Tarjeta de Lealtad ###
            if loyalty_program:
                if not loyalty_card:
                    # Actualizar programa de tipo Promociones
                    update_promotion_or_loyalty_card(
                        loyalty_program=loyalty_program,
                        reward_discount_id=reward_discount_id,
                        temporary_reward_discount_id=temporary_reward_discount_id,
                        reward_discount_id_2=reward_discount_id_2,
                        reward_product_id=reward_product_id,
                        reward_discount_value=reward_discount_value,
                        temporary_reward_discount_value=temporary_reward_discount_value,
                        coupon_reward_discount_value=coupon_reward_discount_value,
                        reward_product_qty=reward_product_qty,
                        required_points=required_points,
                        coupon=coupon if coupon==3 else None
                    )
                else:
                    ## Guardar informacion de las recompensas antes de archivar ##
                    # Guardar ID y descuento para recompensa de descuento normal
                    if reward_discount_id:
                        archived_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id, reward_type="discount")
                        loyalty_program.sudo().write({
                            'archived_discount_reward_info': archived_discount_reward_info
                        })
                    # Guardar ID y descuento para recompensa de descuento temporal
                    if temporary_reward_discount_id:
                        archived_temporary_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=temporary_reward_discount_id, reward_type="discount")
                        loyalty_program.sudo().write({
                            'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                        })
                    # Guardar ID y descuento para la segunda recompensa de descuento
                    if reward_discount_id_2:
                        archived_second_discount_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_discount_id_2, reward_type="discount")
                        loyalty_program.sudo().write({
                            'archived_second_discount_reward_info': archived_second_discount_reward_info
                        })
                    # Guardar ID, base y promocion para la recompensa de producto gratis
                    if reward_product_id:
                        archived_product_reward_info = loyalty_program.obtain_char_id_and_values(reward_id=reward_product_id, reward_type="product")
                        loyalty_program.sudo().write({
                            'archived_product_reward_info': archived_product_reward_info
                        })

                    # Archivar programa de tipo Promociones, y las reglas y recompensas
                    loyalty_program.archive_program()

                    # Desarchivar programa de tipo Tarjeta de Lealtad en caso de existir
                    loyalty_card_program = self.env['loyalty.program'].restore_last_archived_program(product_id=product_id, program_type='loyalty')
                    if loyalty_card_program:
                        # Preprocesar programa de Tipo Tarjeta de Lealtad desarchivado
                        archived_discount_reward_info = loyalty_card_program.archived_discount_reward_info
                        loyalty_card_reward_discount_id = loyalty_card_program.preprocess_unarchived_program(product_id=product_id, reward_info=archived_discount_reward_info)

                        # Actualizar programa de tipo Tarjeta de Lealtad
                        update_promotion_or_loyalty_card(
                            loyalty_program=loyalty_card_program,
                            reward_discount_id=loyalty_card_reward_discount_id,
                            temporary_reward_discount_id=loyalty_card_temporary_reward_discount_id,
                            reward_discount_id_2=loyalty_card_reward_discount_id_2,
                            reward_product_id=loyalty_card_reward_product_id,
                            reward_discount_value=reward_discount_value,
                            temporary_reward_discount_value=temporary_reward_discount_value,
                            coupon_reward_discount_value=coupon_reward_discount_value,
                            reward_product_qty=reward_product_qty,
                            required_points=required_points,
                            coupon=coupon if coupon == 3 else None
                        )
                    else:
                        # Crear programa de tipo Tarjeta de Lealtad
                        self.create_loyalty_program(
                            product_id=product.id,
                            product_name=product_info.get('name'),
                            units_per_box=units_per_box,
                            mandatory_promotion=loyalty_info.get('mandatory_promotion'),
                            discount_date_from=loyalty_info.get('discount_date_from') or None,
                            discount_date_to=loyalty_info.get('discount_date_to') or None,
                            product_date_from=loyalty_info.get('product_date_from') or None,
                            product_date_to=loyalty_info.get('product_date_to') or None,
                            coupon_discount_date_from=loyalty_info.get('coupon_discount_date_from') or None,
                            coupon_discount_date_to=loyalty_info.get('coupon_discount_date_to') or None,
                            discount=reward_discount_value,
                            temporary_discount=temporary_reward_discount_value,
                            coupon_discount=loyalty_info.get('coupon_discount', 0),
                            reward_product_qty=loyalty_info.get('product_reward_qty', 0),
                            required_points=loyalty_info.get('product_reward_required_points', 0),
                            note_promotion=loyalty_info.get('note_promotion', ''),
                            coupon=coupon if coupon==3 else None,
                            loyalty_card=loyalty_card,
                        )
            ### Actualizar programa de tipo Tarjeta de Lealtad o crear programa de tipo Promociones ###
            elif loyalty_card_program:
                if loyalty_card:
                    # Actualizar programa de tipo Tarjeta de Lealtad
                    update_promotion_or_loyalty_card(
                        loyalty_program=loyalty_card_program,
                        reward_discount_id=loyalty_card_reward_discount_id,
                        temporary_reward_discount_id=loyalty_card_temporary_reward_discount_id,
                        reward_discount_id_2=loyalty_card_reward_discount_id_2,
                        reward_product_id=loyalty_card_reward_product_id,
                        reward_discount_value=reward_discount_value,
                        temporary_reward_discount_value=temporary_reward_discount_value,
                        coupon_reward_discount_value=coupon_reward_discount_value,
                        reward_product_qty=reward_product_qty,
                        required_points=required_points,
                        coupon=coupon if coupon==3 else None
                    )
                else:
                    ## Guardar informacion de las recompensas antes de archivar ##
                    # Guardar ID y descuento para recompensa de descuento normal
                    if loyalty_card_reward_discount_id:
                        archived_discount_reward_info = loyalty_card_program.obtain_char_id_and_values(reward_id=loyalty_card_reward_discount_id, reward_type="discount")
                        loyalty_card_program.sudo().write({
                            'archived_discount_reward_info': archived_discount_reward_info
                        })
                    # Guardar ID y descuento para recompensa de descuento temporal
                    if loyalty_card_temporary_reward_discount_id:
                        archived_temporary_discount_reward_info = loyalty_card_program.obtain_char_id_and_values(reward_id=loyalty_card_temporary_reward_discount_id, reward_type="discount")
                        loyalty_card_program.sudo().write({
                            'archived_temporary_discount_reward_info': archived_temporary_discount_reward_info
                        })
                    # Guardar ID y descuento para la segunda recompensa de descuento
                    if loyalty_card_reward_discount_id_2:
                        archived_second_discount_reward_info = loyalty_card_program.obtain_char_id_and_values(reward_id=loyalty_card_reward_discount_id_2, reward_type="discount")
                        loyalty_card_program.sudo().write({
                            'archived_second_discount_reward_info': archived_second_discount_reward_info
                        })
                    # Guardar ID, base y promocion para la recompensa de producto gratis
                    if loyalty_card_reward_product_id:
                        archived_product_reward_info = loyalty_card_program.obtain_char_id_and_values(reward_id=loyalty_card_reward_product_id, reward_type="product")
                        loyalty_card_program.sudo().write({
                            'archived_product_reward_info': archived_product_reward_info
                        })

                    # Archivar programa de tipo Tarjeta de lealtad, y las reglas y recompensas
                    loyalty_card_program.archive_program()

                    # Desarchivar programa de tipo Promociones en caso de existir
                    loyalty_program = self.env['loyalty.program'].restore_last_archived_program(product_id=product_id, program_type='promotion')
                    if loyalty_program:
                        # Preprocesar programa de Tipo Promociones desarchivado
                        archived_discount_reward_info = loyalty_program.archived_discount_reward_info
                        reward_discount_id = loyalty_program.preprocess_unarchived_program(product_id=product_id, reward_info=archived_discount_reward_info)

                        # Actualizar programa de tipo Promociones
                        update_promotion_or_loyalty_card(
                            loyalty_program=loyalty_program,
                            reward_discount_id=reward_discount_id,
                            temporary_reward_discount_id=temporary_reward_discount_id,
                            reward_discount_id_2=reward_discount_id_2,
                            reward_product_id=reward_product_id,
                            reward_discount_value=reward_discount_value,
                            temporary_reward_discount_value=temporary_reward_discount_value,
                            coupon_reward_discount_value=coupon_reward_discount_value,
                            reward_product_qty=reward_product_qty,
                            required_points=required_points,
                            coupon=coupon if coupon == 3 else None
                        )
                    else:
                        # Crear programa de tipo Promociones
                        self.create_loyalty_program(
                            product_id=product.id,
                            product_name=product_info.get('name'),
                            units_per_box=units_per_box,
                            mandatory_promotion=loyalty_info.get('mandatory_promotion'),
                            discount_date_from=loyalty_info.get('discount_date_from') or None,
                            discount_date_to=loyalty_info.get('discount_date_to') or None,
                            product_date_from=loyalty_info.get('product_date_from') or None,
                            product_date_to=loyalty_info.get('product_date_to') or None,
                            coupon_discount_date_from=loyalty_info.get('coupon_discount_date_from') or None,
                            coupon_discount_date_to=loyalty_info.get('coupon_discount_date_to') or None,
                            discount=reward_discount_value,
                            temporary_discount=temporary_reward_discount_value,
                            coupon_discount=loyalty_info.get('coupon_discount', 0),
                            reward_product_qty=loyalty_info.get('product_reward_qty', 0),
                            required_points=loyalty_info.get('product_reward_required_points', 0),
                            note_promotion=loyalty_info.get('note_promotion', ''),
                            coupon=coupon if coupon==3 else None,
                            loyalty_card=loyalty_card,
                        )
            else:
                # Crear programa de tipo Promociones o Tarjeta de Lealtad
                self.create_loyalty_program(
                    product_id=product.id,
                    product_name=product_info.get('name'),
                    units_per_box=units_per_box,
                    mandatory_promotion=loyalty_info.get('mandatory_promotion'),
                    discount_date_from=loyalty_info.get('discount_date_from') or None,
                    discount_date_to=loyalty_info.get('discount_date_to') or None,
                    product_date_from=loyalty_info.get('product_date_from') or None,
                    product_date_to=loyalty_info.get('product_date_to') or None,
                    coupon_discount_date_from=loyalty_info.get('coupon_discount_date_from') or None,
                    coupon_discount_date_to=loyalty_info.get('coupon_discount_date_to') or None,
                    discount=reward_discount_value,
                    temporary_discount=temporary_reward_discount_value,
                    coupon_discount=loyalty_info.get('coupon_discount', 0),
                    reward_product_qty=loyalty_info.get('product_reward_qty', 0),
                    required_points=loyalty_info.get('product_reward_required_points', 0),
                    note_promotion=loyalty_info.get('note_promotion', ''),
                    coupon=coupon if coupon==3 else None,
                    loyalty_card=loyalty_card,
                )

            ######## Actualizar/crear programa de cupones ########
            coupon_loyalty_program = False
            coupon_program_id = loyalty_info.get('coupon_program_id')
            if coupon_program_id:
                coupon_loyalty_program = self.env['loyalty.program'].sudo().browse(coupon_program_id)

            ## Variables para la recompensa de descuento
            coupon_discount_reward_id = loyalty_info.get('coupon_discount_reward_id')
            reward_discount_value = float(loyalty_info.get('discount') or 0)
            temporary_reward_discount_value = float(loyalty_info.get('temporary_discount') or 0)
            coupon_reward_discount_value = float(loyalty_info.get('coupon_discount') or 0)
            coupon_discount_date_from = loyalty_info.get('coupon_discount_date_from') or None
            coupon_discount_date_to = loyalty_info.get('coupon_discount_date_to') or None

            ### Verificar si existen programas archivados de tipo Cupones, y desarchivar si coupon es igual a 1 o 2
            if not coupon_loyalty_program and coupon in (1,2):
                coupon_loyalty_program=self.env['loyalty.program'].restore_last_archived_program(product_id=product_id, program_type='coupons')
                if coupon_loyalty_program:
                    # Preprocesar programa de Tipo Cupones desarchivado
                    archived_discount_reward_info = coupon_loyalty_program.archived_discount_reward_info
                    coupon_discount_reward_id = coupon_loyalty_program.preprocess_unarchived_program(product_id=product_id, reward_info=archived_discount_reward_info)

            ### Actualizar programa de cupones ###
            if coupon_loyalty_program:
                ## Actualizar programa de cupones para la opcion 0: archivar programa, regla y recompensas asociadas ##
                if coupon == 0 or coupon == 3:
                    ## Guardar informacion de las recompensas antes de archivar ##
                    # Guardar ID y descuento para recompensa de descuento normal
                    if coupon_discount_reward_id:
                        archived_discount_reward_info = coupon_loyalty_program.obtain_char_id_and_values(reward_id=coupon_discount_reward_id, reward_type="discount")
                        coupon_loyalty_program.sudo().write({
                            'archived_discount_reward_info': archived_discount_reward_info
                        })

                    # Archivar programa de cupones, y las reglas y recompensas
                    coupon_loyalty_program.archive_program()

                    # Actualizar descuento nuevamente para el modal
                    product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                ## Actualizar programa de cupones para la opcion 1: por unidad ##
                if coupon == 1:
                    # Actualizar programa
                    coupon_loyalty_program.sudo().write({
                        'name': f"CUPON-POR-UNIDAD-{product_name}",
                        'mandatory_promotion': True,
                        'is_selection_promotion': False,
                        'note_promotion': '',
                        'applies_by_boxes': False,
                        'is_auto_apply': True,
                        #'date_from': coupon_date_from,
                        #'date_to': coupon_date_to,
                    })

                    # Desarchivar recompensa de descuento en caso de existir, y si el descuento es mayor a cero
                    if not coupon_discount_reward_id and coupon_reward_discount_value > 0:
                        archived_discount_reward_info = coupon_loyalty_program.archived_discount_reward_info
                        coupon_discount_reward_id = coupon_loyalty_program.restore_archived_reward_by_id(reward_info=archived_discount_reward_info, reward_type='discount', product_id=product_id).id

                    # Actualizar la recompensa de descuento
                    if coupon_discount_reward_id:
                        coupon_discount_reward = self.env['loyalty.reward'].sudo().browse(coupon_discount_reward_id)
                        if coupon_discount_reward:
                            if coupon_reward_discount_value > 0:
                                coupon_discount_reward.sudo().write({
                                    'discount': coupon_reward_discount_value,
                                    'required_points': 1,
                                    'is_main': False,
                                    'date_from': coupon_discount_date_from,
                                    'date_to': coupon_discount_date_to,
                                    'is_temporary': False,
                                })
                                product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                            else:
                                archived_discount_reward_info = coupon_loyalty_program.obtain_char_id_and_values(reward_id=coupon_discount_reward_id, reward_type="discount")
                                coupon_loyalty_program.sudo().write({
                                    'archived_discount_reward_info': archived_discount_reward_info
                                })
                                coupon_discount_reward.sudo().write({
                                    'active': False,
                                })
                                product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                    else:
                        if coupon_reward_discount_value > 0:
                            self.env['loyalty.reward'].sudo().create({
                                'program_id': coupon_loyalty_program.id,
                                'reward_type': 'discount',
                                'discount': coupon_reward_discount_value,
                                'discount_applicability': 'specific',
                                'required_points': 1,
                                'discount_product_ids': [(6, 0, [product_id])],
                                'date_from': coupon_discount_date_from,
                                'date_to': coupon_discount_date_to,
                                'is_temporary': False,
                            })
                            product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                    # Actualizar cupones
                    Coupon = self.env['loyalty.card'].sudo()
                    coupons = Coupon.search([('program_id', '=', coupon_loyalty_program.id)])
                    coupons.write({
                        'expiration_date': coupon_discount_date_to,
                    })
                    # Crear cupones en caso de existir menos de 500
                    actual_coupons_quantity = len(coupons)
                    total_coupons = 500
                    coupons_to_create = total_coupons - actual_coupons_quantity
                    if coupons_to_create > 0:
                        # Crear cupones
                        wiz = self.env['loyalty.generate.wizard'].sudo().create({
                            'program_id': coupon_loyalty_program.id,
                            'coupon_qty': coupons_to_create,
                            'display_name': f"CUPON-POR-UNIDAD-{product_name}",
                            'create_date': coupon_discount_date_from,
                            'valid_until': coupon_discount_date_to,
                        })
                        wiz.generate_coupons()

                    # Actualizar descuento nuevamente para el modal
                    product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                ## Actualizar programa de cupones para la opcion 2: por caja ##
                if coupon == 2:
                    # Actualizar programa
                    coupon_loyalty_program.sudo().write({
                        'name': f"CUPON-POR-CAJA-{product_name}",
                        'mandatory_promotion': True,
                        'is_selection_promotion': False,
                        'note_promotion': '',
                        'applies_by_boxes': True,
                        'is_auto_apply': True,
                        #'date_from': coupon_date_from,
                        #'date_to': coupon_date_to,
                    })

                    # Desarchivar recompensa de descuento en caso de existir, y si el descuento es mayor a cero
                    if not coupon_discount_reward_id and coupon_reward_discount_value > 0:
                        archived_discount_reward_info = coupon_loyalty_program.archived_discount_reward_info
                        coupon_discount_reward_id = coupon_loyalty_program.restore_archived_reward_by_id(reward_info=archived_discount_reward_info, reward_type='discount', product_id=product_id).id

                    # Actualizar la recompensa de descuento
                    if coupon_discount_reward_id:
                        coupon_discount_reward = self.env['loyalty.reward'].sudo().browse(coupon_discount_reward_id)
                        if coupon_discount_reward:
                            if coupon_reward_discount_value > 0:
                                coupon_discount_reward.sudo().write({
                                    'discount': coupon_reward_discount_value,
                                    'required_points': 1,
                                    'is_main': False,
                                    'date_from': coupon_discount_date_from,
                                    'date_to': coupon_discount_date_to,
                                    'is_temporary': False,
                                })
                                product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                            else:
                                archived_discount_reward_info = coupon_loyalty_program.obtain_char_id_and_values(reward_id=coupon_discount_reward_id, reward_type="discount")
                                coupon_loyalty_program.sudo().write({
                                    'archived_discount_reward_info': archived_discount_reward_info
                                })
                                coupon_discount_reward.sudo().write({
                                    'active': False,
                                })
                                product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                    else:
                        if coupon_reward_discount_value > 0:
                            self.env['loyalty.reward'].sudo().create({
                                'program_id': coupon_loyalty_program.id,
                                'reward_type': 'discount',
                                'discount': coupon_reward_discount_value,
                                'discount_applicability': 'specific',
                                'required_points': 1,
                                'discount_product_ids': [(6, 0, [product_id])],
                                'date_from': coupon_discount_date_from,
                                'date_to': coupon_discount_date_to,
                                'is_temporary': False,
                            })
                            product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})
                    # Actualizar cupones
                    Coupon = self.env['loyalty.card'].sudo()
                    coupons = Coupon.search([('program_id', '=', coupon_loyalty_program.id)])
                    coupons.write({
                        'expiration_date': coupon_discount_date_to,
                    })
                    # Crear cupones en caso de existir menos de 500
                    actual_coupons_quantity = len(coupons)
                    total_coupons = 500
                    coupons_to_create = total_coupons - actual_coupons_quantity
                    if coupons_to_create > 0:
                        # Crear cupones
                        wiz = self.env['loyalty.generate.wizard'].sudo().create({
                            'program_id': coupon_loyalty_program.id,
                            'coupon_qty': coupons_to_create,
                            'display_name': f"CUPON-POR-CAJA-{product_name}",
                            'create_date': coupon_discount_date_from,
                            'valid_until': coupon_discount_date_to,
                        })
                        wiz.generate_coupons()
                    # Actualizar descuento nuevamente para el modal
                    product.sudo().write({'discount': reward_discount_value if (reward_discount_value > 0) else temporary_reward_discount_value})

            ### Crear programa de cupones ###
            else:
                if coupon != 0 and coupon != 3:
                    self.create_loyalty_program(
                        product_id=product.id,
                        product_name=product_info.get('name'),
                        units_per_box=units_per_box,
                        mandatory_promotion=loyalty_info.get('coupon_mandatory_promotion'),
                        discount_date_from=loyalty_info.get('discount_date_from') or None,
                        discount_date_to=loyalty_info.get('discount_date_to') or None,
                        product_date_from=loyalty_info.get('product_date_from') or None,
                        product_date_to=loyalty_info.get('product_date_to') or None,
                        coupon_discount_date_from=loyalty_info.get('coupon_discount_date_from') or None,
                        coupon_discount_date_to=loyalty_info.get('coupon_discount_date_to') or None,
                        discount=reward_discount_value,
                        temporary_discount=temporary_reward_discount_value,
                        coupon_discount=loyalty_info.get('coupon_discount', 0),
                        reward_product_qty=loyalty_info.get('product_reward_qty', 0),
                        required_points=loyalty_info.get('product_reward_required_points', 0),
                        note_promotion=loyalty_info.get('note_promotion'),
                        coupon=coupon,
                        loyalty_card=False,
                    )
            return Response(
                json.dumps({'status': 'success',
                            'message': 'Información guardada correctamente'}),
                status=200,
                content_type='application/json'
            )
        except Exception:
           return Response(
               json.dumps({'error': 'Error al guardar la información'}),
               status=500,
               content_type='application/json'
           )