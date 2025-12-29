

from odoo import models, fields, api
from odoo.exceptions import ValidationError

DAY_SELECT_VALUES = [str(i) for i in range(1, 29)] + ['last']
DAY_SELECT_SELECTION_NO_LAST = tuple(zip(DAY_SELECT_VALUES, (str(i) for i in range(1, 29))))

def _get_selection_days(self):
    return DAY_SELECT_SELECTION_NO_LAST + (("last", ("Último día")),)
class HrLeaveAccrualPlan(models.Model):
    _inherit = 'hr.leave.accrual.plan'

    @api.constrains('is_plan_general')
    def _check_unique_is_plan_general(self):
        for record in self:
            if record.is_plan_general:
                other_general_plans = self.env['hr.leave.accrual.plan'].search([
                    ('is_plan_general', '=', True),
                    ('id', '!=', record.id),
                ])
                if other_general_plans:
                    raise ValidationError(
                        "Solo puede haber un plan de acumulación con 'Es plan general' activo. "
                        "Desactive el plan general existente antes de activar este."
                    )


    is_plan_general = fields.Boolean(string='Es plan general', default=False)
    day_plan_general = fields.Selection(
        _get_selection_days,
        string='Día del mes',
        help='Selecciona el día del mes para la acumulación.'
    )
    month_plan_general = fields.Selection(
        [
            ('jan', 'Enero'), ('feb', 'Febrero'), ('mar', 'Marzo'), ('apr', 'Abril'),
            ('may', 'Mayo'), ('jun', 'Junio'), ('jul', 'Julio'), ('aug', 'Agosto'),
            ('sep', 'Septiembre'), ('oct', 'Octubre'), ('nov', 'Noviembre'), ('dec', 'Diciembre')
        ],
        string='Mes',
        help='Selecciona el mes para la acumulación.',
        default="jan"
    )

    @api.onchange('day_plan_general', 'month_plan_general')
    def _prepare_leave_accrual_plan(self):
        for record in self:
            if record.day_plan_general and record.month_plan_general:
                for level in record.level_ids:
                    level.yearly_day = record.day_plan_general
                    level.yearly_month = record.month_plan_general
