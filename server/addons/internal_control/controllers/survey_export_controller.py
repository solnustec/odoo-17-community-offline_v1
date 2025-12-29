# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class SurveyExportController(http.Controller):
    """Extended controller for survey metrics export with observations"""
    
    @http.route('/survey/get_export_data', auth="user", type='json')
    def action_get_survey_export_data(self, **kw):
        """
        Extended method to fetch survey metrics data with observations support
        """

        fields = kw['fields']
        model = kw['model']
        observations = kw.get('observations', '')
        Model = request.env[model]
        field_names = [f['name'] for f in fields]
        columns_headers = [val['label'].strip() for val in fields]

        # Get records based on filters
        domain = [('id', 'in', kw['res_ids'])] if kw['res_ids'] else kw['domain']
        groupby = kw['grouped_by']
        records = Model.browse(kw['res_ids']) if kw['res_ids'] else Model.search(domain, offset=0, limit=False, order=False)
        
        # Generate participants summary
        participants_summary = []
        if records:
            # Get unique campaigns from records
            campaigns = records.mapped('campaign_id')
            for campaign in campaigns:
                # Get all assignments for this campaign
                assignments = request.env['in.survey.campaign.assignment'].search([
                    ('campaign_id', '=', campaign.id)
                ])
                
                for assignment in assignments:
                    employee = assignment.employee_id
                    if employee:
                        participant_info = {
                            'name': employee.name,
                            'department': employee.department_id.name if employee.department_id else None,
                            'job': employee.job_id.name if employee.job_id else None,
                            'responded': assignment.user_input_id is not None,
                            'campaign': campaign.name
                        }
                        participants_summary.append(participant_info)
        
        # Save observations to records if provided
        if observations and records:
            records.write({'observations': observations})
        
        if groupby:
            # Handle grouped data - EXACTLY like the original module
            field_names = [f['name'] for f in fields]
            groupby_type = [Model._fields[x.split(':')[0]].type for x in kw['grouped_by']]
            domain = kw['domain']
            groups_data = Model.read_group(domain,
                                           [x if x != '.id' else 'id' for x in field_names], 
                                           groupby, lazy=False)
            group_by = []
            for rec in groups_data:
                ids = Model.search(rec['__domain'])
                list_key = [x for x in rec.keys() if x in field_names and x not in kw['grouped_by']]
                # CRITICAL: Wrap in list like the original
                export_data = [ids.export_data(field_names).get('datas', [])]
                group_tuple = (
                    {'count': rec['__count']}, 
                    rec.get(kw['grouped_by'][0]),
                    export_data,  # This is already a list
                    [(rec[x], field_names.index(x)) for x in list_key]
                )
                group_by.append(group_tuple)
            
            # Use the last export_data like the original
            result = {
                'header': columns_headers, 
                'data': export_data,  # Use the last export_data from the loop
                'type': groupby_type, 
                'other': group_by,
                'observations': observations,
                'participants_summary': participants_summary
            }
            return result
        else:
            # Handle non-grouped data
            export_data = records.export_data(field_names).get('datas', [])

            result = {
                'data': export_data, 
                'header': columns_headers,
                'observations': observations,
                'participants_summary': participants_summary
            }
            return result 