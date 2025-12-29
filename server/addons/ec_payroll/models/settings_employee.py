# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    email_department_change_sender = fields.Many2one('ir.mail_server', string='Servidor de correo saliente')
    enable_email_department_change = fields.Boolean(string='Activar envío de correos (Cambio de Departamento)', default=False)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        email_department_change_sender_id = self.env['ir.config_parameter'].sudo().get_param(
            'ec_payroll.email_department_change_sender')
        enable_email_department_change = self.env['ir.config_parameter'].sudo().get_param(
            'ec_payroll.enable_email_department_change')

        res.update(
            email_department_change_sender=int(
                email_department_change_sender_id) if email_department_change_sender_id else False,
            enable_email_department_change=enable_email_department_change if enable_email_department_change else False,
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'ec_payroll.email_department_change_sender',
            self.email_department_change_sender.id)
        self.env['ir.config_parameter'].sudo().set_param(
            'ec_payroll.enable_email_department_change',
            self.enable_email_department_change)

