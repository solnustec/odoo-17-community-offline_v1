# -*- coding: utf-8 -*-
import re
from difflib import SequenceMatcher

from odoo import http
from odoo.fields import Datetime
from odoo.http import request, Response
from datetime import datetime
import json


class JsonStorageAPI(http.Controller):
    @http.route('/api/json_storage/create/<int:pos_id>', type='http',
                auth='public', methods=['GET'], csrf=False)
    def get_json_by_pos(self, pos_id, **kwargs):
        try:
            records = request.env['json.storage'].sudo().search([
                ('id_point_of_sale', '=', pos_id),
                ('sent', '=', False),
                ('is_access_key', '=', True)
            ])
            json_list = []
            for record in records:
                try:
                    json_data = json.loads(record.json_data or "[]")

                    # Asegurar que json_data sea una lista
                    if isinstance(json_data, list):
                        # Filtrar solo las facturas donde idcustomer != -1
                        filtered_json_data = []
                        for factura_item in json_data:
                            factura = factura_item.get('factura', {})
                            if factura.get('idcustomer') != -1:
                                filtered_json_data.append(factura_item)
                    else:
                        filtered_json_data = []

                    # Si después del filtro hay al menos una factura válida, la agregamos
                    if filtered_json_data:
                        data = {
                            "id": record.id,
                            "json_data": filtered_json_data,
                            "id_point_of_sale": record.id_point_of_sale,
                            "sent": record.sent
                        }
                        json_list.append(data)

                except json.JSONDecodeError:
                    json_list.append({
                        "error": "JSON inválido",
                        "record_id": record.id
                    })

            return Response(json.dumps({
                "data": json_list
            }, indent=4), content_type='application/json')

        except Exception as e:
            return json.dumps({
                "status": 404,
                "error": "Ocurrió un error al consultar los datos.",
                "details": str(e)
            }, indent=4)

    # Ruta para actualizar json_data
    @http.route('/api/json_storage/<int:id>', type='http', auth='public',
                methods=['PUT'], csrf=False)
    def update_json_data(self, id, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            llave = data.get("llave", "")
            record = request.env['json.storage'].sudo().search([
                ('id', '=', id)
            ], limit=1)

            if not record:
                return json.dumps({
                    "error": f"No se encontró un registro asociado al POS ID {id}."
                }, indent=4)

            # Obtener el cuerpo de la solicitud
            record.write(
                {'sent': True, 'sync_date': Datetime.now(), "db_key": llave})

            return json.dumps({
                "success": True,
                "message": "El campo 'json_data' se actualizó correctamente.",
                "updated_record_id": record.id
            }, indent=4)
        except Exception as e:
            return json.dumps({
                "error": "Ocurrió un error al intentar actualizar el registro.",
                "details": str(e)
            }, indent=4)

    @http.route('/api/json_note_credit/', type='http', auth='public', methods=['GET'], csrf=False)
    def get_json_note_credit(self, **kwargs):
        try:
            id_point_of_sale = kwargs.get('id_point_of_sale')
            domain = [('sent', '=', False)]  # Filtro principal para sent = False

            if id_point_of_sale:
                domain.extend([
                    ('id_point_of_sale', '=', id_point_of_sale),
                ])
            note_credits = http.request.env['json.note.credit'].sudo().search(domain)

            result = []
            for note in note_credits:
                try:
                    json_data_parsed = json.loads(note.json_data) if note.json_data else None
                except json.JSONDecodeError:
                    json_data_parsed = {"error": "Invalid JSON format in json_data"}
                result.append({
                    'json_data': json_data_parsed,
                    'date_invoices': note.create_date.strftime("%Y-%m-%d"),
                    'db_key': note.db_key
                })

            return http.Response(
                json.dumps(result),
                content_type='application/json'
            )

        except Exception as e:
            return http.Response(
                json.dumps({'error': str(e)}),
                status=500,
                content_type='application/json'
            )

    @http.route('/api/update_note_credit/', type='http', auth='public', methods=['POST'],
                csrf=False)
    def update_note_credit(self):
        try:
            # Leer el cuerpo JSON de la solicitud
            request_data = json.loads(http.request.httprequest.data.decode('utf-8') or '{}')
            db_key = request_data.get('db_key')
            sent = request_data.get('sent')

            if not db_key:
                return http.Response(
                    json.dumps({'error': 'db_key is required'}),
                    status=400,
                    content_type='application/json'
                )

            # Buscar el registro por db_key
            note_credit = http.request.env['json.note.credit'].sudo().search(
                [('db_key', '=', db_key)], limit=1)

            if not note_credit:
                return http.Response(
                    json.dumps({'error': 'No record found with provided db_key'}),
                    status=404,
                    content_type='application/json'
                )

            # Preparar valores para actualizar
            update_vals = {}
            if sent is not None:
                # Convertir el valor de sent a booleano si viene como string
                if isinstance(sent, str):
                    sent = sent.lower() == 'true'
                update_vals['sent'] = sent

                # Actualizar sync_date con la fecha y hora actuales si sent se establece a True
                if sent:
                    update_vals['sync_date'] = datetime.now()

            # Actualizar el registro
            note_credit.write(update_vals)

            return http.Response(
                json.dumps({
                    'status': 'success',
                    'message': 'Record updated successfully',
                    'db_key': note_credit.db_key,
                    'sent': note_credit.sent
                }),
                content_type='application/json'
            )

        except json.JSONDecodeError:
            return http.Response(
                json.dumps({'error': 'Invalid JSON format in request body'}),
                status=400,
                content_type='application/json'
            )
        except Exception as e:
            return http.Response(
                json.dumps({'error': str(e)}),
                status=500,
                content_type='application/json'
            )

    # Ruta para obtener los registros de stock regulation
    @http.route('/api/stock_regulation/<int:pos_id>', type='http',
                auth='public',
                methods=['GET'], csrf=False)
    def get_stock_regulation_data(self, pos_id, **kwargs):
        try:
            records = request.env['json.stock.regulation'].sudo().search(
                [("sent", "=", False), ("id_point_of_sale", "=", pos_id)])
            json_list = []
            for record in records:
                data = {
                    "id": record.id,
                    "json_data": json.loads(record.json_data or "{}"),
                    "warehouse_id": record.warehouse_id.external_id or record.warehouse_id.id,
                    "laboratory_id": record.laboratory_id.id,
                    "pos_config_id": record.pos_config_id.id,
                    "sent": record.sent
                }
                try:
                    json_list.append(data)
                except json.JSONDecodeError:
                    json_list.append(
                        {"error": "JSON inválido", "record_id": record.id})

            # Responder con la lista de json_data
            return Response(json.dumps({
                "data": json_list
            }, indent=4), content_type='application/json')

        except Exception as e:
            return json.dumps({
                "error": "Ocurrió un error al consultar los datos.",
                "details": str(e)
            }, indent=4)

    @http.route('/api/stock_regulation/<int:id>', type='http', auth='public',
                methods=['PUT'], csrf=False)
    def send_stock_regulation_mark_sent(self, id, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))

            llave = data.get("llave", "")
            record = request.env['json.stock.regulation'].sudo().search([
                ('id', '=', id)
            ], limit=1)

            if not record:
                return json.dumps({
                    "error": f"No se encontró un registro asociado al ID {id}."
                }, indent=4)

            record.write(
                {'sent': True, 'sync_date': Datetime.now(), "db_key": llave})

            # formatear el nuevo json
            """
            {
               "llave":9012495121411604896,
               "iduser":1249,
               "idbodega":189,
               "l_close":1,
               "l_sync":0,
               "t_init":"20251030113812",
               "t_close":"20251030114119",
               "t_sync":"20251030114119",
               "total":3.03,
               "nota":"",
               "responsable":"USERTEST",
               "idlaboratorio":269,
               "cdet":"{\"fields\": [\"iditem\", \"cantidad\", \"faltante\", \"sobrante\"], \"data\": [[25174, 1.0, 0.0, 1.0], [10751, 2.0, 0.0, 2.0]]}"
            }
            """
            try:
                cdet_obj = json.loads(record.json_data)[0].get("c_det", "{}")
                info = json.loads(record.json_data)[0]
                data = {
                    "llave": record.db_key,
                    "iduser": info.get("iduser"),
                    "idbodega": info.get("idbodega"),
                    "l_close": info.get("l_close"),
                    "l_sync": info.get("l_sync"),
                    "t_init": info.get("t_init"),
                    "t_close": info.get("t_close"),
                    "t_sync": info.get("t_sync"),
                    "total": info.get("total"),
                    "nota": info.get("nota", ""),
                    "responsable": info.get("responsable", ""),
                    "idlaboratorio": info.get("id_laboratorio", ""),
                    "cdet": json.dumps(cdet_obj)
                }
                record.sudo().write(
                    {
                        'json_formated': json.dumps(data),
                        'sent_to_vf': True
                    }
                )
            except Exception as e:
                pass

            return json.dumps({
                "success": True,

                "message": "El campo 'sent' se actualizó correctamente.",
                "updated_record_id": record.id
            }, indent=4)
        except Exception as e:
            return json.dumps({
                "error": "Ocurrio un error al intentar actualizar el registro.",
                "details": str(e)
            }, indent=4)

    @http.route('/api/close_session/<int:id>', type='http', auth='public',
                methods=['PUT'], csrf=False)
    def stock_regulation_mark_sent(self, id, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))

            llave = data.get("llave", "")
            record = request.env['json.pos.close.session'].sudo().search([
                ('id', '=', id)
            ], limit=1)

            if not record:
                return json.dumps({
                    "error": f"No se encontró un registro asociado al ID {id}."
                }, indent=4)

            record.write(
                {'sent': True, 'sync_date': Datetime.now(), "db_key": llave})

            return json.dumps({
                "success": True,

                "message": "El campo 'sent' se actualizó correctamente.",
                "updated_record_id": record.id
            }, indent=4)
        except Exception as e:
            return json.dumps({
                "error": "Ocurrio un error al intentar actualizar el registro.",
                "details": str(e)
            }, indent=4)
