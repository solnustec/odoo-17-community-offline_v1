import json
import logging
import re
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class FormioFormData(models.Model):
    _name = 'formio.form.data'

    form_id = fields.Many2one('formio.form', string='Form Submission', ondelete='cascade')
    builder_id = fields.Many2one(related='form_id.builder_id', store=True)
    key = fields.Char(string='Campo')
    value = fields.Char(string='Valor')

class FormioBuilder(models.Model):
    _inherit = 'formio.builder'

    def get_fields_to_include(self):
        self.ensure_one()
        fields_to_include = {}

        def extract_keys_and_labels(components):
            field_types_to_include = ['number', 'radio', 'select']
            for component in components:
                if 'components' in component:
                    extract_keys_and_labels(component['components'])
                elif component.get('type') in field_types_to_include:
                    key = component.get('key')
                    label = component.get('label')
                    if key and label:
                        fields_to_include[key] = label

        if self.schema:
            try:
                schema_data = json.loads(self.schema)
                components = schema_data.get('components', [])
                extract_keys_and_labels(components)
            except json.JSONDecodeError:
                _logger.exception("Failed to decode schema as JSON.")
        return fields_to_include

class FormioForm(models.Model):
    _inherit = 'formio.form'

    @api.model
    def create(self, vals):
        record = super().create(vals)  
        record._process_submission_data()
        return record
    
    def _format_key(self, key):
        key = key.replace('_', ' ')
        key = re.sub(r'(?<!^)(?=[A-Z])', ' ', key)
        key = key.title()
        return key

    def _process_submission_data(self):
        for record in self:
            if record.submission_data:
                fields_to_include = record.builder_id.get_fields_to_include()
                try:
                    data = json.loads(record.submission_data)
                    for key, value in data.items():
                        if key in fields_to_include:
                            label = fields_to_include[key]
                            self.env['formio.form.data'].create({
                                'form_id': record.id,
                                'key': label, 
                                'value': value,
                            })
                except json.JSONDecodeError:
                    _logger.exception("Failed to decode submission_data as JSON.")