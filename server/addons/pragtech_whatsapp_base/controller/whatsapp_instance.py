import json

from odoo import http
from odoo.http import request, Response


class WhatsAppController(http.Controller):

    @http.route('/api/whatsapp_instance', type='http', auth='public',
                methods=['GET'])
    def get_whatsapp_instance(self):
        """ Retorna la instancia de WhatsApp configurada en Odoo """
        whatsapp_instance = request.env[
            'whatsapp.instance'].sudo().get_whatsapp_instance()
        if not whatsapp_instance:
            return Response(
                json.dumps(
                    {"error": "No se encontró una instancia de WhatsApp"}
                ),
                status=404
            )
        return Response(json.dumps(
            {
                "meta_api_token": whatsapp_instance.whatsapp_meta_api_token,
                "meta_phone_number": whatsapp_instance.whatsapp_meta_phone_number_id
            }
        ),
            status=200
        )
