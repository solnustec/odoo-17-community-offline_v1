# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from datetime import datetime
from collections import defaultdict
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    state = fields.Selection(selection_add=[('waiting_approval', 'Esperando aprobación'), ('rejected', 'Rechazado')])
    approval_required = fields.Boolean(compute='_compute_approval_required')
    reject_reason = fields.Char("Razón de Rechazo")

    # Approved information fields
    is_approved = fields.Boolean('Esta Aprobado?', default=False)
    approved_by_id = fields.Many2one('res.users', 'Aprobado por')
    approved_date = fields.Datetime('Fecha de aprobación')

    @api.depends('picking_type_id')
    def _compute_approval_required(self):
        config = self.env['ir.config_parameter'].sudo()
        delivery_approval = config.get_param('bi_picking_double_approval.delivery_approval', default='False') == 'True'
        receipt_approval = config.get_param('bi_picking_double_approval.receipt_approval', default='False') == 'True'
        internal_transfer_approval = config.get_param('bi_picking_double_approval.internal_transfer_approval',
                                                      default='False') == 'True'

        for record in self:
            record.approval_required = (
                    (record.picking_type_id.code == 'outgoing' and delivery_approval) or
                    (record.picking_type_id.code == 'incoming' and receipt_approval) or
                    (record.picking_type_id.code == 'internal' and internal_transfer_approval)
            )

    @api.depends('move_type', 'move_ids.state', 'move_ids.picking_id', 'approval_required', 'is_approved')
    def _compute_state(self):
        super(StockPicking, self)._compute_state()
        for picking in self:
            if (not picking.is_approved and picking.approval_required and
                    picking.state not in ('draft', 'done', 'cancel')):
                picking.state = 'waiting_approval'

    @api.depends('picking_type_id', 'partner_id')
    def _compute_location_id(self):
        for picking in self:
            if picking.state not in ['draft','waiting_approval'] or picking.return_id:
                continue
            picking = picking.with_company(picking.company_id)
            if picking.picking_type_id:
                if picking.picking_type_id.default_location_src_id:
                    location_id = picking.picking_type_id.default_location_src_id.id
                elif picking.partner_id:
                    location_id = picking.partner_id.property_stock_supplier.id
                else:
                    _customerloc, location_id = self.env['stock.warehouse']._get_partner_locations()

                if picking.picking_type_id.default_location_dest_id:
                    location_dest_id = picking.picking_type_id.default_location_dest_id.id
                elif picking.partner_id:
                    location_dest_id = picking.partner_id.property_stock_customer.id
                else:
                    location_dest_id, _supplierloc = self.env['stock.warehouse']._get_partner_locations()

                picking.location_id = location_id
                picking.location_dest_id = location_dest_id
    

    def action_approve(self):
        self.write({
            'is_approved': True,
            'approved_by_id': self.env.user.id,
            'approved_date': datetime.now(),
        })
        self._compute_state()

    def action_reject(self):
        return {
            'name': _('Picking Reject'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'picking.reject.wizard',
            'target': 'new',
            'context': {'default_picking_id': self.id}
        }

    def button_validate(self):
        for picking in self:
            if picking.approval_required and not picking.is_approved:
                raise UserError(_("Este traslado requiere aprobación antes de ser validado."))
        return super(StockPicking, self).button_validate()

    def _create_backorder(self):
        backorder = super(StockPicking, self)._create_backorder()
        backorder.approval_required = self.approval_required
        backorder.is_approved = False
        backorder.approved_by_id = False
        backorder.approved_date = False
        backorder._compute_approval_required()
        backorder._compute_state()
        return backorder




