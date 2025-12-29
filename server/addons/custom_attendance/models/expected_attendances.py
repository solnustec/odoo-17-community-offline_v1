import logging

from odoo import models, fields, api
from datetime import datetime, timedelta

class ExpectedLocations(models.Model):
    _name = 'hr.expected.locations'
    _description = 'Expected Locations for Attendance'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Location Name", required=True)
    reference = fields.Char(string="Reference", required=True)
    last_attendance = fields.Datetime(string="Last Attendance Received")
    status = fields.Selection([
        ('ok', 'Recibida'),
        ('missing', 'Faltante')],
        string='Estado de marcaciones',
        default='missing')

    def check_missing_attendance(self):

        try:
            configurable_period = int(self.env['ir.config_parameter'].sudo().get_param(
                'custom_attendance.configurable_period', 0))

            # Calcular fecha límite (ahora - período configurado)
            limit_date = datetime.now() - timedelta(days=configurable_period)

            locations_to_check = self.search([
                '|',
                ('last_attendance', '=', False),
                ('last_attendance', '<', limit_date)
            ])

            for location in locations_to_check:
                location.status = 'missing'
                self.env['mail.activity'].create({
                    'res_model_id': self.env['ir.model']._get_id('hr.expected.locations'),
                    'res_id': location.id,
                    'activity_type_id': self.env.ref('mail.mail_activity_data_warning').id,
                    'summary': f'Falta marcación en {location.name} (más de {configurable_period} días)',
                    'user_id': self.env.user.id,
                })

        except Exception as e:
            print(f"Error en check_missing_attendance: {str(e)}")