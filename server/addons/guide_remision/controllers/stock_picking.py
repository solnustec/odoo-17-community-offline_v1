# -- coding: utf-8 --
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http, _
from odoo.http import request
import json
from odoo.fields import Datetime

from odoo import api, http, models, tools, SUPERUSER_ID
from odoo.http import request, Response, ROUTING_KEYS, Stream
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class StockTransfers(http.Controller):

    @http.route('/api/transferstobranch_sync/<int:id>', type='http', auth='public',
                methods=['PUT'], csrf=False)
    def transfers_to_branch_sync(self, id, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            llave = data.get("llave", "")

            record = request.env['json.pos.transfers.edits'].sudo().browse(id)

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



    @http.route('/api/tranferstobranch/<int:external_id>', type='http',
                auth='public', methods=['GET'], csrf=False)
    def branch_to_branch_transfer(self, external_id, **kwargs):
        try:
            records = request.env['json.pos.transfers.edits'].sudo().search(
                [("sent", "=", False), ("external_id", "=", external_id)])
            json_list = []
            for record in records:
                data = {
                    "id": record.id,
                    "json_data": json.loads(record.json_data or "{}"),
                    "point_of_sale_series": record.point_of_sale_series,
                    "sent": record.sent,
                    "db_key": record.db_key,
                    "sync_date": record.sync_date.isoformat() if record.sync_date else None
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

    # =====================================================================
    # APIs para json.pos.transfers (Transferencias Hechas)
    # =====================================================================

    @http.route('/api/transfers_done/<int:external_id>', type='http',
                auth='public', methods=['GET'], csrf=False)
    def get_transfer_edits(self, external_id, **kwargs):
        """
        Obtiene los borradores de transferencias no sincronizados por external_id
        """
        try:
            records = request.env['json.pos.transfers'].sudo().search(
                [("sent", "=", False), ("external_id", "=", external_id)])
            json_list = []
            for record in records:
                data = {
                    "id": record.id,
                    # "json_data": json.loads(record.json_data or "{}"),
                    # "point_of_sale_series": record.point_of_sale_series,
                    # "stock_picking_id": record.stock_picking_id.id if record.stock_picking_id else None,
                    "sent": record.sent,
                    "db_key": record.db_key,
                    # "employee": record.employee,
                    # "origin": record.origin,
                    # "destin": record.destin,
                    "sync_date": record.sync_date.isoformat() if record.sync_date else None,
                    # "create_date": record.create_date.isoformat() if record.create_date else None
                }
                try:
                    json_list.append(data)
                except json.JSONDecodeError:
                    json_list.append(
                        {"error": "JSON inválido", "record_id": record.id})

            return Response(json.dumps({
                "data": json_list
            }, indent=4), content_type='application/json')

        except Exception as e:
            return json.dumps({
                "error": "Ocurrió un error al consultar los borradores.",
                "details": str(e)
            }, indent=4)

    @http.route('/api/transfers_done_sync/<string:db_key>', type='http',
                auth='public', methods=['PUT'], csrf=False)
    def sync_transfer_edit_by_key(self, db_key, **kwargs):
        """
        Actualiza un borrador de transferencia buscando por db_key directamente
        """
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            new_key = data.get("llave", db_key)

            # Buscar por db_key en lugar de por id
            record = request.env['json.pos.transfers'].sudo().search(
                [("db_key", "=", db_key)], limit=1)

            if not record:
                return Response(json.dumps({
                    "error": f"No se encontró un registro con db_key: {db_key}"
                }, indent=4), content_type='application/json', status=404)

            # Actualizar el registro
            record.write({
                'sent': True,
                'sync_date': Datetime.now(),
                'db_key': new_key
            })

            return Response(json.dumps({
                "success": True,
                "message": "El borrador se sincronizó correctamente.",
                "updated_record_id": record.id,
                "db_key": new_key
            }, indent=4), content_type='application/json')

        except Exception as e:
            return Response(json.dumps({
                "error": "Ocurrió un error al sincronizar el borrador.",
                "details": str(e)
            }, indent=4), content_type='application/json', status=500)