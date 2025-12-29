

from odoo import models, fields, api

class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    exclude_weekends = fields.Boolean(
        string='Excluir fines de semana',
        default=False,
        help=(
            'Si está activado, los días se calcularán excluyendo los fines de semana'
        ),
    )