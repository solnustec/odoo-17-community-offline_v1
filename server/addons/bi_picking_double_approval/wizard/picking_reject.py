# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api, _


class PickingRejectWizard(models.TransientModel):
    _name = "picking.reject.wizard"
    _description = "Picking Reject Wizard"

    picking_id = fields.Many2one('stock.picking', string='Picking')
    reject_reason = fields.Char("Reject Reason")

    def button_reject(self):
        if self.picking_id:
            self.picking_id.reject_reason = self.reject_reason
            self.picking_id.state = 'rejected'
