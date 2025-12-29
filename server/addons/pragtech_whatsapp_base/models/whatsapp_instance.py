import json
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import requests
import logging
_logger = logging.getLogger(__name__)
from requests.structures import CaseInsensitiveDict
from werkzeug.urls import url_join


class WhatsappInstance(models.Model):
    _name = "whatsapp.instance"
    _description = 'Whatsapp Instance'

    def _get_default_sequence(self):
        return self.search([], orden='sequence desc', limit=1).sequence + 1

    name = fields.Char('Name', required=True)
    status = fields.Selection([('enable', 'Enable'), ('disable', 'Disable')], string='Status', default='disable', copy=False)
    provider = fields.Selection([('whatsapp_chat_api', '1msg'), ('meta', 'Meta')], string="Whatsapp Service Provider",
                                default='whatsapp_chat_api')
    whatsapp_endpoint = fields.Char('Whatsapp Endpoint', help="1msg endpoint url with instance id", copy=False)
    whatsapp_token = fields.Char('Whatsapp Token', help="1msg token", copy=False)
    send_whatsapp_through_template = fields.Boolean(string='Send Message Through Template', help='Send Message Through Template Using Respective Provider')
    whatsapp_gupshup_api_key = fields.Char('Gupshup Api Key', copy=False)
    whatsapp_gupshup_app_name = fields.Char('Gupshup App Name', copy=False)
    gupshup_source_number = fields.Char('Gupshup Phone Number', copy=False)
    signed_by_instance = fields.Char(string='Signed By')
    signature = fields.Image(string='Signature')

    default_instance = fields.Boolean('Default Instance', required=True,
                                      help="Only one instance is default instance if whatsapp instance is not selected from users & "
                                           "message is sent from this instance")
    user_ids = fields.One2many('res.users', 'whatsapp_instance_id', string='Connected Users',
                               help="Message is send from this instance when these user is logged in")
    res_company_ids = fields.One2many('res.company', 'whatsapp_instance_id', string='Connected Companies')
    whatsapp_template_ids = fields.One2many('whatsapp.templates', 'whatsapp_instance_id', string='Whatsapp Templates')
    sequence = fields.Char(string="Sequence", readonly=True, required=True, copy=False, default='New')
    #integrating meta and its credential fields
    whatsapp_meta_api_token = fields.Char('Meta Api Token', copy=False)
    whatsapp_meta_webhook_token = fields.Char('Meta Webhook Verify Token', copy=False)
    whatsapp_meta_phone_number_id = fields.Char('Meta Phone Number Id', copy=False)
    meta_whatsapp_business_account_id = fields.Char('Meta WhatsApp Business Account ID', copy=False)

    # For Logger Info adding
    terminal_log_ids = fields.One2many('terminal.log', 'terminal_log_id', string='Logger Info')

    def configure_meta_webhook(self):
        """Configura la instancia Meta cuando se verifica el webhook"""
        self.ensure_one()
        if self.provider != 'meta':
            return False

        # Hacer una llamada a la API de Meta para obtener la información del número
        headers = {
            'Authorization': f'Bearer {self.whatsapp_meta_api_token}',
            'Content-Type': 'application/json'
        }
        phone_number_id = self.whatsapp_meta_phone_number_id
        url = f"https://graph.facebook.com/v12.0/{phone_number_id}"
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                display_phone_number = data.get('display_phone_number')
                if display_phone_number:
                    self.write({
                        'gupshup_source_number': display_phone_number,
                        'whatsapp_endpoint': f"https://graph.facebook.com/v12.0/{phone_number_id}"
                    })
                    return True
        except Exception as e:
            print(f"Error al configurar instancia Meta: {str(e)}")
        
        return False

    def configure_meta_instance(self, display_phone_number, phone_number_id):
        """Configura los datos de la instancia Meta manualmente"""
        self.ensure_one()
        if self.provider == 'meta':
            self.write({
                'gupshup_source_number': display_phone_number,
                'whatsapp_endpoint': f"https://graph.facebook.com/v12.0/{phone_number_id}"
            })
            return True
        return False

    @api.model
    def create(self, vals):
        """Al crear una instancia, asignar número por defecto si es Meta"""
        if vals.get('sequence', 'New') == 'New':
            vals['sequence'] = self.env['ir.sequence'].next_by_code('whatsapp.instance') or 'New'
        
        # Si es una instancia Meta, asignar número por defecto
        if vals.get('provider') == 'meta' and not vals.get('gupshup_source_number'):
            vals['gupshup_source_number'] = '593981612687'
        
        res = super(WhatsappInstance, self).create(vals)
        # Allow provider wise only one default instance is true
        module = self.env['ir.module.module'].sudo().search([('name' , '=', 'pragtech_whatsapp_messenger'), ('state', '=', 'installed')])
        if module:
            Param_set = self.env['ir.config_parameter'].sudo()
            if res.provider == 'meta':
                Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_phone_number", res.whatsapp_meta_phone_number_id)
                Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_meta_token", res.whatsapp_meta_api_token)
                Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_meta_webhook_token", res.whatsapp_meta_webhook_token)
            elif res.provider == 'whatsapp_chat_api':
                Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_endpoint", res.whatsapp_endpoint)
                Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_token", res.whatsapp_token)
        if 'default_instance' in vals and vals.get('provider'):
            if vals.get('default_instance'):
                for whatsapp_instance_id in self.env['whatsapp.instance'].sudo().search([('provider', '=', vals.get('provider'))]):
                    if whatsapp_instance_id.default_instance:
                        raise UserError(_('You already added default instance to another instance for %s provider') % whatsapp_instance_id.provider)
        return res

    def write(self, vals):
        # Allow provider wise only one default instance is true
        module = self.env['ir.module.module'].sudo().search([('name' , '=', 'pragtech_whatsapp_messenger'), ('state', '=', 'installed')])
        if module:
            Param_set = self.env['ir.config_parameter'].sudo()
            if self.provider == 'meta':
                if 'whatsapp_meta_phone_number_id' in vals:
                    Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_phone_number", vals['whatsapp_meta_phone_number_id'])
                if 'whatsapp_meta_api_token' in vals:
                    Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_meta_token", vals['whatsapp_meta_api_token'])
                if 'whatsapp_meta_webhook_token' in vals:
                    Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_meta_webhook_token", vals['whatsapp_meta_webhook_token'])
                if 'status' in vals and vals['status'] != 'disable':
                    Param_set.set_param("pragtech_whatsapp_messenger.use_meta_api", True)
                elif 'status' in vals and vals['status'] == 'disable':
                    Param_set.set_param("pragtech_whatsapp_messenger.use_meta_api", False)
            elif self.provider == 'whatsapp_chat_api':
                if 'whatsapp_endpoint' in vals:
                    Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_endpoint", vals['whatsapp_endpoint'])
                if 'whatsapp_endpoint' in vals:
                    Param_set.set_param("pragtech_whatsapp_messenger.whatsapp_token", vals['whatsapp_token'])
        if 'default_instance' in vals:
            for whatsapp_instance_id in self.env['whatsapp.instance'].sudo().search([('provider', '=', self.provider)]):
                if not vals['default_instance']:
                    vals['default_instance'] = False
                elif whatsapp_instance_id.default_instance:
                    raise UserError(_('You already added default instance to another instance for %s provider') % whatsapp_instance_id.provider)
        return super(WhatsappInstance, self).write(vals)

    def get_whatsapp_instance(self):
        # When sending message from any object get instance based on provider & conditions
        provider_list = ['gupshup', 'whatsapp_chat_api', 'meta']
        for provider in provider_list:
            whatsapp_instance_id = self._get_whatsapp_instance(provider)
            if whatsapp_instance_id:
                return whatsapp_instance_id

        if not self._context.get('skip_error'):
            raise UserError(_('Please select atleast one default instance or add %s user in whatsapp instance in users or companies') % self.env.user.name)

    def _get_whatsapp_instance(self, provider):

        whatsapp_instance_id = self.sudo().search([('user_ids', '=', self.env.user.id), ('provider', '=', provider),
                                                    ('status', '=', 'enable')], limit=1)

        if whatsapp_instance_id:
            return whatsapp_instance_id
        else:
            whatsapp_instance_id = self.sudo().search([('res_company_ids', '=', self.env.user.company_id.id), ('provider', '=', provider),
                                                        ('status', '=', 'enable')], limit=1)
            if whatsapp_instance_id:
                return whatsapp_instance_id
            else:
                return self._get_default_instance(provider)

    def _get_default_instance(self, provider):
        # Get default instance using following condition:
        # 1) In whatsapp instance search for any instance have default instance true & provider is corresponding provide
        # 2) If not getting instance from 1st condition then we check for whatsapp instance which has status enable
        # 3) If 1st & 2nd condition is not satisfied then raise an user error
        whatsapp_instance_id = self.sudo().search([('default_instance', '=', True), ('provider', '=', provider)], limit=1)
        if whatsapp_instance_id:
            return whatsapp_instance_id
        else:
            whatsapp_instance_id = self.sudo().search([('status', '=', 'enable'), ('provider', '=', provider)], limit=1)
            if whatsapp_instance_id:
                return whatsapp_instance_id
            else:
                return False

    def action_test_connection(self):
        # Checks connection if it is successful or not & add specific message
        if self.provider == 'whatsapp_chat_api':
            try:
                response = requests.request('GET', self.whatsapp_endpoint + '/status?token=' + self.whatsapp_token)
            except Exception as e_log:
                _logger.exception(e_log)
                raise UserError(_('Please add proper whatsapp endpoint or whatsapp token'))
            if response.status_code == 200:
                self.status = 'enable'
                if self.sequence == 'New':
                    self.sequence = self.env['ir.sequence'].next_by_code('whatsapp.instance.sequence')
                return self.wizard_message("CONNECTION SUCCESSFUL")
            elif response.status_code == 401:
                return self.wizard_message("Invalid Credentials")
            else:
                raise Warning("CONNECTION UNSUCCESSFUL")
        elif self.provider == 'gupshup':
            try:
                url = "https://api.gupshup.io/sm/api/v1/users/" + self.whatsapp_gupshup_app_name
                headers = {"apikey": self.whatsapp_gupshup_api_key}
                response = requests.get(url, headers=headers)
            except Exception as e_log:
                _logger.exception(e_log)
                raise UserError(_('Please add proper whatsapp endpoint or whatsapp token'))
            if response.status_code == 200:
                self.status = 'enable'
                if self.sequence == 'New':
                    self.sequence = self.env['ir.sequence'].next_by_code('whatsapp.instance.sequence')
                return self.wizard_message("CONNECTION SUCCESSFUL")
            elif response.status_code == 401:
                return self.wizard_message("Invalid Credentials")
            else:
                raise Warning("CONNECTION UNSUCCESSFUL")
        elif self.provider == 'meta':
            try:
                headers = CaseInsensitiveDict()
                headers["Authorization"] = "Bearer " + self.whatsapp_meta_api_token
                headers["Content-Type"] = "application/json"
                meta_test = 'https://graph.facebook.com/v15.0/'
                url = url_join(meta_test, self.whatsapp_meta_phone_number_id)
                response = requests.get(url , headers=headers)
            except Exception as e_log:
                _logger.exception(e_log)
                raise UserError(_('Please add proper whatsapp endpoint or whatsapp token'))
            if response.status_code == 200:
                self.status = 'enable'
                if self.sequence == 'New':
                    self.sequence = self.env['ir.sequence'].next_by_code('whatsapp.instance.sequence')
                return self.wizard_message("CONNECTION SUCCESSFUL")
            elif response.status_code == 401:
                return self.wizard_message("Invalid Credentials")
            else:
                raise Warning("CONNECTION UNSUCCESSFUL")


    def wizard_message(self, message):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Message',
            'res_model': 'test.connection.wizard',
            'view_mode': 'form',
            'view_id': self.env['ir.model.data']._xmlid_to_res_id('pragtech_whatsapp_base.test_connection_wizard_form'),
            'context': {'message': message},
            'target': 'new',
            'nodestroy': True,
        }

    def action_whatsapp_instance_disable(self):
        if self.status == 'enable':
            self.status = 'disable'
        return self.status

    def action_import_templates(self):
        # Select provider & import templates
        if self.provider == 'whatsapp_chat_api':
            self.import_template_from_chat_api()
        elif self.provider == 'gupshup':
            self.import_template_from_gupshup()
        elif self.provider == 'meta':
            self.import_template_from_meta()

    def import_template_from_meta(self):
        # Import templates from meta need business_account_id
        business_account_id = self.meta_whatsapp_business_account_id
        if business_account_id:
            access_token = self.whatsapp_meta_api_token
            url = "https://graph.facebook.com/v15.0/{}/message_templates".format(business_account_id)
            req_headers = CaseInsensitiveDict()
            req_headers["Authorization"] = "Bearer " + access_token
            req_headers["Content-Type"] = "application/json"

            response = requests.get(url, headers=req_headers)
            if response.status_code == 200:
                json_data = response.json()
                data_list = json_data.get("data", [])
                for template in data_list:
                    if template.get('components') and len(template.get('components')) > 1:
                        if template.get('components')[0].get('text') and not template.get('components')[1].get('text'):
                            body_message = template.get('components')[0].get('text')
                        elif template.get('components')[0].get('text') and template.get('components')[1].get('text'):
                            body_message = template.get('components')[0].get('text') + "\n" + \
                                           template.get('components')[1].get('text')
                        elif not template.get('components')[0].get('text') and template.get('components')[1].get(
                                'text'):
                            body_message = template.get('components')[1].get('text')
                    else:
                        body_message = template.get('components')[0].get('text')
                    template_header_type = template.get('components')[0].get('format')
                    if template_header_type == 'DOCUMENT':
                        header = 'media_document'
                    if template_header_type == 'TEXT':
                        header = 'text'
                    if template_header_type == 'IMAGE':
                        header = 'media_image'
                    if template_header_type == None:
                        header = 'text'
                    if template_header_type == 'VIDEO':
                        header = 'media_video'
                    values = {
                        'provider': 'meta',
                        'whatsapp_instance_id': self.id,
                        'name': template.get('name'),
                        'category': template.get('category'),
                        'template_id': template.get('id'),
                        'header': header,
                        'body': body_message,
                        'approval_state': template.get('status'),
                    }
                    if template.get('status') == 'APPROVED':
                        values['state'] = 'post'
                    whatsapp_templates_id = self.env['whatsapp.templates'].sudo().search(
                        [('name', '=', template.get('name')), ('whatsapp_instance_id', '=', self.id)], limit=1)
                    if whatsapp_templates_id:
                        whatsapp_template_update_record = whatsapp_templates_id.write(values)
                        if whatsapp_template_update_record:
                            _logger.info("Whatsapp Template is updated into odoo from meta ----------- " + str(
                                whatsapp_templates_id.id))
                    else:
                        whatsapp_template_id = self.env['whatsapp.templates'].create(values)
                        if whatsapp_template_id:
                            _logger.info("Whatsapp Template is created into odoo from meta----------- " + str(
                                whatsapp_template_id.id))
        else:
            raise ValidationError("Meta WhatsApp Business Account ID")
        return True


    def import_template_from_chat_api(self):
        # Import templates from 1msg
        url = self.whatsapp_endpoint + '/templates?token=' + self.whatsapp_token
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, headers=headers)
        if response.status_code == 200 or response.status_code == 201:
            for template in response.json()['templates']:
                vals = {'namespace': template['namespace'], 'state': 'post', 'name': template['name'], 'provider': 'whatsapp_chat_api'}
                if template['category']:
                    vals['category'] = template['category']
                for components in template['components']:
                    if components.get('type') == 'HEADER' and 'format' in components:
                        if components['format'] == 'IMAGE':
                            vals.update({'header': 'media_image'})
                        elif components['format'] == 'DOCUMENT':
                            vals.update({'header': 'media_document'})
                        elif components['format'] == 'VIDEO':
                            vals.update({'header': 'media_video'})
                    elif components['type'] == 'BODY':
                        vals.update({'body': components['text']})
                vals.update({'approval_state': template['status'], 'whatsapp_instance_id': self.id})
                language_id = self.env['res.lang'].search(
                    ['|', ('code', '=', template['language']), ('iso_code', '=', template['language']), '|', ('active', '=', True), ('active', '=', False)], limit=1)
                if language_id:
                    vals.update({'languages': language_id.id})
                whatsapp_templates_id = self.env['whatsapp.templates'].sudo().search(
                    [('name', '=', template.get('name')), ('languages', '=', language_id.id), ('provider', '=', 'whatsapp_chat_api')], limit=1)
                if whatsapp_templates_id:
                    whatsapp_template_update_record = whatsapp_templates_id.write(vals)
                    self._cr.commit()
                    if whatsapp_template_update_record:
                        _logger.info("Whatsapp Template is updated into odoo ----------- " + str(whatsapp_templates_id.id))
                else:
                    whatsapp_template_id = self.env['whatsapp.templates'].create(vals)
                    if whatsapp_template_id:
                        _logger.info("Whatsapp Template is created into odoo ----------- " + str(whatsapp_template_id.id))

    def import_template_from_gupshup(self):
        # Import templates from gupshup
        api_key = self.whatsapp_gupshup_api_key
        app_name = self.whatsapp_gupshup_app_name
        if not api_key or not app_name:
            raise UserError(_("Please add Gupshup App Name and Gupshup Api Key"))
        headers = {"Content-Type": "application/x-www-form-urlencoded", "apikey": api_key}
        template_url = "https://api.gupshup.io/sm/api/v1/template/list/" + app_name
        templates = requests.get(template_url, headers=headers)
        if templates.status_code == 200:
            for template in templates.json().get('templates'):
                media_type = 'text'
                gupshup_media_type = template['templateType']
                if gupshup_media_type == 'DOCUMENT':
                    media_type = 'media_document'
                elif gupshup_media_type == 'IMAGE':
                    media_type = 'media_image'
                elif gupshup_media_type == 'VIDEO':
                    media_type = 'media_video'
                values = {
                    'provider': 'gupshup',
                    'whatsapp_instance_id': self.id,
                    'header': media_type,
                }
                if template.get('meta'):
                    meta_example = json.loads(template['meta'])
                    if meta_example:
                        if meta_example.get('example'):
                            values['gupshup_sample_message'] = meta_example.get('example')
                if template.get('elementName'):
                    values['name'] = template['elementName']
                if template.get('category'):
                    values['category'] = template['category']
                if template.get('data'):
                    values['body'] = template['data']
                if template.get('id'):
                    values['template_id'] = template['id']
                if template.get('status'):
                    values['approval_state'] = template['status']
                if template.get('data'):
                    values['sample_message'] = template['data']
                if template.get('vertical'):
                    values['gupshup_template_labels'] = template['vertical']
                if template.get('namespace'):
                    values['namespace'] = template['namespace']

                if template.get('status') == 'APPROVED':
                    values['state'] = 'post'
                whatsapp_templates_id = self.env['whatsapp.templates'].sudo().search([('name', '=', template['elementName']), ('whatsapp_instance_id', '=', self.id)], limit=1)
                if whatsapp_templates_id:
                    whatsapp_template_update_record = whatsapp_templates_id.write(values)
                    if whatsapp_template_update_record:
                        _logger.info("Whatsapp Template is updated into odoo from gupshup ----------- " + str(whatsapp_templates_id.id))
                else:
                    whatsapp_template_id = self.env['whatsapp.templates'].create(values)
                    if whatsapp_template_id:
                        _logger.info("Whatsapp Template is created into odoo from gupshup----------- " + str(whatsapp_template_id.id))
        return True

    def action_export_templates(self):
        # Export template if template have signature then open wizard & from wizard add current instance signature else export templates
        whatsapp_template_ids = self.env['whatsapp.templates'].sudo().search(
            [('whatsapp_instance_id', '=', self.id), ('approval_state', 'not in', ['approved', 'APPROVED', 'submitted', 'rejected'])])
        template_signature = False
        for whatsapp_template_id in whatsapp_template_ids:
            if whatsapp_template_id.send_template:
                template_signature = True
        if template_signature:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Message',
                'res_model': 'export.template.wizard',
                'view_mode': 'form',
                'view_id': self.env['ir.model.data']._xmlid_to_res_id('pragtech_whatsapp_base.export_template_wizard_form'),
                'target': 'new',
                'nodestroy': True,
            }
        else:
            for whatsapp_template_id in whatsapp_template_ids:
                self.confirm_export_template(whatsapp_template_id)

    def confirm_export_template(self, template_id):
        # Select provider & export templates
        if self.provider == 'whatsapp_chat_api':
            template_id.action_export_template_to_chat_api()

    def action_create_missing_templates(self):
        return True
