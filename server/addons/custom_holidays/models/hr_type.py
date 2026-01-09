# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    exclude_weekends = fields.Boolean(
        string='Excluir fines de semana',
        default=False,
        help=(
            'Si está activado, los días se calcularán excluyendo los fines de semana'
        ),
    )

    # Group validation fields
    first_validator_group_id = fields.Many2one(
        'res.groups',
        string="Grupo Creador/Primera Validacion",
        help="Usuarios de este grupo pueden crear solicitudes y auto-aprobar la primera validacion"
    )

    second_validator_group_id = fields.Many2one(
        'res.groups',
        string="Grupo Segunda Validacion",
        help="Usuarios de este grupo pueden realizar la segunda validacion final"
    )

    @api.constrains('leave_validation_type', 'first_validator_group_id', 'second_validator_group_id')
    def _check_validation_groups(self):
        for record in self:
            if record.leave_validation_type == 'both':
                if record.first_validator_group_id and not record.second_validator_group_id:
                    raise ValidationError(_(
                        "Si configura el Grupo Creador/Primera Validacion, "
                        "tambien debe configurar el Grupo Segunda Validacion."
                    ))
                if record.second_validator_group_id and not record.first_validator_group_id:
                    raise ValidationError(_(
                        "Si configura el Grupo Segunda Validacion, "
                        "tambien debe configurar el Grupo Creador/Primera Validacion."
                    ))
