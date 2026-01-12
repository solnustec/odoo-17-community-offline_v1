# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Sadique Kottekkat (<https://www.cybrosys.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
################################################################################
from odoo import models


class PosSession(models.Model):
    """
       This is an Odoo model for Point of Sale (POS) sessions.
       It inherits from the 'pos.session' model and extends its functionality.

       Methods: _loader_params_product_product(): Adds the 'qty_available'
        field to the search parameters for the product loader.
    """
    _inherit = 'pos.session'

    def _loader_params_product_product(self):
        """Function to load the product field to the product params"""
        result = super()._loader_params_product_product()
        result['search_params']['fields'].append('qty_available')
        return result

    def _loader_params_pos_receipt(self):
        """Function that returns the product field pos Receipt"""
        return {
            'search_params': {
                'fields': ['design_receipt', 'name','coupon_receipt_template'],
            },
        }

    def _get_pos_ui_pos_receipt(self, params):
        """Used to Return the params value to the pos Receipts"""
        return self.env['pos.receipt'].search_read(**params['search_params'])

    def _loader_params_res_company(self):
        """Add enable_coupon_printing field to company loader"""
        result = super()._loader_params_res_company()
        result['search_params']['fields'].append('enable_coupon_printing')
        return result

    def _loader_params_coupon_bin_tc(self):
        """Function that returns the params for coupon.bin.tc model"""
        return {
            'search_params': {
                'domain': [('active', '=', True)],
                'fields': ['bin_pattern'],
            },
        }

    def _get_pos_ui_coupon_bin_tc(self, params):
        """Returns the active BIN TC patterns for coupon duplication"""
        return self.env['coupon.bin.tc'].search_read(**params['search_params'])

    def load_pos_data(self):
        """Override to load coupon_bin_tc data into POS"""
        loaded_data = super().load_pos_data()
        loaded_data['coupon_bin_tc'] = self._get_pos_ui_coupon_bin_tc(
            self._loader_params_coupon_bin_tc()
        )
        return loaded_data
