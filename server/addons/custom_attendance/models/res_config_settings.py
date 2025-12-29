from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    grace_period_value = fields.Integer(
        string="Valor del Período de Gracia",
        default=30,
        help="Define la cantidad numérica del período de gracia"
    )

    grace_period_unit = fields.Selection(
        selection=[
            ('days', 'Días'),
            ('weeks', 'Semanas'),
            ('months', 'Meses'),
            ('years', 'Años'),
        ],
        string="Unidad del Período de Gracia",
        default='days',
        required=True,
        help="Unidad de tiempo para el período de gracia"
    )

    grace_limit = fields.Integer(
        string="Límite de Inconsistencias",
        default=5,
        help="Cantidad máxima de inconsistencias permitidas"
    )

    configurable_period = fields.Integer(
        string="Período de Alerta (días)",
        default=1,
        help="Número de días después de los cuales se alerta sobre la falta de marcaciones."
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        grace_period_value = self.env['ir.config_parameter'].sudo().get_param(
            'custom_attendance.grace_period_value')
        grace_period_unit = self.env['ir.config_parameter'].sudo().get_param(
            'custom_attendance.grace_period_unit')
        grace_limit = self.env['ir.config_parameter'].sudo().get_param(
            'custom_attendance.grace_limit')
        configurable_period = self.env['ir.config_parameter'].sudo().get_param(
            'custom_attendance.configurable_period')

        res.update(
            grace_period_value=int(grace_period_value) if grace_period_value else 0,
            grace_period_unit=grace_period_unit if grace_period_unit else 'days',
            grace_limit=int(grace_limit) if grace_limit else 0,
            configurable_period=int(configurable_period) if configurable_period else 0
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'custom_attendance.grace_period_value',
            self.grace_period_value)
        self.env['ir.config_parameter'].sudo().set_param(
            'custom_attendance.grace_period_unit',
            self.grace_period_unit)
        self.env['ir.config_parameter'].sudo().set_param(
            'custom_attendance.grace_limit',
            self.grace_limit)
        self.env['ir.config_parameter'].sudo().set_param(
            'custom_attendance.configurable_period',
            self.configurable_period)
