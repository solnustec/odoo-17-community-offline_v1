# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    email_that_sender = fields.Many2one('ir.mail_server',string='Servidor de correo saliente')
    enable_email = fields.Boolean(string='Activar envío de correos (Excepciones)', default=False)
    max_hours_for_shift = fields.Integer(string='Número base de horas en Jornada')
    max_hours_for_lactance = fields.Integer(string='Número base de horas en Jornada')
    range_of_tolerance = fields.Float(
        string='Tiempo permitido de tolerancia para marcaciones',
        help='Define un rango en el cual se puede marcar y esta pueda ser reconocida por el sistema como entrada o salida'
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        email_that_sender_id = self.env['ir.config_parameter'].sudo().get_param(
            'employee_shift_scheduling_app.email_that_sender')
        max_hours_for_shift = self.env['ir.config_parameter'].sudo().get_param(
            'employee_shift_scheduling_app.max_hours_for_shift')
        max_hours_for_lactance = self.env['ir.config_parameter'].sudo().get_param(
            'employee_shift_scheduling_app.max_hours_for_lactance')
        enable_email = self.env['ir.config_parameter'].sudo().get_param(
            'employee_shift_scheduling_app.enable_email')
        range_of_tolerance = self.env['ir.config_parameter'].sudo().get_param(
            'employee_shift_scheduling_app.range_of_tolerance')

        res.update(
            email_that_sender=int(
                email_that_sender_id) if email_that_sender_id else False,
            max_hours_for_shift=int(
                max_hours_for_shift) if max_hours_for_shift else False,
            max_hours_for_lactance=int(
                max_hours_for_lactance) if max_hours_for_lactance else False,
            enable_email=enable_email if enable_email else False,
            range_of_tolerance=float(
                range_of_tolerance) if range_of_tolerance else 0.0,
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'employee_shift_scheduling_app.email_that_sender',
            self.email_that_sender.id)
        self.env['ir.config_parameter'].sudo().set_param(
            'employee_shift_scheduling_app.max_hours_for_shift',
            self.max_hours_for_shift)
        self.env['ir.config_parameter'].sudo().set_param(
            'employee_shift_scheduling_app.max_hours_for_lactance',
            self.max_hours_for_lactance)
        self.env['ir.config_parameter'].sudo().set_param(
            'employee_shift_scheduling_app.enable_email',
            self.enable_email)
        self.env['ir.config_parameter'].sudo().set_param(
            'employee_shift_scheduling_app.range_of_tolerance',
            self.range_of_tolerance)

