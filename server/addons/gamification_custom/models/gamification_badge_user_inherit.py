# -*- coding: utf-8 -*-
from odoo import api, fields, models

class GamificationBadgeUser(models.Model):
    _inherit = 'gamification.badge.user'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        compute='_compute_employee_id',
        store=True,
        index=True,
        help='Empleado vinculado al usuario que recibió la insignia.'
    )

    @api.depends('user_id')
    def _compute_employee_id(self):
        if not self:
            return

        to_fill = self.filtered(lambda r: not r.employee_id and r.user_id)
        if not to_fill:
            return

        users = to_fill.mapped('user_id')
        Employee = self.env['hr.employee'].sudo()
        emps = Employee.search([('user_id', 'in', users.ids)])

        by_user = {}
        for e in emps:
            by_user.setdefault(e.user_id.id, []).append(e)

        for rec in to_fill:
            candidates = by_user.get(rec.user_id.id) or []
            if candidates:
                same_company = [
                    e for e in candidates
                    if e.company_id and rec.user_id and e.company_id == rec.user_id.company_id
                ]
                rec.employee_id = (same_company[0] if same_company else candidates[0]).id
            else:
                rec.employee_id = False

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        missing = recs.filtered(lambda r: not r.employee_id and r.user_id)
        if missing:
            missing._compute_employee_id()
        return recs