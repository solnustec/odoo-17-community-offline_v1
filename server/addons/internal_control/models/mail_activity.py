# -*- coding: utf-8 -*-
from odoo import models

class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def activity_notify(self, force_send=True, **kwargs):
        # Evitar notificaciones por correo para asignaciones de encuesta
        other_activities = self.filtered(lambda act: act.res_model != 'in.survey.campaign.assignment')
        if other_activities:
            return super(MailActivity, other_activities).activity_notify(force_send=force_send, **kwargs)
        return True

    def action_open_survey_from_activity(self):
        """Abrir encuesta directamente desde la actividad"""
        self.ensure_one()
        if self.res_model == 'in.survey.campaign.assignment':
            assignment = self.env['in.survey.campaign.assignment'].browse(self.res_id)
            if assignment.exists():
                return assignment.action_open_survey()
        return False