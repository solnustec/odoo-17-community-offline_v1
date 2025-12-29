import json
from datetime import datetime, date

import requests

from odoo import models, api, fields


class LoyaltySync(models.Model):
    _name = 'loyalty.sync'
    _description = 'Loyalty Sync'
    """
        {
            "ID": "123456",
            "promCant": 10,
            "baseCant": 5,
            "descEsp": 2.5,
            "desde": "2024-06-01",
            "hasta": "2024-12-31",
            "acumulableS": 1
        },
        """
    name = fields.Char(tracking=True, )
    product_id = fields.Many2one('product.product', string='Product')
    product_id_old = fields.Char(string='Old Product ID',
                                 help='Old product ID for reference')
    promo_cant = fields.Integer(string='Promotion Quantity')
    base_cant = fields.Integer(string='Base Quantity')
    desc_esp = fields.Float(string='Discount Amount')
    date_from = fields.Date(string='Start Date')

    date_to = fields.Date(string='End Date')

    acumulable = fields.Boolean(string='Promocion Accumulable')
    obligatory_promotion = fields.Boolean(string='Mandatory Promotion')
    note = fields.Text(string='Note')
    coupon = fields.Integer(string='Coupon')
    coupon_date_from = fields.Date(string='Start Date Cupon')
    coupon_discount = fields.Float(string='Coupon Discount')
    coupon_date_to = fields.Date(string='End Date Cupon')
    obligatory_coupon = fields.Boolean(string='Mandatory Coupon')
    sync_state = fields.Boolean(string='Sync State')
    sync_date = fields.Datetime(string='Sync Date', )
    active = fields.Boolean(string='Active', default=True)
    user_id = fields.Many2one('res.users', string='User',
                              default=lambda self: self.env.user, tracking=True, readonly=True)

    @api.model
    def sync_loyalty_programs(self, data):
        product_info = data[0]

        product_id = self.env['product.product'].search(
            [('id', '=', product_info['product_id'])])
        loyalty = self.env['loyalty.sync'].create({
            'product_id': product_info.get('product_id'),
            'name': product_id.name,
            'product_id_old': product_id.id_database_old,
            'promo_cant': product_info.get('promo_cant', 0),
            'base_cant': product_info.get('base_cant', 0),
            'desc_esp': product_info.get('desc_esp', 0.0),
            'date_from': product_info.get('date_from') or None,
            'date_to': product_info.get('date_to') or None,
            'acumulable': bool(product_info.get('acumulable', False)),
            'coupon_date_from': product_info.get('coupon_date_from') or None,
            'coupon_date_to': product_info.get('coupon_date_to') or None,
            'coupon_discount': product_info.get('coupon_discount', 0.0),
            'obligatory_coupon': bool(product_info.get('obligatory_coupon', 0)),
            'obligatory_promotion': bool(product_info.get('obligatory_promotion', 0)),
            'coupon': product_info.get('coupon', 0),
            # Assuming this is always true
            'note': product_info.get('program_note', ''),
        })
        return loyalty

    @api.model
    def cron_sync_loyalty_programs(self):
        """
        Cron job to sync loyalty programs.
        This method should be scheduled to run periodically.
        """
        loyaties = self.env['loyalty.sync'].search(
            [('active', '=', True), ('sync_state', '=', False)])
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'vf_promotions_url')
        headers = {
            "Content-Type": "application/json",
            'Authorization': 'Bearer ' + 'cuxiloja2025__'
        }
        if loyaties:
            for loyalty in loyaties:
                data = {
                    "ID": loyalty.product_id_old,
                    "promCant": loyalty.promo_cant,
                    "baseCant": loyalty.base_cant,
                    "descEsp": loyalty.desc_esp,
                    "pdesde": loyalty.date_from.isoformat() if isinstance(
                        loyalty.date_from,
                        (date, datetime)) else loyalty.date_from,
                    "phasta": loyalty.date_to.isoformat() if isinstance(
                        loyalty.date_to,
                        (date, datetime)) else loyalty.date_to,
                    "acumulable": loyalty.acumulable,
                    "obligatory": loyalty.obligatory_promotion,
                    "note": loyalty.note,
                    "lcupon": loyalty.coupon,
                    "porcdesc1": loyalty.coupon_discount,
                }
                try:
                    res = requests.put(base_url, json=[data], headers=headers,
                                       timeout=5)
                    res.raise_for_status()
                    if res.status_code == 201:
                        loyalty.write({
                            'sync_state': True,
                            'active': False,
                            'sync_date': fields.Datetime.now(),
                        })
                except requests.exceptions.HTTPError as e:
                    print("Error HTTP:", e, res.json())
                except requests.exceptions.RequestException as e:
                    print("Error en la solicitud:", e)
