import json

from .api_security import validate_api_static_token
from odoo.http import Response, request
from odoo import http


class PartnerController(http.Controller):
    @http.route('/api/store/partner/search', type='http', auth='public',
                cors='*')
    @validate_api_static_token
    def search_partner(self, **kwargs):
        """busca el partne por numero de identificaion r."""
        identification = kwargs.get('identification')
        if not identification:
            return Response(
                json.dumps(
                    {
                        'status': 'error',
                        'message': 'La identificación es requerida',
                        'data': None
                    }
                ),
                status=400,
                content_type='application/json'
            )

        partner = request.env['res.partner'].sudo().search(
            [('l10n_latam_identification_type_id', '!=', False),
             ('vat', '=', identification)], limit=1)
        if not partner:
            return Response(
                json.dumps(
                    {
                        'status': 'success',
                        'message': 'No es encontraron resultados, para la identificación ingresada intente de nuevo',
                        'data': None
                    }
                ),
                status=200,
                content_type='application/json'
            )
        return Response(
            json.dumps({
                'status': 'success',
                'message': 'Información encontrada',
                'data': {
                    'id': partner.id,
                    'name': partner.name,
                    # 'last_names': partner.last_names,
                    'email': partner.email,
                    'mobile': partner.mobile,
                    'street': partner.street,
                    'street2': partner.street2,
                    'city': partner.city,
                    'country_id': partner.country_id.id,
                    'country_name': partner.country_id.name,
                    'l10n_latam_identification_type_id': partner.l10n_latam_identification_type_id.id,
                    'l10n_latam_identification_type_name': partner.l10n_latam_identification_type_id.name,
                    'vat': partner.vat,
                    'state_id': partner.state_id.id,
                }}),
            status=200,
            content_type='application/json'
        )
