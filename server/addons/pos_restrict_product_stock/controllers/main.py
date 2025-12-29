from odoo import http
from odoo.http import request, Response
import json

class POSNotificationController(http.Controller):

    @http.route('/pos/update_discounts', type='json', auth='public', csrf=False)
    def update_discounts(self):
        session = request.env['pos.session'].sudo().search([], limit=1)
        if session:
            session.notify_pos_discount_update()
            return {"status": "success", "message": "Notificación enviada"}
        return {"status": "error", "message": "No hay sesiones activas"}


    @http.route('/api/partners/old_database', type='http', auth='public', methods=['GET'])
    def get_partners_with_old_id(self, **kwargs):
        try:
            # Buscar contactos con id_database_old = -1
            partners = request.env['res.partner'].sudo().search([('id_database_old', '=', -1)])

            # Preparar los datos para la respuesta
            partner_data = []
            for partner in partners:
                ruc = partner.vat or ''
                if not ruc:  # Verifica si el RUC está vacío
                    continue  # O bien, puedes lanzar un error si prefieres que no se muestre

                partner_data.append({
                    'id': partner.id,
                    'name': partner.name,
                    'email': partner.email or '',
                    'phone': partner.phone or '',
                    'address': partner.street or '',
                    'ruc': ruc,
                    'city': partner.city or '',
                    'id_database_old': partner.id_database_old,
                })

            # Respuesta en formato JSON
            return http.Response(
                json.dumps({
                    'status': 'success',
                    'data': partner_data,
                    'count': len(partner_data)
                }),
                status=200,
                mimetype='application/json'
            )
        except Exception as e:
            # Manejo de errores
            return http.Response(
                json.dumps({
                    'status': 'error',
                    'message': str(e)
                }),
                status=500,
                mimetype='application/json'
            )
