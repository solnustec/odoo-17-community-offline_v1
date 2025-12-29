from odoo import _, models, fields, api
from odoo.exceptions import UserError

class GamificationGoal(models.Model):
    _inherit = 'gamification.goal'

    x_user_department_id = fields.Many2one(
        'hr.department',
        string='Departamento',
        compute='_compute_user_department',
        store=True,
        readonly=True,
    )

    x_user_department_parent_id = fields.Many2one(
        'hr.department',
        string='Zona',
        related='x_user_department_id.parent_id',
        store=True,
        readonly=True,
    )

    x_challenge_line_id = fields.Many2one(
        'gamification.challenge.line',
        string="Línea del desafío",
        compute='_compute_ch_line',
        store=True,
        readonly=True,
    )

    x_bonification = fields.Text(
        string="Bonificación",
        related="x_challenge_line_id.x_bonification",
        store=True,
        readonly=True,
    )

    x_bonification_amount = fields.Float(
        string="Bonificación monetaria",
        related="x_challenge_line_id.x_bonification_amount",
        store=True,
        readonly=True,
    )

    x_bonification_status = fields.Boolean(
        string="Bonificación entregada",
        default=False,
        help="Marcar si ya se entregó la bonificación para este usuario/meta."
    )

    x_completion_pct = fields.Float(
        string='Avance (%)',
        compute='_compute_x_completion_pct',
        store=True,
    )

    x_gauge_max_pct = fields.Float(
        string='Gauge Max (%)',
        default=100.0,
        readonly=True,
    )

    x_gauge_suffix = fields.Char(
        string='Unidad',
        default='%',
        readonly=True,
    )

    x_reached_date = fields.Date(
        string='Fecha de cumplimiento',
        readonly=True,
        copy=False,
        index=True,
        help="Fecha en la que la meta llegó a estado 'Alcanzada'."
    )

    x_payroll_discount_id = fields.Many2one(
        'hr.payroll.discounts',
        string='Abono/Descuento generado',
        readonly=True,
        copy=False
    )

    @api.depends('user_id', 'user_id.employee_id', 'user_id.employee_id.department_id')
    def _compute_user_department(self):
        Employee = self.env['hr.employee'].sudo()
        for r in self:
            dept = False
            user = r.user_id
            if user:
                if 'employee_id' in user._fields and user.employee_id:
                    dept = user.employee_id.department_id
                else:
                    emp = Employee.search([('user_id', '=', user.id), ('active', '=', True)], limit=1)
                    dept = emp.department_id if emp else False
            r.x_user_department_id = dept

    @api.depends('challenge_id', 'definition_id')
    def _compute_ch_line(self):
        for goal in self:
            line = self.env['gamification.challenge.line'].search([
                ('challenge_id', '=', goal.challenge_id.id),
                ('definition_id', '=', goal.definition_id.id),
            ], limit=1)
            goal.x_challenge_line_id = line.id

    @api.depends('completeness')
    def _compute_x_completion_pct(self):
        for rec in self:
            rec.x_completion_pct = rec.completeness or 0.0

    def _gpb__employee_from_goal(self):
        self.ensure_one()
        if not self.user_id:
            return self.env['hr.employee']
        return self.env['hr.employee'].sudo().with_context(active_test=False).search(
            [('user_id', '=', self.user_id.id)], limit=1
        )

    def _gpb__discount_vals(self, employee, category):
        reached_date = self.x_reached_date or fields.Date.context_today(self)
        goal_label = self.definition_id.name or self.display_name or ''
        challenge_label = self.challenge_id.name or self.challenge_id.id or ''

        description = _(
            "Bonificación por meta alcanzada dentro de un desafío.\n"
            "Meta: %(goal)s\n"
            "Desafío: %(challenge)s"
        ) % {
            'goal': goal_label,
            'challenge': challenge_label,
        }
        return {
            'employee_id': employee.id,
            'category_id': category.id,
            'date': reached_date,
            'amount': self.x_bonification_amount or 0.0,
            'is_percentage': False,
            'description': description,
        }

    def _gpb_sync_discount(self):
        Discount = self.env['hr.payroll.discounts']
        try:
            category = self.env.ref('gamification_custom.discount_cat_gam_bonus')
        except ValueError:
            raise UserError(_("Falta la categoría de Abonos: 'Bonificación por Metas'."))

        for goal in self:
            if goal.state != 'reached' or (goal.x_bonification_amount or 0.0) <= 0:
                continue

            employee = goal._gpb__employee_from_goal()
            if not employee:
                continue

            vals = goal._gpb__discount_vals(employee, category)

            if goal.x_payroll_discount_id:
                goal.x_payroll_discount_id.write(vals)
            else:
                discount = Discount.create(vals)
                goal.x_payroll_discount_id = discount.id

    def _gpb_cleanup_discount_if_unreached(self):
        for goal in self:
            if goal.state != 'reached' and goal.x_payroll_discount_id:
                goal.x_payroll_discount_id.unlink()
                goal.x_payroll_discount_id = False

    @api.model_create_multi
    def create(self, vals_list):
        goals = super().create(vals_list)
        for goal, vals in zip(goals, vals_list):
            if vals.get('state') == 'reached' and not goal.x_reached_date:
                goal.x_reached_date = fields.Date.context_today(goal)
        return goals

    def write(self, vals):
        prev_state = {r.id: r.state for r in self} if 'state' in vals else {}
        res = super().write(vals)
        touched_reached_date = False

        if 'state' in vals and not self.env.context.get('gpb_skip_sync'):
            reached_ids, cleared_ids = [], []
            for rec in self:
                old = prev_state.get(rec.id)
                new = rec.state
                if old != 'reached' and new == 'reached' and not rec.x_reached_date:
                    reached_ids.append(rec.id)
                elif old == 'reached' and new != 'reached' and rec.x_reached_date:
                    cleared_ids.append(rec.id)
            if reached_ids:
                self.browse(reached_ids).with_context(gpb_skip_sync=True).write({
                    'x_reached_date': fields.Date.context_today(self)
                })
                touched_reached_date = True
            if cleared_ids:
                self.browse(cleared_ids).with_context(gpb_skip_sync=True).write({
                    'x_reached_date': False
                })
                touched_reached_date = True

        if not self.env.context.get('gpb_skip_sync'):
            if ({'state', 'x_bonification_amount', 'x_reached_date'} & set(vals.keys())) or touched_reached_date:
                self._gpb_cleanup_discount_if_unreached()
                self._gpb_sync_discount()
        return res

    def unlink(self):
        """Archivar metas antes de eliminarlas."""
        History = self.env["gamification.goal.history"]
        for goal in self:
            # Solo archivar si tiene datos relevantes
            if goal.user_id and (goal.state in ["reached", "failed"] or goal.completeness > 0):
                # Verificar si ya existe en historial
                existing = History.search([
                    ("original_goal_id", "=", goal.id),
                ], limit=1)
                if not existing:
                    History.create_from_goal(goal)
        return super().unlink()