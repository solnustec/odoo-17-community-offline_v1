import json
from odoo import http
from odoo.http import request, Response


class JsonPosCloseSessionController(http.Controller):

    @http.route('/api/json_pos_close_sessions', type='http', auth='public', methods=['GET'], csrf=False)
    def get_json_pos_close_sessions(self, **kwargs):
        """
        API GET para obtener los registros de json.pos.close.session,
        filtrando por id_point_of_sale si se proporciona.
        """
        try:
            # Obtener parámetro desde la URL
            point_of_sale_id = kwargs.get('id_point_of_sale')

            # Construir dominio de búsqueda
            domain = [('sent', '=', False)]
            if point_of_sale_id:
                domain.append(('id_point_of_sale', '=', point_of_sale_id))

            sessions = request.env['json.pos.close.session'].sudo().search(domain)
            result = []

            for session in sessions:
                try:
                    json_data = json.loads(session.json_data.replace("'", "\"")) if session.json_data else None
                except json.JSONDecodeError:
                    json_data = session.json_data

                result.append({
                    'id': session.id,
                    'json_data': json_data,
                })

            return Response(json.dumps({'status': 'success', 'data': result}), content_type='application/json',
                            status=200)

        except Exception as e:
            return Response(json.dumps({'status': 'error', 'message': str(e)}), content_type='application/json',
                            status=500)