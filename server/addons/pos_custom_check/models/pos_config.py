# -*- coding: utf-8 -*-
import json
from odoo import api, fields, models, tools, _
import logging

_logger = logging.getLogger(__name__)



class PosOrder(models.Model):
    _inherit = 'pos.config'

    id_digital_payment = fields.Char(
        string="Código Punto de Venta",
        default=False,
        tracking=True,
        help="Este id será usado para el pago mediante la app De Una"
    )

    def use_coupon_code(self, code, creation_date, partner_id, pricelist_id):
        self.ensure_one()
        # Points desc so that in coupon mode one could use a coupon multiple times
        coupon = self.env['loyalty.card'].sudo().search(
            [('program_id', 'in', self._get_program_ids().ids),
             '|', ('partner_id', 'in', (False, partner_id)), ('program_type', '=', 'gift_card'),
             ('code', '=', code)],
            order='partner_id, points desc', limit=1)

        program = coupon.program_id
        if not coupon or not program.active:
            return {
                'successful': False,
                'payload': {
                    'error_message': _('El cupón "%s" no es válido. Verifique su origen, fecha de caducidad o si se encuentra activo.', code)
                },
            }
        check_date = fields.Date.from_string(creation_date[:11])
        today_date = fields.Date.context_today(self)
        error_message = False
        if (
                (coupon.expiration_date and coupon.expiration_date < check_date)
                or (program.date_to and program.date_to < today_date)
                or (program.limit_usage and program.total_order_count >= program.max_usage)
        ):
            error_message = _("This coupon is expired (%s).", code)
        elif program.date_from and program.date_from > today_date:
            error_message = _("This coupon is not yet valid (%s).", code)
        elif (
                not program.reward_ids or
                not any(r.required_points <= coupon.points for r in program.reward_ids)
        ):
            error_message = _("No reward can be claimed with this coupon.")
        elif program.pricelist_ids and pricelist_id not in program.pricelist_ids.ids:
            error_message = _("This coupon is not available with the current pricelist.")
        elif coupon and program.program_type == 'promo_code':
            error_message = _("This programs requires a code to be applied.")

        if error_message:
            return {
                'successful': False,
                'payload': {
                    'error_message': error_message,
                },
            }

        return {
            'successful': True,
            'payload': {
                'program_id': program.id,
                'coupon_id': coupon.id,
                'coupon_partner_id': coupon.partner_id.id,
                'points': coupon.points,
                'has_source_order': coupon._has_source_order(),
            },
        }

    @api.model
    def ping_connection(self):
        return True