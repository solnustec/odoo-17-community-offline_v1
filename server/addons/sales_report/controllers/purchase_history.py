import json

from odoo import http
from odoo.http import route, request, Response
from odoo.tools.safe_eval import time


class PurchaseHistory(http.Controller):

    @route(['/api/sales/purchase_history'], type='http', auth='public', cors="*",
           methods=['POST'], csrf=False, )
    # python
    def purchase_history(self, **kw):
        import logging
        _logger = logging.getLogger(__name__)

        def safe_int(val):
            try:
                s = str(val).strip()
                if s == '' or s.lower() == 'none':
                    return None
                # maneja "11672.0" -> 11672
                if '.' in s:
                    return int(float(s))
                return int(s)
            except Exception:
                return None

        BATCH_SIZE = 1000
        result = {
            'status': 201,
            'message': 'Procesamiento completado',
            'successful_records': 0,
            'failed_records': [],
            'data': []
        }
        try:
            purchases = json.loads(request.httprequest.data.decode('utf-8')).get('data', [])
            total = len(purchases)
            _logger.info("purchase_history: recibidos %s registros", total)
            # Buscar el monitor de esta API
            try:
                monitor = request.env['api.monitor'].sudo().search([
                    ('endpoint', '=', 'api/sales/purchase_history')
                ], limit=1)

                if monitor:
                    # Registrar que recibimos una petición
                    monitor.register_request()
            except Exception as e:
                pass
            for start in range(0, total, BATCH_SIZE):
                batch = purchases[start:start + BATCH_SIZE]

                # Recolectar ids únicos normalizados
                product_keys = set()
                partner_keys = set()
                for p in batch:
                    pid = safe_int(p.get('iditem'))
                    sid = safe_int(p.get('supplier'))
                    if pid is not None:
                        product_keys.add(pid)
                    else:
                        # intenta con string si no se pudo parsear
                        s = str(p.get('iditem')).strip()
                        if s:
                            product_keys.add(s)
                    if sid is not None:
                        partner_keys.add(sid)
                    else:
                        s2 = str(p.get('supplier')).strip()
                        if s2:
                            partner_keys.add(s2)

                Product = request.env['product.template'].sudo()
                Partner = request.env['res.partner'].sudo()

                # Buscar intentando con keys tal cual; Odoo aceptará comparar strings/ints según el campo
                products = Product.search(
                    [('id_database_old', 'in', list(product_keys))]) if product_keys else \
                request.env['product.template'].browse()
                # fallback: si no encuentra y había claves numéricas, buscar por string
                if not products and product_keys:
                    products = Product.search(
                        [('id_database_old', 'in', [str(k) for k in product_keys])])

                partners = Partner.search(
                    [('id_database_old_provider', 'in', list(partner_keys))]) if partner_keys else \
                request.env['res.partner'].browse()
                if not partners and partner_keys:
                    partners = Partner.search(
                        [('id_database_old_provider', 'in', [str(k) for k in partner_keys])])

                # Mapas con claves int y str
                prod_map = {}
                for r in products:
                    key_int = safe_int(getattr(r, 'id_database_old', None))
                    prod_map[key_int] = r
                    prod_map[str(getattr(r, 'id_database_old'))] = r

                part_map = {}
                for r in partners:
                    key_int = safe_int(getattr(r, 'id_database_old_provider', None))
                    part_map[key_int] = r
                    part_map[str(getattr(r, 'id_database_old_provider'))] = r

                if partners:
                    partners.sudo().write({'supplier_rank': 1})

                create_vals = []
                for p in batch:
                    pid = safe_int(p.get('iditem'))
                    sid = safe_int(p.get('supplier'))
                    # intenta usar también la representación string
                    prod = prod_map.get(pid) or prod_map.get(str(p.get('iditem')).strip())
                    partner = part_map.get(sid) or part_map.get(str(p.get('supplier')).strip())

                    if not prod or not partner:
                        reason = 'product_missing' if not prod else 'partner_missing'
                        result['failed_records'].append({'record': p, 'reason': reason})
                        _logger.debug(
                            "Registro fallido por %s: pid=%s sid=%s prod_map_keys=%s part_map_keys=%s",
                            reason, pid, sid, list(prod_map.keys()), list(part_map.keys()))
                        continue

                    try:
                        qty = float(p.get('quantity', 0))
                        price = float(p.get('cost', 0))
                        purchase_id = safe_int(p.get('idpurchase')) or -1
                        credit_note = str(p.get('tipo')).strip().lower() == 'credit_note'
                    except Exception:
                        result['failed_records'].append({'record': p, 'reason': 'invalid_numbers'})
                        continue

                    create_vals.append({
                        'date_order': p.get('date'),
                        'partner_id': partner.id,
                        'product_tmpl_id': prod.id,
                        'quantity': qty,
                        'price_unit': price,
                        'credit_note': credit_note,
                        'id_purchase_old': purchase_id,
                    })

                if create_vals:
                    request.env['product.purchase.history'].sudo().create(create_vals)
                    result['successful_records'] += len(create_vals)

            return Response(json.dumps(result), status=201, mimetype='application/json')

        except Exception as e:
            _logger.exception("Error en purchase_history: %s", e)
            return Response(
                json.dumps({'status': 500, 'message': f"Error inesperado: {str(e)}", 'data': [],
                            'failed_records': result.get('failed_records', [])}),
                status=500, mimetype='application/json'
            )

    @route('/api/sales/purchase_history/delete', type='http', auth='public', cors="*",
           methods=['POST'], csrf=False)
    def delete_purchase_history_http(self, **kw):
        """Controller to delete all purchase history records"""
        data = json.loads(request.httprequest.data.decode('utf-8'))
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        try:
            request.env['product.purchase.history'].sudo().search(
                [('date_order', '>=', start_date), ('date_order', '<=', end_date)]).unlink()
            return Response(
                json.dumps(
                    {'status': 200,
                     'message': f'All purchase history records deleted successfully. ',
                     'data': []}),
                status=200, mimetype='application/json'
            )
        except Exception as e:
            return Response(
                json.dumps(
                    {'status': 500, 'message': f'Error deleting purchase history records: {str(e)}',
                     'data': []}),
                status=500, mimetype='application/json'
            )
    # def purchase_history(self, **kw):
    #     """Controller for purchase history"""
    #     try:
    #         # Configuración para el procesamiento por bloques
    #         BATCH_SIZE = 1000  # Número de registros por bloque
    #         result = {
    #             'status': 200,
    #             'message': 'Procesamiento completado',
    #             'successful_records': 0,
    #             'failed_records': [],
    #             'data': []
    #         }
    #
    #         # Obtener los datos enviados
    #         purchases = json.loads(request.httprequest.data.decode('utf-8')).get('data', [])
    #         # Dividir los registros en bloques
    #         total_records = len(purchases)
    #         batches = [purchases[i:i + BATCH_SIZE] for i in range(0, total_records, BATCH_SIZE)]
    #
    #         # Procesar cada bloque
    #         for batch_index, batch in enumerate(batches):
    #             batch_vals = []
    #             # Validar y preparar datos para el bloque
    #             for index, purchase in enumerate(batch):
    #                 # Validar existencia de product_tmpl_id
    #                 product_tmpl = request.env['product.template'].sudo().search(
    #                     [('id_database_old', '=', int(purchase['iditem']))])
    #                 # Validar existencia de partner_id
    #                 partner = request.env['res.partner'].sudo().search(
    #                     [('id_database_old_provider', '=', int(purchase['supplier']))])
    #                 partner.sudo().write({
    #                     'supplier_rank': 1
    #                 })
    #                 vals = {
    #                     'date_order': purchase['date'],
    #                     'partner_id': partner.id,
    #                     'product_tmpl_id': product_tmpl.id,
    #                     'quantity': float(purchase['quantity']),
    #                     'price_unit': float(purchase['cost']),
    #                 }
    #                 batch_vals.append(vals)
    #             # Crear registros en bloque si no hay errores en la validación
    #             if batch_vals:
    #                 # try:
    #                 request.env['product.purchase.history'].sudo().create(batch_vals)
    #                 result['successful_records'] += len(batch_vals)
    #         return Response(
    #             json.dumps(
    #                 {'status': 201, 'message': "Datos insertados correctamente", 'data': []}),
    #             status=201, mimetype='application/json'
    #         )
    #     except Exception as e:
    #         return Response(
    #             json.dumps({'status': 500, 'message': f"Error inesperado: {str(e)}", 'data': []}),
    #             status=500, mimetype='application/json'
    #         )

# purchases = json.loads(request.httprequest.data.decode('utf-8')).get('data')
#         for purchase in purchases:
#             product_template_id = request.env['product.template'].search(
#                 [('id_database_old', '=', int(purchase.get('iditem')))]
#             )
#             print(product_template_id.name)
#             partner = request.env['res.partner'].sudo().search([('name', '=ilike', purchase['supplier'])])
#             request.env['product.purchase.history'].sudo().create({
#                 'date_order': purchase.get('date'),
#                 'partner_id': partner.id,
#                 'product_tmpl_id': product_template_id.id,
#                 'quantity': purchase.get('quantity'),
#                 'price_unit': purchase.get('cost'),
#             })
#             # product_template_id.sudo().write({
#             #     'po_history_line_ids': [(4, line.id)]
#             # })
#
#         return Response(
#             json.dumps({'status': 200, 'message': 'Registro realizado con exito', 'data': []}),
#             status=200, mimetype='application/json'
#         )
