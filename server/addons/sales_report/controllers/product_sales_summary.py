import json

from odoo import http
from odoo.http import route, request, Response
from odoo.tools.safe_eval import time


class ProductSalesSummary(http.Controller):
    @route('/api/sales/product/stock', type='http', auth='public', cors="*",
           methods=['POST'], csrf=False)
    def update_product_stock_summary(self, **kwargs):
        # Obtener los datos de la solicitud
        # Decodificar y validar datos JSON
        data = json.loads(request.httprequest.data.decode('utf-8')).get('data',
                                                                        [])
        # Validar que cada producto tenga los campos necesarios
        valid_data = []
        errors = []
        for product in data:
            id_product = product.get('id_product')
            stock = product.get('stock')
            if not id_product or stock is None:
                errors.append({
                    'error_details': f"Datos inválidos para el producto: id_product={id_product}, stock={stock}"
                })
                continue
            valid_data.append({'id_product': id_product, 'stock': stock})

        # Obtener todos los productos en una sola consulta
        id_products = [p['id_product'] for p in valid_data]
        product_templates = request.env['product.template'].sudo().search([
            ('id_database_old', 'in', id_products)
        ])
        product_map = {pt.id_database_old: pt for pt in product_templates}

        # Preparar actualizaciones y errores
        updates = []
        for product in valid_data:
            id_product = product['id_product']
            stock = product['stock']
            product_template = product_map.get(id_product)
            if not product_template:
                errors.append({
                    'error_details': f"Producto no encontrado para actualizar el stock: {id_product}"
                })
                continue
            updates.append({
                'product_template': product_template,
                'stock': stock
            })

        # Realizar actualizaciones masivas
        if updates:
            product_ids = [u['product_template'].id for u in updates]
            products_to_update = request.env['product.template'].sudo().browse(
                product_ids)
            for update in updates:
                products_to_update.filtered(
                    lambda p: p.id == update['product_template'].id).write({
                    'sales_stock_total': update['stock']
                })

        # Crear registros de error en una sola operación
        if errors:
            request.env['sales.summary.error'].sudo().create(errors)
        return Response(json.dumps({'success': True, 'status': 'success'}),
                        mimetype='application/json', status=201)

    @http.route('/api/sales/delete', type='http', auth='public', cors="*",
                methods=['POST'], csrf=False)
    # delete sales summatry byr date range
    def delete_sales_summary(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        summaries = request.env[
            'product.warehouse.sale.summary'].sudo().search(
            [('is_legacy_system', '=', True), ('date', '>=', start_date), ('date', '<=', end_date)])
        count = len(summaries)
        summaries.sudo().unlink()
        return Response(
            json.dumps({
                'status': 'success',
                'message': f'Se eliminaron {count} resúmenes de ventas.',
            }),
            status=200,
            content_type='application/json'
        )

    @route('/api/sales/history', type='http', auth='public', cors="*",
           methods=['POST'], csrf=False)
    def product_sales_summary(self, **kwargs):
        time_start = time.time()
        # Obtener los datos de la solicitud
        data = json.loads(request.httprequest.data.decode('utf-8')).get('data',
                                                                        [])
        # Paso 1: Agregar datos de entrada por (id_product, warehouse_id, date)
        aggregated_data = {}
        try:
            monitor = request.env['api.monitor'].sudo().search([
                ('endpoint', '=', 'api/sales/history')
            ], limit=1)

            if monitor:
                # Registrar que recibimos una petición
                monitor.register_request()
        except Exception:
            pass
        for product in data:
            id_product = product.get('id_product')
            warehouse_id = product.get('warehouse_id').lstrip('0')
            date = product.get('date')

            # Validar que los campos requeridos estén presentes
            if not all([id_product, warehouse_id, date]):
                request.env['sales.summary.error'].sudo().create({
                    'error_details': f"Entrada inválida: {product}"
                })
                continue  # Saltar entrada inválida

            key = (id_product, warehouse_id, date)
            quantity_sold_in = float(product.get('quantity_sold', 0))
            amount_total_in = float(product.get('amount_total', 0))
            costo_total_in = float(product.get('costo_total', 0))

            # Sumar quantity_sold y amount_total para entradas con la misma clave
            if key in aggregated_data:
                aggregated_data[key]['quantity_sold'] += quantity_sold_in
                aggregated_data[key]['amount_total'] += amount_total_in
                aggregated_data[key]['costo_total'] += costo_total_in

            else:
                aggregated_data[key] = {
                    'id_product': id_product,
                    'warehouse_id': warehouse_id,
                    'date': date,
                    'quantity_sold': quantity_sold_in,
                    'amount_total': amount_total_in,
                    'costo_total': costo_total_in
                }
        # Convertir los datos agregados a una lista
        aggregated_data_list = list(aggregated_data.values())
        # Paso 2: Extraer IDs únicos de productos y almacenes
        product_ids = set(item['id_product'] for item in aggregated_data_list)
        warehouse_ids = set(
            item['warehouse_id'] for item in aggregated_data_list)
        # date = aggregated_data_list[0]['date']
        dates = set(item['date'] for item in aggregated_data_list)

        # Paso 3: Obtener productos en lote
        products = request.env['product.product'].sudo().search_read(
            [('id_database_old', 'in', list(product_ids))],
            ['id', 'name', 'id_database_old']
        )
        # product_map = {p['id_database_old']: p for p in products if
        #                'id_database_old' in p}
        product_map = {p['id_database_old']: p for p in products}

        # Paso 4: Obtener almacenes en lote
        warehouses = request.env['stock.warehouse'].sudo().search_read(
            [('external_id', 'in', list(warehouse_ids))],
            ['id', 'external_id']
        )
        warehouse_map = {w['external_id']: w['id'] for w in warehouses}
        # Paso 5: Obtener resúmenes de ventas existentes en lote
        sales_summaries = request.env[
            'product.warehouse.sale.summary'].sudo().search_read(
            [
                ('product_id', 'in',
                 [p['id'] for p in products]),
                ('warehouse_id', 'in', [w['id'] for w in warehouses]),
                ('date', 'in', list(dates)),
                ('is_legacy_system', '=', True)
            ],
            ['id', 'product_id', 'warehouse_id', 'quantity_sold',
             'amount_total', 'costo_total', 'date']
        )
        sales_summary_map = {
            (s['product_id'][0], s['warehouse_id'][0], str(s['date'])): s
            for s in sales_summaries
        }

        # Paso 6: Listas para operaciones en lote
        errors_to_create = []
        summaries_to_create = []
        summaries_to_update = []

        for item in aggregated_data_list:

            id_product = item['id_product']
            quantity_sold = item['quantity_sold']
            amount_total = item['amount_total']
            costo_total = item['costo_total']
            date = item['date']
            date_str = str(item['date'])
            warehouse_id = item['warehouse_id']

            product_info = product_map.get(id_product)
            warehouse_info = warehouse_map.get(warehouse_id)

            # Registrar errores si no se encuentra producto o almacén
            if not warehouse_info:
                errors_to_create.append({
                    'error_details': f"Almacén no encontrado: {warehouse_id}"})
                continue
            if not product_info:
                errors_to_create.append(
                    {'error_details': f"Producto no encontrado: {id_product}"})
                continue

            product_variant_id = product_info['id']
            warehouse_id_int = warehouse_info

            # Verificar si existe un resumen de ventas
            summary_key = (product_variant_id, warehouse_id_int, date_str)
            existing_summary = sales_summary_map.get(summary_key)

            if not existing_summary:
                summaries_to_create.append({
                    'product_id': product_variant_id,
                    'quantity_sold': quantity_sold,
                    'amount_total': amount_total,
                    'date': date,
                    'costo_total': costo_total,
                    'warehouse_id': warehouse_id_int,
                    'is_legacy_system': True,
                })
            else:
                summaries_to_update.append({
                    'id': existing_summary['id'],
                    'quantity_sold': existing_summary[
                                         'quantity_sold'] + quantity_sold,
                    'amount_total': existing_summary[
                                        'amount_total'] + amount_total,
                    'costo_total': existing_summary[
                                       'costo_total'] + costo_total
                })

        # Paso 7: Crear errores en lote
        if errors_to_create:
            request.env['sales.summary.error'].sudo().create(errors_to_create)

        # Paso 8: Crear nuevos resúmenes de ventas en lote
        if summaries_to_create:
            request.env['product.warehouse.sale.summary'].sudo().create(
                summaries_to_create)

        # Paso 9: Actualizar resúmenes de ventas existentes en lote
        # Nota: El encolamiento para reabastecimiento se hace automáticamente
        # en el write() del modelo product.warehouse.sale.summary
        for summary in summaries_to_update:
            request.env['product.warehouse.sale.summary'].sudo().browse(
                summary['id']).write({
                'quantity_sold': summary['quantity_sold'],
                'amount_total': summary['amount_total'],
                'costo_total': summary['costo_total'],
            })

        time_end = time.time()
        print(f"Tiempo de ejecución: {time_end - time_start} segundos")
        return Response(
            json.dumps({
                'status': 'success',
                'message': 'Resumen de ventas creado exitosamente.',
            }),
            status=201,
            content_type='application/json'
        )

        #
        # data = json.loads(request.httprequest.data.decode('utf-8')).get('data',
        #                                                                 [])
        #
        # # Extract unique product and warehouse IDs
        # product_ids = set(product.get('id_product') for product in data)
        # print(list(product_ids))
        # warehouse_ids = set(product.get('warehouse_id') for product in data)
        # date = data[0].get('date') if data else False
        #
        # # Batch fetch products
        # products = request.env['product.template'].sudo().search_read(
        #     [('id_database_old', 'in', list(product_ids))],
        #     ['id', 'name', 'product_variant_id','id_database_old']
        # )
        # product_map = {p['id_database_old']: p for p in products}
        # print(product_map,'product_map')
        #
        # # Batch fetch warehouses
        # warehouses = request.env['stock.warehouse'].sudo().search_read(
        #     [('external_id', 'in', list(warehouse_ids))],
        #     ['id','external_id']
        # )
        # warehouse_map = {w['external_id']: w['id'] for w in warehouses}
        #
        # # Batch fetch existing sales summaries
        # sales_summaries = request.env[
        #     'product.warehouse.sale.summary'].sudo().search_read(
        #     [
        #         ('product_id', 'in',
        #          [p['product_variant_id'][0] for p in products]),
        #         ('warehouse_id', 'in', [w['id'] for w in warehouses]),
        #         ('date', '=', date),
        #         ('is_legacy_system', '=', True)
        #     ],
        #     ['product_id', 'warehouse_id', 'quantity_sold', 'amount_total']
        # )
        # sales_summary_map = {
        #     (s['product_id'][0], s['warehouse_id'][0]): s
        #     for s in sales_summaries
        # }
        #
        # # Lists for batch operations
        # errors_to_create = []
        # summaries_to_create = []
        # summaries_to_update = []
        #
        # for product in data:
        #     id_product = product.get('id_product')
        #     quantity_sold = float(product.get('quantity_sold'))
        #     amount_total = float(product.get('amount_total'))
        #     date = product.get('date')
        #     warehouse_id = product.get('warehouse_id')
        #
        #     product_info = product_map.get(id_product)
        #     warehouse_info = warehouse_map.get(warehouse_id)
        #
        #     # Log errors if product or warehouse not found
        #     if not warehouse_info:
        #         errors_to_create.append({'error_details': f"W {product}"})
        #         continue
        #     if not product_info:
        #         errors_to_create.append({'error_details': f"P {product}"})
        #         continue
        #
        #     product_variant_id = product_info['product_variant_id'][0]
        #     warehouse_id_int = warehouse_info
        #
        #     # Check if sales summary exists
        #     summary_key = (product_variant_id, warehouse_id_int)
        #     existing_summary = sales_summary_map.get(summary_key)
        #
        #     if not existing_summary:
        #         summaries_to_create.append({
        #             'product_id': product_variant_id,
        #             'quantity_sold': quantity_sold,
        #             'amount_total': amount_total,
        #             'date': date,
        #             'warehouse_id': warehouse_id_int,
        #             'is_legacy_system': True,
        #         })
        #     else:
        #         summaries_to_update.append({
        #             'id': existing_summary['id'],
        #             'quantity_sold': existing_summary[
        #                                  'quantity_sold'] + quantity_sold,
        #             'amount_total': existing_summary[
        #                                 'amount_total'] + amount_total,
        #         })
        #
        # # Batch create errors
        # if errors_to_create:
        #     request.env['sales.summary.error'].sudo().create(errors_to_create)
        #
        # # Batch create new sales summaries
        # if summaries_to_create:
        #     request.env['product.warehouse.sale.summary'].sudo().create(
        #         summaries_to_create)
        #
        # # Batch update existing sales summaries
        # for summary in summaries_to_update:
        #     request.env['product.warehouse.sale.summary'].sudo().browse(
        #         summary['id']).write({
        #         'quantity_sold': summary['quantity_sold'],
        #         'amount_total': summary['amount_total'],
        #     })
        # time_end = time.time()
        # print(f"Tiempo de ejecución: {time_end - time_start} segundos")
        # return Response(
        #     json.dumps({
        #         'status': 'success',
        #         'message': 'Resumen de ventas creado exitosamente.',
        #     }),
        #     status=201,
        #     content_type='application/json'
        # )

        # time_start = time.time()
        # data = json.loads(request.httprequest.data.decode('utf-8'))
        # for product in data.get('data'):
        #     id_product = product.get('id_product')
        #     quantity_sold = product.get('quantity_sold')
        #     amount_total = product.get('amount_total')
        #     date = product.get('date')
        #     warehouse_id = product.get('warehouse_id')
        #
        #     product_id = request.env['product.template'].sudo().search_read(
        #         [('id_database_old', '=', id_product)],
        #         ['id', 'name', 'product_variant_id'],
        #         limit=1
        #     )
        #     warehouse = request.env['stock.warehouse'].sudo().search_read(
        #         [('external_id', '=', warehouse_id)],
        #         ['id'],
        #         limit=1
        #     )
        #     if not warehouse:
        #         request.env['sales.summary.error'].sudo().create({
        #             'error_details': f"W {product}",
        #         })
        #     if not product_id:
        #         request.env['sales.summary.error'].sudo().create({
        #             'error_details': f"P {product}",
        #         })
        #     if product_id and warehouse:
        #         sales_summary = request.env[
        #             'product.warehouse.sale.summary'].sudo().search([
        #             ('product_id', '=',
        #              product_id[0].get('product_variant_id')[0]),
        #             ('date', '=', date),
        #             ('warehouse_id', '=', warehouse[0].get('id')),
        #             ('is_legacy_system', '=', True)
        #         ])
        #         if not sales_summary:
        #             request.env[
        #                 'product.warehouse.sale.summary'].sudo().create({
        #                 'product_id': product_id[0].get('product_variant_id')[
        #                     0],
        #                 'quantity_sold': quantity_sold,
        #                 'amount_total': amount_total,
        #                 'date': date,
        #                 'warehouse_id': warehouse[0].get('id'),
        #                 'is_legacy_system': True,
        #             })
        #         else:
        #             sales_summary.sudo().write({
        #                 'quantity_sold': float(
        #                     quantity_sold) + sales_summary.quantity_sold,
        #                 'amount_total': float(
        #                     amount_total) + sales_summary.amount_total,
        #             })
        # time_end = time.time()
        # print(f"Tiempo de ejecución: {time_end - time_start} segundos")
        # return Response(
        #     json.dumps(
        #         {
        #             'status': 'success',
        #             'message': 'Resumen de ventas creado exitosamente.',
        #
        #         }
        #     ),
        #     status=201,
        #     content_type='application/json'
        # )
