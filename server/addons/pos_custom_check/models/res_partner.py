# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    has_discount_institution = fields.Boolean(
        string='Tiene Descuento Institucional',
        compute='_compute_institution_flags',
        store=False,
        help='Indica si el cliente tiene instituciones de descuento asociadas.'
    )
    has_credit_institution = fields.Boolean(
        string='Tiene Crédito Institucional',
        compute='_compute_institution_flags',
        store=False,
        help='Indica si el cliente tiene instituciones de crédito asociadas.'
    )

    @api.depends('institution_ids', 'institution_ids.institution_id', 'institution_ids.institution_id.type_credit_institution')
    def _compute_institution_flags(self):
        for partner in self:
            has_discount = False
            has_credit = False
            for inst_client in partner.institution_ids:
                if inst_client.institution_id:
                    if inst_client.institution_id.type_credit_institution == 'discount':
                        has_discount = True
                    elif inst_client.institution_id.type_credit_institution == 'credit':
                        has_credit = True
                if has_discount and has_credit:
                    break
            partner.has_discount_institution = has_discount
            partner.has_credit_institution = has_credit
