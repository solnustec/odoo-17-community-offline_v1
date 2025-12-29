# -*- coding: utf-8 -*-
from datetime import datetime
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tools.translate import _
from odoo import models, fields, api
from odoo.exceptions import UserError
import base64

class HrApplicant(models.Model):
    _inherit = 'hr.applicant'


    def create_employee_from_applicant(self):
        """ Create an employee from applicant """
        self.ensure_one()
        self._check_interviewer_access()

        if not self.partner_id:
            if not self.partner_name:
                raise UserError(_('Please provide an applicant name.'))
            self.partner_id = self.env['res.partner'].create({
                'is_company': False,
                'name': self.partner_name,
                'email': self.email_from,
            })

        action = self.env['ir.actions.act_window']._for_xml_id('hr.open_view_employee_list')
        (employee_camps,employee_dict,applicant) = self._get_employee_create_vals()
        employee = self.env['hr.employee'].create(employee_camps)
        relationship = self.env['type_of_relationship.custom_employe'].search(
            [('name', '=', employee_dict.get('relationship'))], limit=1
        ) or self.env['type_of_relationship.custom_employe'].create({
            'name': employee_dict.get('relationship'),
        })
        self.env['references.custom_employe'].create(self.create_in_model_rerence(employee_dict,employee.id,relationship))
        self.env['additional_preparation.custom_employe'].create(self.create_in_model_additional_preparation(employee_dict,employee.id))
        action['res_id'] = employee.id
        applicant.write({'emp_id': employee.id})
        return action

    def _get_employee_create_vals(self):
        self.ensure_one()
        address_id = self.partner_id.address_get(['contact'])['contact']
        address_sudo = self.env['res.partner'].sudo().browse(address_id)
        applicant_id = self.get_applicants_from_partner(self.partner_id.id)
        applicant = applicant_id.generic_field_value_ids
        generic_field_values = self.get_generic_field_values(applicant)
        name = generic_field_values.get('name', 'Sin Nombre')
        last_name = generic_field_values.get('last_name', 'Sin Apellido')
        full_name = f"{name} {last_name}".strip().title()
        nacionality = self.env['res.country'].sudo().search([('name', '=', generic_field_values.get('nationality'))])
        state = self.env['res.country.state'].sudo().search([('name', '=', generic_field_values.get('province'))])
        curriculum = generic_field_values.get('curriculum')
        if curriculum:
            file_content = base64.b64decode(curriculum.datas)
            curriculum = base64.b64encode(file_content).decode('utf-8')
        photography = generic_field_values.get('photography')
        if photography:
            file_content2 = base64.b64decode(photography.datas)
            photography = base64.b64encode(file_content2).decode('utf-8')
        return {
            'name': full_name,
            'birthday': generic_field_values.get('birth_date'),
            'country_id': nacionality.id,
            'type_identification': generic_field_values.get('id_type'),
            'identification_id': generic_field_values.get('identification'),
            'private_state_id': state.id,
            'canton': generic_field_values.get('canton'),
            'private_city': generic_field_values.get('city'),
            'private_street': generic_field_values.get('address'),
            'phone_landline': generic_field_values.get('partner_phone'),
            'private_phone': generic_field_values.get('partner_mobile'),
            'private_email': generic_field_values.get('email'),
            'marital': generic_field_values.get('civil_status'),
            'drivers_license_type': generic_field_values.get('drivers_license_type'),
            'own_vehicle_availability': generic_field_values.get('own_vehicle_availability'),
            'gender': generic_field_values.get('gender'),
            'image_1920': photography or False,
            'availability_to_travel': generic_field_values.get('availability_to_travel'),
            'availability_date_to_start': generic_field_values.get('availability_date_to_start'),
            'url_facebook': generic_field_values.get('url_facebook'),
            'url_linkedin': generic_field_values.get('url_linkedin'),
            'name_of_institution': generic_field_values.get('secondary_education_name_of_institution')
                                   or generic_field_values.get('higher_education_name_of_the_institution')
                                   or generic_field_values.get('postgraduates_masters_doctorates_name_of_the_institution'),
            'graduation_year': generic_field_values.get('secondary_education_graduation_year')
                                   or generic_field_values.get('higher_education_graduation_year')
                                   or generic_field_values.get('postgraduates_masters_doctorates_graduation_year'),
            'education_degree_earned': generic_field_values.get('secondary_education_degree_earned')
                                   or generic_field_values.get('postgraduates_masters_doctorates_degree_obtained')
                                   or generic_field_values.get('degree'),
            'level_of_instruction': generic_field_values.get('level_of_instruction'),
            'no_senescyt_registration': generic_field_values.get('higher_education_no_senescyt_registration')
                                   or generic_field_values.get('postgraduates_masters_doctorates_no_senescyt_registration'),
            'availability_to_change_residence': generic_field_values.get('availability_to_change_residence'),
            'availability_for_rotating_shifts': generic_field_values.get('availability_for_rotating_shifts'),
            'availability_to_work_weekends_and_holidays': generic_field_values.get('availability_to_work_weekends_and_holidays'),
            'curriculum_vitae': curriculum or False,
        },generic_field_values,applicant_id

    def get_applicants_from_partner(self, partner_id):
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            raise ValidationError("No se encuentra el contacto")

        applicant = self.env['hr.applicant'].sudo().search([('partner_id', '=', partner_id)], limit=1)
        return applicant

    def get_generic_field_values(self, field_values):
        field_dict = {}
        for field_value in field_values:
            field_id = field_value.field_id.code_field
            if field_value.value_char:
                field_dict[field_id] = field_value.value_char
            elif field_value.value_text:
                field_dict[field_id] = field_value.value_text
            elif field_value.value_integer:
                field_dict[field_id] = field_value.value_integer
            elif field_value.value_float:
                field_dict[field_id] = field_value.value_float
            elif field_value.value_boolean:
                field_dict[field_id] = field_value.value_boolean
            elif field_value.value_date:
                field_dict[field_id] = field_value.value_date
            elif field_value.value_datetime:
                field_dict[field_id] = field_value.value_datetime
            elif field_value.value_selection:
                field_dict[field_id] = field_value.value_selection
            elif field_value.file_attachment_ids:
                field_dict[field_id] = field_value.file_attachment_ids
        return field_dict

    def create_in_model_rerence(self,dict,id,relationship):
        return{
            'name': dict.get('name_reference'),
            'place_of_work': dict.get('place_of_work_or_economic_activity'),
            'relationship': relationship.id,
            'email': dict.get('email_reference'),
            'employee_references_id': id,
        }
    def create_in_model_additional_preparation(self,dict,id):
        return{
            'name': dict.get('certifications_and_courses_name_of_course_certification'),
            'institution': dict.get('certifications_and_courses_institution'),
            'completion_date': dict.get('certifications_and_courses_completion_date'),
            'duration': dict.get('certifications_and_courses_duration'),
            'internal_course': dict.get('certifications_and_courses_internal_course'),
            'employee_additional_preparation_id': id,
        }
