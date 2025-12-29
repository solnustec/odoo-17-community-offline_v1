from odoo import http
import requests
import json


class SriController(http.Controller):
    # @http.route('/sri/consultar_guia', type='http', auth="public", methods=['GET'], csrf=False)
    # def consultar_guia(self, **kwargs):
    #     # Obtener la clave de acceso desde los parámetros de la URL
    #     clave_acceso_comprobante = kwargs.get('clave_acceso_comprobante')
    #     picking = request.env['account.move'].sudo().search([('l10n_ec_authorization_number', '=', clave_acceso_comprobante)], limit=1)
    #     print(picking)
    #     breakpoint()
    #     if clave_acceso_comprobante:
    #         print(clave_acceso_comprobante)
    #         response_data = {
    #             'status': 'success',
    #             'message': 'Consulta exitosa'
    #         }
    #     else:
    #         # Si no se recibe la clave de acceso
    #         response_data = {
    #             'status': 'error',
    #             'message': 'Clave de acceso no recibida'
    #         }
    #
    #     # Devolver la respuesta como JSON
    #     return request.make_response(
    #         json.dumps(response_data),
    #         [('Content-Type', 'application/json')]
    #     )

    @http.route('/proxy_invoices', type='http', auth='public', methods=['POST'], csrf=False)
    def proxy_invoices(self, **post):
        try:
            body = json.loads(http.request.httprequest.data)
            identification = body.get('identification')

            if not identification:
                return http.Response(
                    json.dumps({'error': 'Identification is required.'}),
                    status=400,
                    content_type='application/json'
                )

            url = f'http://190.95.219.234:7501/invoices/{identification}'
            headers = {
                'Authorization': 'Bearer cuxiloja2025__',
                'Content-Type': 'application/json',
            }
            response = requests.get(url, headers=headers)

            return http.Response(
                response.text,
                status=response.status_code,
                content_type='application/json'
            )
        except Exception as e:
            return http.Response(
                json.dumps({'error': str(e)}),
                status=500,
                content_type='application/json'
            )
