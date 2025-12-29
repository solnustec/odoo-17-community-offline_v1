from odoo import http
from odoo.http import request
import logging
import json
from odoo.http import Response
from werkzeug.utils import redirect
import base64

_logger = logging.getLogger(__name__)


class WebsiteSaveApplicant(http.Controller):

    def _build_response(self, status, message, data=None, status_code=200):
        response = {
            'status': status,
            'message': message
        }
        if data:
            response.update(data)
        return Response(
            json.dumps(response),
            status=status_code,
            headers=[('Content-Type', 'application/json')]
        )
    @http.route('/website/form/hr/applicant/hr/applicant', type='http', auth='public', methods=['POST'],
                website=True, csrf=False)
    def save_applicant(self, **post):

        job_id = post.get('job_id')

        if not job_id:
            return self._build_response(
                status='error',
                message='job_id inválido',
                status_code=400
            )

        job_id = int(job_id)

        partner_name = None
        partner_last_name = None
        partner_phone = None
        partner_mobile = None
        identification = None
        email_from = None
        linkedin_profile = None
        description = None
        salary_proposed = None
        salary_expected = None

        custom_fields = request.env['custom.field'].search([
            ('model_id.model', '=', 'hr.applicant'),
            ('active', '=', True)
        ])
        for field in custom_fields:
            field_name = field.code_field
            value = post.get(field.code_field)
            if field_name in ['partner_name', 'name', 'nombre', 'nombre completo']:
                partner_name = value
            if field_name in ['last_name', 'apellido']:
                partner_last_name = value
            elif field_name in ['partner_phone', 'phone', 'telefono', 'teléfono']:
                partner_phone = value
            elif field_name in ['partner_mobile', 'mobile', 'movil', 'móvil']:
                partner_mobile = value
            elif field_name in ['identification', 'identificación']:
                identification = value
            elif field_name in ['email_from', 'email', 'correo', 'correo electrónico']:
                email_from = value
            elif field_name in ['linkedin_profile', 'linkedin', 'Url Perfil Linkedin']:
                linkedin_profile = value
            elif field_name in ['description', 'descripción', 'descrição']:
                description = value
            elif field_name in ['salary_proposed', 'salario propuesto', 'salário proposto']:
                salary_proposed = value
            elif field_name in ['salary_expected', 'salario esperado', 'salário esperado']:
                salary_expected = value

        if not partner_name or not partner_last_name:
            return self._build_response(
                status='error',
                message='Campos obligatorios faltantes',
                data={
                    'missing_fields': {
                        'Nombres': not partner_name,
                        'Apellidos': not partner_last_name
                    }
                },
                status_code=400
            )


        applicant_data = {
            'partner_name': f"{partner_name} {partner_last_name}".strip().title(),
            'name': f"{partner_name} {partner_last_name}".strip().title(),
            'job_id': job_id,
        }

        if partner_phone:
            applicant_data['partner_phone'] = partner_phone

        if partner_mobile:
            applicant_data['partner_mobile'] = partner_mobile

        if identification:
            applicant_data['identification'] = identification

        if email_from:
            applicant_data['email_from'] = email_from

        if linkedin_profile:
            applicant_data['linkedin_profile'] = linkedin_profile

        if description:
            applicant_data['description'] = description

        if salary_proposed:
            applicant_data['salary_proposed'] = salary_proposed

        if salary_expected:
            applicant_data['salary_expected'] = salary_expected


        try:
            applicant = request.env['hr.applicant'].sudo().create(applicant_data)
            template = request.env.ref('hr_recruitment.email_template_data_applicant_congratulations')
            if template:
                template.sudo().send_mail(applicant.id, force_send=True)
        except Exception as e:
            return self._build_response(
                status='error',
                message='Error al crear al candidato',
                data={'details': str(e)},
                status_code=500
            )

        res_id = applicant.id

        for field in custom_fields:
            field_name = field.code_field
            value = post.get(field_name)
            if value:

                field_value_obj = {
                    'field_id': field.id,
                    'res_model': request.env['ir.model'].search([('model', '=', 'hr.applicant')], limit=1).id,
                    'res_id': res_id,
                }
                if field.field_type == 'char':
                    field_value_obj['value_char'] = value
                elif field.field_type == 'text':
                    field_value_obj['value_text'] = value
                elif field.field_type == 'integer':
                    field_value_obj['value_integer'] = int(value)
                elif field.field_type == 'float':
                    field_value_obj['value_float'] = float(value)
                elif field.field_type == 'boolean':
                    field_value_obj['value_boolean'] = value == 'on'
                elif field.field_type == 'date':
                    field_value_obj['value_date'] = value
                elif field.field_type == 'datetime':
                    field_value_obj['value_datetime'] = value
                elif field.field_type == 'selection':
                    field_value_obj['value_selection'] = value
                elif field.field_type == 'file':
                    file_data = request.httprequest.files.get(field_name)
                    if file_data:
                        file_name = file_data.filename
                        file_content = file_data.read()
                        file_attachment = request.env['ir.attachment'].sudo().create({
                            'name': file_name,
                            'type': 'binary',
                            'datas': base64.b64encode(file_content).decode('utf-8') if file_content else False,
                            'mimetype': file_data.content_type,
                            'res_model': 'hr.applicant',
                            'res_id': 0,
                        })
                        field_value_obj['file_attachment_ids'] = [(6, 0, [file_attachment.id])]

                try:
                    request.env['custom.generic_field'].sudo().create(field_value_obj)
                except Exception as e:
                    _logger.error("Error al crear campo personalizado: %s", e)
                    return self._build_response(
                        status='error',
                        message='Error al crear uno de los campos',
                        data={'details': str(e)},
                        status_code=500
                    )

        return self._build_response(
            status='success',
            message='Guardado exitoso',
            data={
                'redirect_url': f'/job-thank-you?applicant_id={res_id}',
                'applicant_id': res_id
            }
        )


class WebsiteThankYou(http.Controller):

    @http.route('/job-thank-you', type='http', auth='public', website=True)
    def thank_you(self, applicant_id=None, **kwargs):
        applicant = None
        if applicant_id:
            applicant = request.env['hr.applicant'].sudo().browse(int(applicant_id))
            if not applicant.exists():
                applicant = None
        _logger.info(applicant)
        version = {
            'server_version': '13.0',
        }
        return request.render('custom.job_thank_you_template', {
            'applicant': applicant,
            'version': version
        })


class CustomFieldManagerController(http.Controller):
    @http.route('/check_cedula', type='json', auth='public', methods=['POST'])
    def check_cedula(self, **kwargs):
        request_bytes = request.httprequest.data
        request_json_str = request_bytes.decode('utf-8')
        request_data = json.loads(request_json_str)
        cedula = request_data.get('identification')
        if not cedula:
            return json.dumps({'exists': False, 'message': 'No cedula provided'})

        cr = request.env.cr

        query = """
                SELECT id
                FROM hr_applicant
                WHERE identification = %s
                LIMIT 1
            """
        cr.execute(query, (cedula,))

        result = cr.fetchone()


        # print("revisar aca al postuante??", result)
        #
        # applicant = request.env['hr.applicant'].sudo().with_context(active_test=False).search([('identification', '=', cedula)], limit=1)
        if result:
            return json.dumps({'exists': True, 'message': 'Cedula already exists'})
        return json.dumps({'exists': False, 'message': 'Cedula does not exist'})

