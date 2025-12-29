from odoo import http
from odoo.http import request
from odoo.addons.survey.controllers.main import Survey

class InSurveySurvey(Survey):
    @http.route(['/survey/start/<string:survey_token>'], type='http', auth='public', website=True, sitemap=False)
    def survey_start(self, survey_token=None, answer_token=None, **post):
        # Captura los parámetros extra
        campaign_id = request.params.get('campaign_id')
        assignment_id = request.params.get('assignment_id')
        if campaign_id or assignment_id:
            ctx = {}
            if campaign_id:
                ctx['default_campaign_id'] = int(campaign_id)
            if assignment_id:
                ctx['default_assignment_id'] = int(assignment_id)
            request.update_context(**ctx)
        return super(InSurveySurvey, self).survey_start(survey_token=survey_token, answer_token=answer_token, **post)

    @http.route(['/survey/retry/<model("survey.survey"):survey>/<string:answer_token>'],
                type='http', auth='public', website=True)
    def survey_retry(self, survey=None, answer_token=None, **post):
        # Buscar la respuesta del usuario por token
        user_input = request.env['survey.user_input'].sudo().search([('token', '=', answer_token)], limit=1)
        if not user_input:
            return request.render("internal_control.survey_already_answered")
        
        # Verificar si ya existe una asignación completada para este usuario y campaña
        assignment = request.env['in.survey.campaign.assignment'].sudo().search([
            ('user_input_id', '=', user_input.id),
            ('state', '=', 'answered')
        ], limit=1)
        
        if assignment:
            # Si ya respondió, mostrar mensaje
            return request.render("internal_control.survey_already_answered", {
                'survey': survey,
                'assignment': assignment
            })
        
        # Si no ha respondido, continuar con el flujo normal
        return request.redirect('/survey/fill/%s/%s' % (survey.id, answer_token))

