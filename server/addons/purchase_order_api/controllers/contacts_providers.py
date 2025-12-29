from odoo import http

from odoo.http import request, Response, _logger

import json


class ContactProviderAPIController(http.Controller):
    @http.route('/api/contact/create_or_update_provider', type='json', auth='public', methods=['POST'], csrf=False)
    def create_or_update_contact(self, **post):
        try:

            data = json.loads(request.httprequest.data.decode('utf-8'))
            contacts = data.get('data')

            if not isinstance(contacts, list) or not contacts:
                return {'status': 'error', 'message': 'A non-empty list of contacts is required.'}

            vat_numbers = [c.get('vat_number') for c in contacts if c.get('vat_number')]
            existing_partners = {
                p.vat: p for p in request.env['res.partner'].sudo().search([('vat', 'in', vat_numbers)])
            }

            response_list = []
            for contact in contacts:
                vat_number = contact.get('vat_number')
                name = contact.get('name')
                email = contact.get('email')

                if not vat_number:
                    response_list.append({'status': 'error', 'message': 'VAT number is required.', 'data': contact})
                    continue

                if not name or not email:
                    response_list.append(
                        {'status': 'error', 'message': 'Name and email are required.', 'data': contact})
                    continue

                vat_length = len(vat_number)
                vat_identifier = 5 if vat_length == 10 else 4 if vat_length == 13 else 0

                partner_data = {
                    'name': name,
                    'email': email,
                    'phone': contact.get('phone'),
                    'street': contact.get('street'),
                    'city': contact.get('city'),
                    'vat': vat_number,
                    'l10n_latam_identification_type_id': vat_identifier,
                    'id_database_old_provider': contact.get('id_database_old_provider'),
                }

                partner = existing_partners.get(vat_number)
                if partner:
                    partner.sudo().write({'id_database_old_provider': partner_data['id_database_old_provider']})
                    response_list.append({
                        'status': 'success',
                        'message': f'Contact with VAT {vat_number} updated successfully.',
                        'contact_id': partner.id,
                        'vat_number': vat_number
                    })
                else:
                    new_partner = request.env['res.partner'].sudo().create(partner_data)
                    response_list.append({
                        'status': 'success',
                        'message': 'Contact created successfully.',
                        'contact_id': new_partner.id,
                        'vat_number': vat_number
                    })

            return {
                'status': 'success',
                'results': response_list,
                'count': len(response_list),
                'failed': len([r for r in response_list if r['status'] == 'error'])
            }

        except json.JSONDecodeError:
            return {'status': 'error', 'message': 'Invalid JSON data.'}
        except Exception as e:
            return {'status': 'error', 'message': f'Internal server error: {str(e)}'}

        # {
        #     "data": [
        #         {
        #             "name": "John Doe",
        #             "email": "john.doe@example.com",
        #             "phone": "+1234567890",
        #             "street": "123 Main St",
        #             "city": "New York",
        #             "vat_number": "1234567890",
        #             "id_database_old_provider": "PROV001"
        #         },
        #         {
        #             "name": "Jane Smith",
        #             "email": "jane.smith@example.com",
        #             "phone": "+0987654321",
        #             "street": "456 Elm St",
        #             "city": "Los Angeles",
        #             "vat_number": "0987654321098",
        #             "id_database_old_provider": "PROV002"
        #         }
        #     ]
        # }