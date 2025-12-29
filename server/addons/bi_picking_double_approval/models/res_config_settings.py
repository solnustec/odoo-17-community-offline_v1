# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    delivery_approval = fields.Boolean(string='Delivery Approval', default=False)
    receipt_approval = fields.Boolean(string='Receipt Approval', default=False)
    internal_transfer_approval = fields.Boolean(string='Internal Transfer Approval', default=False)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res['delivery_approval'] = bool(self.env['ir.config_parameter'].sudo().get_param('bi_picking_double_approval.delivery_approval'))
        res['receipt_approval'] = bool(self.env['ir.config_parameter'].sudo().get_param('bi_picking_double_approval.receipt_approval'))
        res['internal_transfer_approval'] = bool(self.env['ir.config_parameter'].sudo().get_param('bi_picking_double_approval.internal_transfer_approval'))
        return res

    @api.model
    def set_values(self):
        self.env['ir.config_parameter'].sudo().set_param('bi_picking_double_approval.delivery_approval', self.delivery_approval)
        self.env['ir.config_parameter'].sudo().set_param('bi_picking_double_approval.receipt_approval', self.receipt_approval)
        self.env['ir.config_parameter'].sudo().set_param('bi_picking_double_approval.internal_transfer_approval', self.internal_transfer_approval)
        super(ResConfigSettings, self).set_values()

