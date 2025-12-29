from odoo import http, fields
from odoo.http import request, Response, _logger

import json


class ProductAPI(http.Controller):

    @http.route('/api/products/update/lots', type='json', auth='public',
                methods=['POST'], csrf=False)
    def update_product_stock_lots(self):
        try:
            # Obtener los datos del JSON
            data = request.httprequest.get_json()
            products = data.get('data', [])

            if not products:
                return {'status': 'error',
                        'message': 'No se recibieron productos para actualizar'}

            print(f"=== INICIO PROCESAMIENTO: {len(products)} productos ===")

            results = []

            # Procesar en lotes de 1000 registros para evitar timeouts
            BATCH_SIZE = 10000
            total_products = len(products)

            for batch_start in range(0, total_products, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total_products)
                batch_products = products[batch_start:batch_end]

                print(
                    f"Procesando lote {batch_start // BATCH_SIZE + 1}: registros {batch_start + 1} al {batch_end}")

                batch_results = self._process_product_batch(batch_products)
                results.extend(batch_results)

                # Commit intermedio para liberar memoria y evitar timeouts
                request.env.cr.commit()
                print(f"Lote {batch_start // BATCH_SIZE + 1} completado y confirmado")

            print(f"=== FIN PROCESAMIENTO: {len(results)} resultados ===")
            return {'status': 'success', 'results': results, 'total_processed': len(results)}

        except Exception as e:
            print(f"ERROR GENERAL: {str(e)}")
            # Rollback en caso de error
            request.env.cr.rollback()
            return {'status': 'error', 'message': str(e)}

    def _process_product_batch(self, batch_products):
        """Procesa un lote de productos de manera optimizada"""

        print(f"--- Iniciando procesamiento de lote con {len(batch_products)} productos ---")

        # Colecciones para operaciones en lote
        templates_to_create = []
        templates_to_update = {}
        products_to_create = []
        quants_to_create = []
        quants_to_update = {}
        lot_operations = []

        results = []

        # Pre-cargar datos necesarios para evitar múltiples consultas
        print("Buscando impuesto IVA...")
        iva_tax = request.env['account.tax'].sudo().search(
            [('name', 'ilike', 'IVA')], limit=1)
        print(f"IVA encontrado: {iva_tax.name if iva_tax else 'No encontrado'}")

        # Extraer todos los IDs únicos para búsquedas en lote
        cleaned_iditems = [product.get('iditem', '').lstrip('0') for product in batch_products]
        idbodegas = list(set([product.get('idbodega', '') for product in batch_products]))

        print(f"IDs únicos a procesar: {len(set(cleaned_iditems))}")
        print(f"Bodegas únicas: {len(idbodegas)}")

        # Búsquedas en lote
        print("Realizando búsquedas masivas...")
        existing_templates = {
            template.id_database_old: template
            for template in request.env['product.template'].sudo().search([
                ('id_database_old', 'in', cleaned_iditems)
            ])
        }
        print(f"Plantillas existentes encontradas: {len(existing_templates)}")

        warehouses = {
            warehouse.external_id: warehouse
            for warehouse in request.env['stock.warehouse'].sudo().search([
                ('external_id', 'in', idbodegas)
            ])
        }
        print(f"Bodegas encontradas: {len(warehouses)}")

        # Procesar cada producto del lote
        for i, product_data in enumerate(batch_products):
            if i % 100 == 0:  # Log cada 100 productos
                print(f"Procesando producto {i + 1}/{len(batch_products)}")

            cleaned_iditem = product_data.get('iditem', '').lstrip('0')
            idbodega = product_data.get('idbodega', '')
            cantidad_stock = product_data.get('cantidad_stock')
            lot_id = product_data.get('lote', False)
            lot_exp_date = product_data.get('lote_date_exp', False)
            aplica_iva = product_data.get('iva')

            print(
                f"Procesando producto {cleaned_iditem}: aplica_iva={aplica_iva}, stock={cantidad_stock}")

            # Verificar bodega
            warehouse = warehouses.get(idbodega)
            if not warehouse:
                print(f"ERROR: Bodega {idbodega} no encontrada")
                results.append({
                    'iditem': cleaned_iditem,
                    'idbodega': idbodega,
                    'status': 'error',
                    'message': 'Bodega no encontrada'
                })
                continue

            # Gestión de plantillas
            template = existing_templates.get(cleaned_iditem)

            if not template:
                # Preparar para crear plantilla
                print(f"Preparando creación de plantilla para {cleaned_iditem}")
                product_name = product_data.get('name', f'Producto {cleaned_iditem}')
                template_data = {
                    'name': product_name,
                    'id_database_old': cleaned_iditem,
                    'type': 'product',
                    'taxes_id': [(6, 0, [iva_tax.id])] if aplica_iva == 1 else [(5, 0, 0)],
                }
                templates_to_create.append((cleaned_iditem, template_data, product_data))
            else:
                print(f"Plantilla existente encontrada para {cleaned_iditem}: {template.name}")
                # Preparar para actualizar plantilla si es necesario
                if cleaned_iditem not in templates_to_update and aplica_iva is not None:
                    template_update = {
                        'taxes_id': [(6, 0, [iva_tax.id])] if aplica_iva == 1 else [(5, 0, 0)]
                    }
                    templates_to_update[cleaned_iditem] = (template, template_update)
                    print(f"Preparando actualización de impuestos para {cleaned_iditem}")

                # Preparar operaciones de stock
                self._prepare_stock_operations(
                    template, warehouse, cantidad_stock, lot_id, lot_exp_date,
                    cleaned_iditem, products_to_create, quants_to_create,
                    quants_to_update, lot_operations
                )

        # Ejecutar operaciones en lote
        print("Ejecutando operaciones en lote...")
        self._execute_batch_operations(
            templates_to_create, templates_to_update, products_to_create,
            quants_to_create, quants_to_update, lot_operations,
            warehouses, results
        )

        print(f"--- Lote completado: {len(results)} resultados ---")
        return results

    def _prepare_stock_operations(self, template, warehouse, cantidad_stock, lot_id,
                                  lot_exp_date, cleaned_iditem, products_to_create,
                                  quants_to_create, quants_to_update, lot_operations):
        """Prepara las operaciones de stock para ejecución en lote"""

        # Buscar producto existente
        product = request.env['product.product'].sudo().search([
            ('product_tmpl_id', '=', template.id)
        ], limit=1)

        if not product:
            print(f"Producto no existe para plantilla {cleaned_iditem}, preparando creación")
            products_to_create.append({
                'name': template.name,
                'product_tmpl_id': template.id,
                'template_ref': cleaned_iditem  # Para referencia posterior
            })
            return  # El stock se manejará después de crear el producto

        if lot_id:
            print(f"Preparando operación de lote {lot_id} para producto {cleaned_iditem}")
            lot_operations.append({
                'lot_id': lot_id,
                'product': product,
                'warehouse': warehouse,
                'cantidad_stock': cantidad_stock,
                'lot_exp_date': lot_exp_date,
                'cleaned_iditem': cleaned_iditem
            })
        else:
            print(f"Preparando operación de stock sin lote para producto {cleaned_iditem}")
            # Verificar quant existente
            quant = request.env['stock.quant'].sudo().search([
                ('product_id', '=', product.id),
                ('location_id', '=', warehouse.lot_stock_id.id)
            ], limit=1)

            if quant:
                print(
                    f"Quant existente encontrado para producto {cleaned_iditem}, preparando actualización")
                quants_to_update[quant.id] = cantidad_stock
            else:
                print(f"Quant no existe para producto {cleaned_iditem}, preparando creación")
                quants_to_create.append({
                    'product_id': product.id,
                    'location_id': warehouse.lot_stock_id.id,
                    'quantity': cantidad_stock
                })

    def _execute_batch_operations(self, templates_to_create, templates_to_update,
                                  products_to_create, quants_to_create, quants_to_update,
                                  lot_operations, warehouses, results):
        """Ejecuta todas las operaciones preparadas en lote"""

        # 1. Crear plantillas en lote
        if templates_to_create:
            print(f"Creando {len(templates_to_create)} plantillas en lote...")
            template_values = [data[1] for data in templates_to_create]
            created_templates = request.env['product.template'].sudo().create(template_values)
            print(f"Plantillas creadas exitosamente: {len(created_templates)}")

            # Crear productos para las nuevas plantillas
            new_products_data = []
            for i, (cleaned_iditem, _, product_data) in enumerate(templates_to_create):
                template = created_templates[i]
                new_products_data.append({
                    'name': template.name,
                    'product_tmpl_id': template.id
                })

                # Preparar stock para nuevos productos
                warehouse = warehouses.get(product_data.get('idbodega', ''))
                if warehouse:
                    cantidad_stock = product_data.get('cantidad_stock')
                    lot_id = product_data.get('lote', False)

                    if not lot_id:
                        quants_to_create.append({
                            'product_id': 'PENDING',  # Se actualizará después
                            'location_id': warehouse.lot_stock_id.id,
                            'quantity': cantidad_stock,
                            'template_index': i  # Para mapear con el producto creado
                        })
                    else:
                        # Añadir a operaciones de lote pendientes
                        lot_operations.append({
                            'lot_id': lot_id,
                            'product': 'PENDING',  # Se actualizará después
                            'warehouse': warehouse,
                            'cantidad_stock': cantidad_stock,
                            'lot_exp_date': product_data.get('lote_date_exp', False),
                            'cleaned_iditem': cleaned_iditem,
                            'template_index': i
                        })

                results.append({
                    'iditem': cleaned_iditem,
                    'status': 'created',
                    'message': f'Producto {template.name} creado exitosamente'
                })

            # Crear productos en lote
            if new_products_data:
                print(f"Creando {len(new_products_data)} productos en lote...")
                created_products = request.env['product.product'].sudo().create(new_products_data)
                print(f"Productos creados exitosamente: {len(created_products)}")

                # Actualizar product_id en quants pendientes
                for quant_data in quants_to_create:
                    if quant_data.get('product_id') == 'PENDING':
                        template_index = quant_data.pop('template_index')
                        quant_data['product_id'] = created_products[template_index].id

                # Actualizar product en operaciones de lote pendientes
                for lot_op in lot_operations:
                    if lot_op.get('product') == 'PENDING':
                        template_index = lot_op.pop('template_index')
                        lot_op['product'] = created_products[template_index]

        # 2. Actualizar plantillas en lote
        if templates_to_update:
            print(f"Actualizando {len(templates_to_update)} plantillas...")
            # Agrupar actualizaciones por tipo de datos para escritura masiva
            update_groups = {}
            for cleaned_iditem, (template, update_data) in templates_to_update.items():
                # Convertir update_data a string para usar como clave de agrupación
                update_key = str(sorted(update_data.items()))
                if update_key not in update_groups:
                    update_groups[update_key] = {'data': update_data, 'templates': [], 'items': []}
                update_groups[update_key]['templates'].append(template)
                update_groups[update_key]['items'].append(cleaned_iditem)

            # Ejecutar actualizaciones masivas por grupo
            for update_key, group in update_groups.items():
                templates_recordset = request.env['product.template'].sudo().browse(
                    [t.id for t in group['templates']])
                templates_recordset.write(group['data'])

                # Agregar resultados
                for cleaned_iditem in group['items']:
                    template_name = next(
                        t.name for t in group['templates'] if t.id_database_old == cleaned_iditem)
                    results.append({
                        'iditem': cleaned_iditem,
                        'status': 'updated',
                        'message': f'Producto {template_name} actualizado exitosamente'
                    })
            print(f"Plantillas actualizadas en {len(update_groups)} operaciones masivas")

        # 3. Crear quants en lote
        if quants_to_create:
            # Filtrar quants válidos
            valid_quants = [q for q in quants_to_create if q.get('product_id') != 'PENDING']
            if valid_quants:
                print(f"Creando {len(valid_quants)} quants en lote...")
                request.env['stock.quant'].sudo().create(valid_quants)
                print(f"Quants creados exitosamente: {len(valid_quants)}")

        # 4. Actualizar quants existentes en lote
        if quants_to_update:
            print(f"Actualizando {len(quants_to_update)} quants existentes...")
            # Realizar actualización masiva de quants
            quant_ids = list(quants_to_update.keys())
            quants_recordset = request.env['stock.quant'].sudo().browse(quant_ids)

            # Preparar datos para actualización SQL directa (más eficiente)
            if len(quants_to_update) > 100:  # Para grandes volúmenes, usar SQL directo
                print("Usando actualización SQL directa para mejor rendimiento...")
                query_parts = []
                for quant_id, quantity in quants_to_update.items():
                    query_parts.append(f"({quant_id}, {quantity})")

                if query_parts:
                    query = f"""
                    UPDATE stock_quant 
                    SET quantity = data.quantity 
                    FROM (VALUES {','.join(query_parts)}) AS data(id, quantity)
                    WHERE stock_quant.id = data.id
                    """
                    request.env.cr.execute(query)
            else:
                # Para volúmenes menores, usar write normal
                for quant_id, quantity in quants_to_update.items():
                    request.env['stock.quant'].sudo().browse(quant_id).write({'quantity': quantity})

            print(f"Quants actualizados: {len(quants_to_update)}")

        # 5. Procesar lotes masivamente
        if lot_operations:
            print(f"Procesando {len(lot_operations)} operaciones de lotes...")
            batch_lot_results = self._process_lots_batch(lot_operations)
            results.extend(batch_lot_results)
            print(f"Operaciones de lotes completadas: {len(lot_operations)}")

    # Versión optimizada que se ejecuta en lote desde _execute_batch_operations
    def _process_lots_batch(self, lot_operations):
        """Procesa múltiples operaciones de lotes de manera optimizada"""

        if not lot_operations:
            return []

        print(f"=== PROCESAMIENTO MASIVO DE LOTES: {len(lot_operations)} operaciones ===")

        # Agrupar operaciones por combinación producto-warehouse para optimizar búsquedas
        grouped_ops = {}
        for lot_op in lot_operations:
            key = (lot_op['product'].id, lot_op['warehouse'].id)
            if key not in grouped_ops:
                grouped_ops[key] = []
            grouped_ops[key].append(lot_op)

        print(f"Operaciones agrupadas en {len(grouped_ops)} combinaciones producto-warehouse")

        results = []
        lots_to_create = []
        lots_to_update = {}
        quants_to_create = []
        quants_to_update = {}

        # Pre-cargar todos los lotes existentes para los productos en cuestión
        all_product_ids = [op['product'].id for op in lot_operations]
        all_warehouse_location_ids = [op['warehouse'].lot_stock_id.id for op in lot_operations]

        existing_lots_by_product = {}
        existing_lots = request.env['stock.lot'].sudo().search([
            ('product_id', 'in', all_product_ids),
            ('location_id', 'in', all_warehouse_location_ids)
        ])

        for lot in existing_lots:
            key = (lot.product_id.id, lot.location_id.id)
            if key not in existing_lots_by_product:
                existing_lots_by_product[key] = []
            existing_lots_by_product[key].append(lot)

        print(f"Pre-cargados {len(existing_lots)} lotes existentes")

        # Pre-cargar todos los quants existentes
        existing_quants = {}
        quants = request.env['stock.quant'].sudo().search([
            ('product_id', 'in', all_product_ids),
            ('location_id', 'in', all_warehouse_location_ids)
        ])

        for quant in quants:
            key = (quant.product_id.id, quant.location_id.id,
                   quant.lot_id.id if quant.lot_id else None)
            existing_quants[key] = quant

        print(f"Pre-cargados {len(existing_quants)} quants existentes")

        # Procesar cada operación
        for i, lot_op in enumerate(lot_operations):
            if i % 100 == 0:
                print(f"Procesando lote {i + 1}/{len(lot_operations)}")

            product = lot_op['product']
            warehouse = lot_op['warehouse']
            lot_id = lot_op['lot_id']
            cantidad_stock = lot_op['cantidad_stock']
            lot_exp_date = lot_op['lot_exp_date']
            cleaned_iditem = lot_op['cleaned_iditem']

            # Verificar lotes existentes para este producto-warehouse
            key = (product.id, warehouse.lot_stock_id.id)
            existing_lots_for_product = existing_lots_by_product.get(key, [])
            existing_lots_count = len(existing_lots_for_product)

            # Determinar nombre del lote
            is_first_lot = existing_lots_count == 0
            lot_name = f"Gen{lot_id}" if is_first_lot else lot_id
            lot_name_gen = f"Gen{lot_id}"

            # Buscar lote existente
            existing_lot = None
            for lot in existing_lots_for_product:
                if lot.name in [lot_name_gen, lot_name]:
                    existing_lot = lot
                    break

            if existing_lot:
                # Preparar actualización del lote
                update_data = {'product_qty': cantidad_stock}
                if lot_exp_date and existing_lot.expiration_date != lot_exp_date:
                    update_data['expiration_date'] = lot_exp_date

                if existing_lot.id not in lots_to_update:
                    lots_to_update[existing_lot.id] = update_data

                lot_record_id = existing_lot.id
                message = f'Stock actualizado a {cantidad_stock} en la bodega {warehouse.external_id}'
            else:
                # Preparar creación del lote
                lots_to_create.append({
                    'name': lot_name,
                    'product_id': product.id,
                    'product_qty': cantidad_stock,
                    'expiration_date': lot_exp_date,
                    'location_id': warehouse.lot_stock_id.id,
                    'temp_ref': (cleaned_iditem, len(lots_to_create))  # Para referencia temporal
                })
                lot_record_id = f"NEW_{len(lots_to_create) - 1}"  # Referencia temporal
                message = f'Stock preparado para crear con {cantidad_stock} en la bodega {warehouse.external_id}'

            # Gestionar quant
            if is_first_lot:
                quant_key = (product.id, warehouse.lot_stock_id.id, None)
            else:
                quant_key = (product.id, warehouse.lot_stock_id.id,
                             existing_lot.id if existing_lot else None)

            existing_quant = existing_quants.get(quant_key)

            if existing_quant:
                # Actualizar quant existente
                if isinstance(lot_record_id, str) and lot_record_id.startswith("NEW_"):
                    # Quant para lote nuevo - se procesará después de crear el lote
                    quants_to_create.append({
                        'product_id': product.id,
                        'location_id': warehouse.lot_stock_id.id,
                        'quantity': cantidad_stock,
                        'lot_ref': lot_record_id,  # Referencia temporal
                        'update_existing': existing_quant.id
                    })
                else:
                    quants_to_update[existing_quant.id] = {
                        'quantity': cantidad_stock,
                        'lot_id': lot_record_id
                    }
            else:
                # Crear nuevo quant
                quants_to_create.append({
                    'product_id': product.id,
                    'location_id': warehouse.lot_stock_id.id,
                    'quantity': cantidad_stock,
                    'lot_ref': lot_record_id if isinstance(lot_record_id, str) else lot_record_id
                })

            results.append({
                'iditem': cleaned_iditem,
                'status': 'success',
                'message': message
            })

        # Ejecutar operaciones masivas
        print("Ejecutando operaciones masivas de lotes...")

        # 1. Crear lotes nuevos
        if lots_to_create:
            print(f"Creando {len(lots_to_create)} lotes nuevos...")
            # Remover referencias temporales antes de crear
            clean_lots_data = []
            temp_refs = []
            for lot_data in lots_to_create:
                temp_ref = lot_data.pop('temp_ref')
                temp_refs.append(temp_ref)
                clean_lots_data.append(lot_data)

            created_lots = request.env['stock.lot'].sudo().create(clean_lots_data)
            print(f"Lotes creados: {len(created_lots)}")

            # Mapear referencias temporales con IDs reales
            lot_id_mapping = {}
            for i, lot in enumerate(created_lots):
                lot_id_mapping[f"NEW_{i}"] = lot.id

            # Actualizar referencias en quants
            for quant_data in quants_to_create:
                if isinstance(quant_data.get('lot_ref'), str) and quant_data['lot_ref'].startswith(
                        "NEW_"):
                    quant_data['lot_id'] = lot_id_mapping[quant_data['lot_ref']]
                    del quant_data['lot_ref']

        # 2. Actualizar lotes existentes
        if lots_to_update:
            print(f"Actualizando {len(lots_to_update)} lotes existentes...")
            # Agrupar actualizaciones similares
            update_groups = {}
            for lot_id, update_data in lots_to_update.items():
                update_key = str(sorted(update_data.items()))
                if update_key not in update_groups:
                    update_groups[update_key] = {'data': update_data, 'lot_ids': []}
                update_groups[update_key]['lot_ids'].append(lot_id)

            for update_key, group in update_groups.items():
                lots_recordset = request.env['stock.lot'].sudo().browse(group['lot_ids'])
                lots_recordset.write(group['data'])

            print(f"Lotes actualizados en {len(update_groups)} operaciones masivas")

        # 3. Procesar quants
        if quants_to_create:
            print(f"Procesando {len(quants_to_create)} operaciones de quants...")
            # Separar creaciones de actualizaciones
            pure_creates = []
            updates_from_creates = []

            for quant_data in quants_to_create:
                if 'update_existing' in quant_data:
                    # Es una actualización disfrazada
                    existing_id = quant_data.pop('update_existing')
                    quant_data.pop('lot_ref', None)
                    quants_to_update[existing_id] = quant_data
                else:
                    # Es una creación pura
                    quant_data.pop('lot_ref', None)
                    pure_creates.append(quant_data)

            if pure_creates:
                request.env['stock.quant'].sudo().create(pure_creates)
                print(f"Creados {len(pure_creates)} quants nuevos")

        # 4. Actualizar quants existentes
        if quants_to_update:
            print(f"Actualizando {len(quants_to_update)} quants existentes...")
            if len(quants_to_update) > 100:
                # SQL directo para mejor rendimiento
                query_parts = []
                for quant_id, update_data in quants_to_update.items():
                    quantity = update_data.get('quantity', 0)
                    lot_id = update_data.get('lot_id', 'NULL')
                    if lot_id != 'NULL':
                        query_parts.append(f"({quant_id}, {quantity}, {lot_id})")
                    else:
                        query_parts.append(f"({quant_id}, {quantity}, NULL)")

                if query_parts:
                    query = f"""
                    UPDATE stock_quant 
                    SET quantity = data.quantity, lot_id = data.lot_id
                    FROM (VALUES {','.join(query_parts)}) AS data(id, quantity, lot_id)
                    WHERE stock_quant.id = data.id
                    """
                    request.env.cr.execute(query)
            else:
                # Write normal para volúmenes menores
                for quant_id, update_data in quants_to_update.items():
                    request.env['stock.quant'].sudo().browse(quant_id).write(update_data)

            print(f"Quants actualizados: {len(quants_to_update)}")

        print(f"=== FIN PROCESAMIENTO MASIVO DE LOTES ===")
        return results

    def lot_management(self, lot_id, product, warehouse, cantidad_stock, lot_exp_date):
        """Método individual mantenido para compatibilidad - usa la versión optimizada internamente"""
        return self._process_lots_batch([{
            'lot_id': lot_id,
            'product': product,
            'warehouse': warehouse,
            'cantidad_stock': cantidad_stock,
            'lot_exp_date': lot_exp_date,
            'cleaned_iditem': f"single_{product.id}"
        }])[0]['message']

    @http.route('/api/products/update', type='http', auth='public', methods=['POST'], csrf=False)
    def update_product_stock(self):
        """
        api para actualizar los stocks de los productos asdasdsa
        """
        try:
            data = request.httprequest.get_json()
            products = data.get('data', [])
            try:
                monitor = request.env['api.monitor'].sudo().search([
                    ('endpoint', '=', 'api/products/update')
                ], limit=1)

                if monitor:
                    # Registrar que recibimos una petición
                    monitor.register_request()
            except Exception as e:
                pass

            if not products:
                return Response(
                    json.dumps({'status': 'error',
                                'message': 'No se recibieron productos para actualizar'}),
                    status=400,
                    content_type='application/json'
                )

            results = []
            quants_to_create = []

            # Buscar impuestos
            # iva_tax_15 = request.env['account.tax'].sudo().browse(1)
            # iva_tax_0 = request.env['account.tax'].sudo().browse(10)
            # iva_tax_purchase_15 = request.env['account.tax'].sudo().browse(26)
            # iva_tax_purchase_15 = request.env['account.tax'].sudo().browse(61)

            cleaned_iditems = [p.get('iditem', '').lstrip('0') for p in products]
            idbodegas = list(set([p.get('idbodega', '') for p in products]))

            existing_templates = {
                t.id_database_old: t
                for t in request.env['product.template'].sudo().search(
                    [('id_database_old', 'in', cleaned_iditems)]
                )
            }

            warehouses = {
                w.external_id: w
                for w in request.env['stock.warehouse'].sudo().search(
                    [('external_id', 'in', idbodegas)]
                )
            }

            templates_to_create = []
            templates_to_update = {}
            # Mapa para guardar aplica_iva por cleaned_iditem
            aplica_iva_map = {}

            for product_data in products:
                cleaned_iditem = product_data.get('iditem', '').lstrip('0')
                aplica_iva = product_data.get('iva')
                aplica_iva_map[cleaned_iditem] = aplica_iva  # Guardar para uso posterior
                template = existing_templates.get(cleaned_iditem)

                if not template:
                    # NO asignar supplier_taxes_id aquí, se limpiará y asignará después
                    templates_to_create.append({
                        'name': product_data.get('nombre_producto'),
                        'id_database_old': cleaned_iditem,
                        'detailed_type': 'product',
                        # No asignar impuestos aquí para evitar duplicados
                    })
                # else:
                #     templates_to_update[template.id] = template

            if templates_to_create:
                new_templates = request.env['product.template'].sudo().create(templates_to_create)
                for idx, template in enumerate(new_templates):
                    cleaned_iditem = templates_to_create[idx]['id_database_old']
                    aplica_iva = aplica_iva_map.get(cleaned_iditem)
                    
                    # Limpiar primero ambos campos de impuestos para evitar duplicados
                    template.sudo().write({
                        'supplier_taxes_id': [(5, 0, 0)],  # Limpiar primero
                        'taxes_id': [(5, 0, 0)]  # Limpiar primero
                    })
                    # Ahora asignar solo el impuesto correcto una vez
                    template.sudo().write({
                        'supplier_taxes_id': [(6, 0, [26])] if aplica_iva == 1 else [(6, 0, [61])],
                        'taxes_id': [(6, 0, [1])] if aplica_iva == 1 else [(6, 0, [10])]
                    })
                    existing_templates[cleaned_iditem] = template
                    results.append({
                        'iditem': templates_to_create[idx]['id_database_old'],
                        'status': 'created',
                        'message': f'Producto {template.name} creado exitosamente'
                    })
            #
            template_ids = [t.id for t in existing_templates.values()]
            existing_products = {
                p.product_tmpl_id.id: p
                for p in request.env['product.product'].sudo().search(
                    [('product_tmpl_id', 'in', template_ids)]
                )
            }
            #
            # products_to_create = []
            # for template_id, template in [(t.id, t) for t in existing_templates.values()]:
            #     if template_id not in existing_products:
            #         products_to_create.append({
            #             'name': template.name,
            #             'product_tmpl_id': template_id
            #         })
            #
            # if products_to_create:
            #     new_products = request.env['product.product'].sudo().create(products_to_create)
            #     for product in new_products:
            #         existing_products[product.product_tmpl_id.id] = product
            #
            product_ids = [p.id for p in existing_products.values()]
            location_ids = [w.lot_stock_id.id for w in warehouses.values()]
            #
            existing_quants = {}
            if product_ids and location_ids:
                quants = request.env['stock.quant'].sudo().search([
                    ('product_id', 'in', product_ids),
                    ('location_id', 'in', location_ids)
                ])
                for quant in quants:
                    key = (quant.product_id.id, quant.location_id.id)
                    existing_quants[key] = quant

            quants_to_update = {}
            for product_data in products:
                cleaned_iditem = product_data.get('iditem', '').lstrip('0')
                idbodega = product_data.get('idbodega', '')
                cantidad_stock = product_data.get('cantidad_stock')

                template = existing_templates.get(cleaned_iditem)
                if not template:
                    continue

                warehouse = warehouses.get(idbodega)
                if not warehouse:
                    request.env['sales.summary.error'].sudo().create({
                        'error_details': f'Bodega {idbodega} no encontrada para producto {cleaned_iditem}',
                    })
                    results.append({
                        'idbodega': idbodega,
                        'status': 'error',
                        'message': 'Bodega no encontrada'
                    })
                    continue

                product = existing_products.get(template.id)
                if not product:
                    request.env['sales.summary.error'].sudo().create({
                        'error_details': f'Producto no encontrado para plantilla {template.id} (iditem {cleaned_iditem})',
                    })
                    continue

                key = (product.id, warehouse.lot_stock_id.id)
                quant = existing_quants.get(key)

                if quant:
                    quants_to_update[quant.id] = cantidad_stock
                    message = f'Stock actualizado a {cantidad_stock} en la bodega {idbodega}'
                else:
                    quants_to_create.append({
                        'product_id': product.id,
                        'location_id': warehouse.lot_stock_id.id,
                        'quantity': cantidad_stock
                    })
                    message = f'Stock creado con {cantidad_stock} en la bodega {idbodega}'

                results.append({
                    'iditem': cleaned_iditem,
                    'status': 'success',
                    'message': message
                })

            if quants_to_update:
                for quant_id, quantity in quants_to_update.items():
                    request.env['stock.quant'].sudo().browse(quant_id).write({'quantity': quantity})

            if quants_to_create:
                request.env['stock.quant'].sudo().create(quants_to_create)

            # ✅ Devolver respuesta con status HTTP 201
            return Response(
                json.dumps({'status': 'success', 'results': results}),
                status=201,
                content_type='application/json'
            )

        except Exception as e:
            print(e)
            return Response(
                json.dumps({'status': 'error', 'message': str(e)}),
                status=500,
                content_type='application/json'
            )

    def _tax_command(self, aplica_iva, iva_tax_id):
        """Devuelve el comando ORM (6,0,ids) asegurando reemplazo (o limpieza si no aplica)."""
        try:
            if iva_tax_id and aplica_iva == 1:
                return [(6, 0, [iva_tax_id])]
        except Exception:
            pass
        # Forzar lista vacía (reemplaza cualquier impuesto existente)
        return [(6, 0, [])]

    # def update_product_stock(self):
    #     try:
    #         # Obtener los datos del JSON
    #         data = request.httprequest.get_json()
    #         products = data.get('data', [])
    #
    #         if not products:
    #             return {'status': 'error',
    #                     'message': 'No se recibieron productos para actualizar'}
    #
    #         results = []
    #         quants_to_create = []
    #         global taxes_id
    #
    #         # Buscar el impuesto de IVA
    #         iva_tax = request.env['account.tax'].sudo().search(
    #             [('name', 'ilike', 'IVA')], limit=1)
    #
    #         for product_data in products:
    #             cleaned_iditem = product_data.get('iditem', '').lstrip('0')
    #             idbodega = product_data.get('idbodega', '')
    #             cantidad_stock = product_data.get('cantidad_stock')
    #             # nuevo_precio = product_data.get('price', None)
    #
    #             # Asegurar que el valor 'iva' se interprete como entero
    #             aplica_iva = product_data.get('iva')
    #
    #             # Verificar si la plantilla del producto ya existe
    #             template = request.env['product.template'].sudo().search(
    #                 [('id_database_old', '=', cleaned_iditem)], limit=1
    #             )
    #
    #             if not template:
    #                 # Crear la plantilla como producto almacenable
    #                 product_name = product_data.get('name',
    #                                                 f'Producto {cleaned_iditem}')
    #                 template_values = {
    #                     'name': product_name,
    #                     'id_database_old': cleaned_iditem,
    #                     # 'list_price': nuevo_precio or 0.0,
    #                     'type': 'product',  # Producto almacenable
    #                     'taxes_id': [
    #                         (6, 0, [iva_tax.id])] if aplica_iva == 1 else [
    #                         (5, 0, 0)],
    #                 }
    #
    #                 template = request.env['product.template'].sudo().create(
    #                     template_values)
    #                 results.append({
    #                     'iditem': cleaned_iditem,
    #                     'status': 'created',
    #                     'message': f'Producto {template.name} creado exitosamente'
    #                 })
    #             else:
    #                 # Actualizar precio e impuestos si ya existe
    #                 template_values = {
    #                     # 'list_price': nuevo_precio if nuevo_precio is not None else template.list_price,
    #                     # 'taxes_id': [
    #                     #     (6, 0, [iva_tax.id])] if aplica_iva == 1 else [
    #                     #     (5, 0, 0)]  # Actualizar impuestos explícitamente
    #                 }
    #                 template.sudo().write(template_values)
    #                 results.append({
    #                     'iditem': cleaned_iditem,
    #                     'status': 'updated',
    #                     'message': f'Producto {template.name} actualizado exitosamente'
    #                 })
    #
    #             # Buscar o crear el producto asociado a la plantilla
    #             product = request.env['product.product'].sudo().search(
    #                 [('product_tmpl_id', '=', template.id)], limit=1
    #             )
    #
    #             if not product:
    #                 product = request.env['product.product'].sudo().create({
    #                     'name': template.name,
    #                     'product_tmpl_id': template.id
    #                 })
    #
    #             # Buscar la bodega usando el external_id
    #             warehouse = request.env['stock.warehouse'].sudo().search(
    #                 [('external_id', '=', idbodega)], limit=1
    #             )
    #
    #             if not warehouse:
    #                 results.append({
    #                     'idbodega': idbodega,
    #                     'status': 'error',
    #                     'message': 'Bodega no encontrada'
    #                 })
    #                 continue
    #
    #             # Verificar o crear el quant para este producto y ubicación
    #             quant = request.env['stock.quant'].sudo().search([
    #                 ('product_id', '=', product.id),
    #                 ('location_id', '=', warehouse.lot_stock_id.id)
    #             ], limit=1)
    #
    #             if quant:
    #                 quant.sudo().write({'quantity': cantidad_stock})
    #                 message = f'Stock actualizado a {cantidad_stock} en la bodega {idbodega}'
    #             else:
    #                 quants_to_create.append({
    #                     'product_id': product.id,
    #                     'location_id': warehouse.lot_stock_id.id,
    #                     'quantity': cantidad_stock
    #                 })
    #                 message = f'Stock preparado para crear con {cantidad_stock} en la bodega {idbodega}'
    #
    #             results.append({
    #                 'iditem': cleaned_iditem,
    #                 'status': 'success',
    #                 'message': message
    #             })
    #
    #         # Crear los registros de stock en bloque
    #         if quants_to_create:
    #             request.env['stock.quant'].sudo().create(quants_to_create)
    #
    #         return {'status': 'success', 'results': results}
    #
    #     except Exception as e:
    #         return {'status': 'error', 'message': str(e)}

    class ProductUpdateAPI(http.Controller):
        @http.route('/api/update-product', type='json', auth='none', methods=['POST'], csrf=False)
        def update_or_create_product(self):
            """api para actualizar o crear y actualziar productos  en Odoo desde el otro sistema"""
            try:
                data = request.httprequest.get_json()
                products = data.get('data', [])

                # Usar entorno con superusuario para evitar problemas de permisos
                # auth='none' requiere que obtengamos el entorno manualmente
                env = request.env(user=1)  # Usuario administrador (SUPERUSER)

                if not products:
                    return {'status': 'error',
                            'message': 'No se recibieron datos para procesar'}

                results = []
                # Search for 15% IVA tax  === 1
                # Search for 0% IVA tax ===10
                for product_data in products:
                    # Extract and clean data
                    product_id = product_data.get('id', '').lstrip('0')
                    product_name = product_data.get('name',
                                                    f'Producto Nuevo {product_id}').strip()
                    price = product_data.get('price', 0.0)
                    cost = product_data.get('cost', 0.0)
                    coupon = product_data.get('coupon', 0.0)
                    unit_size = product_data.get('unit_size')
                    unit_size_name = product_data.get('unit_size_name').title().strip()
                    last_cost = product_data.get('last_cost', 0.0)
                    default_code = product_data.get('default_code', '').strip()
                    marca_name = product_data.get('marca', '').strip()
                    brand_id = product_data.get('brandid', '').strip()
                    laboratory_id = product_data.get('laboratoryid', '').strip()
                    laboratorio_name = product_data.get('laboratorio', '').strip()
                    aplica_iva = product_data.get('iva')
                    available_in_pos = product_data.get('available_in_pos', True)

                    # uom
                    if len(unit_size_name) == 0:
                        unit_size_name = "Caja"
                    umo_name = f"{unit_size_name} x {unit_size}".strip()
                    uom = env['uom.uom'].search(
                        [('name', '=', umo_name)], limit=1)
                    if not uom:
                        uom = env['uom.uom'].search(
                            [('name', '=', f"Caja x {unit_size}")], limit=1)
                        env['sales.summary.error'].create({
                            'error_details': f'Unidad de medida {umo_name} no encontrada para producto {product_id}',
                        })

                    # Determine tax based on aplica_iva
                    # tax_id = iva_tax_15.id if aplica_iva == "1" and iva_tax_15 else (iva_tax_0.id if iva_tax_0 else False)
                    marca = None
                    if brand_id:
                        # falta de normalizar el nombre de la marca
                        marca = env['product.brand'].search(
                            [('id_database_old', '=', brand_id)], limit=1)
                        if not marca:
                            marca = env['product.brand'].create(
                                {'name': marca_name, 'id_database_old': brand_id})

                    # Search or create Laboratory
                    laboratorio = None
                    if laboratory_id:
                        # falta de normalizar el nombre de la marca
                        laboratorio = env['product.laboratory'].search(
                            [('id_database_old', '=', laboratory_id)],
                            limit=1)
                        if not laboratorio:
                            laboratorio = env['product.laboratory'].create(
                                {'name': laboratorio_name, 'id_database_old': laboratory_id})

                    # Search for existing product template
                    template = env['product.template'].search(
                        [('id_database_old', '=', product_id),
                         ('active', '=', True)], limit=1)

                    if not template:
                        template_values = {
                            'name': product_name,
                            'id_database_old': product_id,
                            'list_price': price,
                            'standar_price_old': last_cost,
                            'avg_standar_price_old': cost,
                            'standard_price': cost,
                            'default_code': default_code,
                            'type': 'product',
                            'coupon': coupon or 0,
                            'uom_po_id': uom.id if uom else 1,
                            'taxes_id': [
                                (6, 0, [10])] if aplica_iva == 0 else [
                                (6, 0, [1])],
                            'brand_id': marca.id if marca else False,
                            'laboratory_id': laboratorio.id if laboratorio else False,
                            'available_in_pos': available_in_pos
                        }

                        template = env['product.template'].create(template_values)
                        results.append({
                            'id': product_id,
                            'status': 'created',
                            'message': f'Producto {template.name} creado exitosamente'
                        })
                    else:
                        # Update existing product template
                        template_values = {
                            'name': product_name,
                            'list_price': price,
                            'standar_price_old': last_cost,
                            'avg_standar_price_old': cost,
                            'default_code': default_code,
                            'standard_price': cost,
                            'coupon': coupon or 0,
                            'uom_po_id': uom.id if uom else 1,
                            'taxes_id': [
                                (6, 0, [10])] if aplica_iva == 0 else [
                                (6, 0, [1])],
                            'brand_id': marca.id if marca else template.brand_id.id,
                            'laboratory_id': laboratorio.id if laboratorio else template.laboratory_id.id,
                            'available_in_pos': available_in_pos
                        }
                        try:
                            template.write(template_values)
                        except Exception as e:
                            print(e)
                            pass

                        results.append({
                            'id': product_id,
                            'status': 'updated',
                            'message': f'Producto {template.name} actualizado exitosamente'
                        })

                return {'status': 'success', 'results': results}

            except Exception as e:
                return {'status': 'error', 'message': str(e)}

    @http.route('/api/products/search', type='json', auth='public',
                methods=['POST'],
                csrf=False)
    def search_products(self):
        try:
            # Obtener los datos del JSON enviado en el body
            data = request.httprequest.get_json()
            product_ids = data.get('product_ids',
                                   [])  # Esperamos una lista de IDs

            if not product_ids:
                return {
                    'status': 'error',
                    'message': 'No se recibieron IDs para la búsqueda'
                }

            # Realizamos la búsqueda en la base de datos
            products = request.env['product.template'].sudo().search([
                ('id_database_old', 'in', product_ids)
            ])

            # Formateamos los resultados
            result = [{
                'id': product.id,
                'name': product.name,
                'list_price': product.list_price,
                'qty_available': product.qty_available,
                'id_db_old': int(product.id_database_old),
            } for product in products]

            return {
                'status': 'success',
                'data': result
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Ocurrió un error: {str(e)}'
            }

    @http.route('/api/contacts', type='json', auth='public', methods=['POST'],
                csrf=False)
    def get_contacts(self, **kwargs):
        """Endpoint para obtener contactos por VAT"""
        try:
            data = request.httprequest.get_json()
            vat = data.get('vat')

            # Validar si se proporcionó el VAT
            if not vat:
                return {
                    'status': 'error',
                    'message': 'VAT es requerido.'
                }, 400

            # Consultar contactos por VAT
            contacts = request.env['res.partner'].sudo().search_read(
                [('vat', '=', vat)],
                ['id', 'name', 'phone', 'email', 'vat', 'id_database_old']
            )

            # Si no se encuentran contactos
            if not contacts:
                return {
                    'status': 'error',
                    'message': 'No se encontraron contactos con ese VAT.'
                }, 404

            # Devolver los contactos encontrados
            return {
                'status': 'success',
                'data': contacts
            }, 200

        except Exception as e:
            # Manejo de errores
            return {
                'status': 'error',
                'message': f'Error interno: {str(e)}'
            }, 500

    @http.route('/api/institutions/update-client', type='json', auth='public',
                methods=['POST'], csrf=False)
    def update_or_add_client(self, **kwargs):
        try:
            data = request.httprequest.get_json()
            clients = data.get('data', [])
            if not clients:
                return {"status": "error", "message": "No data provided"}

            results = []

            for client in clients:
                # Extraer los datos necesarios para cada cliente
                institution_id = client.get('idinstitucion')
                vat = client.get('ruc')
                available_amount = client.get('cupodisponible')
                available_amount_institution = client.get('cupo')
                active = client.get(
                    'active')  # Nuevo campo para verificar si se elimina el registro

                if not institution_id or not vat:
                    return {"status": "error",
                            "message": "Missing required fields: 'idinstitucion' or 'ruc'"}

                # Buscar la institución por ID
                institution = request.env['institution'].sudo().search(
                    [('id_institutions', '=', institution_id)], limit=1
                )

                if not institution:
                    return {"status": "error",
                            "message": f"Institution with ID {institution_id} not found"}

                # Buscar el cliente en el modelo res.partner por el campo 'vat'
                customer = request.env['res.partner'].sudo().search(
                    [('vat', '=', vat)], limit=1
                )

                if not customer:
                    return {"status": "error",
                            "message": f"Customer with VAT {vat} not found"}

                # Buscar el cliente asociado en la institución
                institution_client = request.env[
                    'institution.client'].sudo().search(
                    [('institution_id', '=', institution.id),
                     ('partner_id', '=', customer.id)], limit=1
                )

                if active == 0:
                    # Si el campo 'active' es 0, eliminar el registro si existe
                    if institution_client:
                        institution_client.sudo().unlink()
                        action = "deleted"
                    else:
                        action = "not_found"
                else:
                    if institution_client:
                        # Actualizar el monto si el cliente ya existe
                        institution_client.sudo().write(
                            {
                                'available_amount': available_amount,
                                'sale': available_amount_institution
                            })
                        action = "updated"
                    else:
                        # Crear el cliente si no existe
                        request.env['institution.client'].sudo().create({
                            'institution_id': institution.id,
                            'partner_id': customer.id,
                            'available_amount': available_amount,
                            'sale': available_amount_institution,
                        })
                        action = "created"

                results.append({
                    "idcustomer": vat,
                    "action": action,
                    "institution": institution_id
                })

                print(results)
            return {
                "status": "success",
                "message": "Clients processed successfully",
                "data": results
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    @http.route('/api/institutions/create-or-update', type='json',
                auth='public',
                methods=['POST'], csrf=False)
    def create_or_update_institution(self, **kwargs):
        try:
            # Obtener los datos enviados en el cuerpo de la solicitud
            data = request.httprequest.get_json()
            institutions = data.get('data', [])
            if not institutions:
                return {"status": "error", "message": "No data provided"}

            results = []

            for institution_data in institutions:
                # Validar los campos requeridos
                id_institutions = institution_data.get('id_institutions')
                name = institution_data.get('name')
                type_credit_institution = institution_data.get(
                    'type_credit_institution')

                if not id_institutions or not name or not type_credit_institution:
                    return {
                        "status": "error",
                        "message": "Missing required fields: 'id_institutions', 'name', or 'type_credit_institution'"
                    }

                # Verificar si la institución ya existe
                existing_institution = request.env[
                    'institution'].sudo().search(
                    [('id_institutions', '=', id_institutions)], limit=1
                )

                if existing_institution:
                    # Si la institución existe, actualizamos los campos permitidos
                    existing_institution.sudo().write({
                        'name': institution_data.get('name'),
                        'ruc_institution': institution_data.get(
                            'ruc_institution'),
                        'agreement_date': institution_data.get(
                            'agreement_date'),
                        'address': institution_data.get('address'),
                        'cellphone': institution_data.get('cellphone'),
                        'court_day': institution_data.get('court_day'),
                        'additional_discount_percentage': institution_data.get(
                            'additional_discount_percentage'),
                        'pvp': institution_data.get('pvp',
                                                    existing_institution.pvp),
                        # Mantiene el valor actual si no se envía
                    })
                    action = "updated"
                else:
                    # Crear la institución si no existe
                    new_institution = request.env['institution'].sudo().create(
                        {
                            'id_institutions': id_institutions,
                            'name': name,
                            'ruc_institution': institution_data.get(
                                'ruc_institution'),
                            'agreement_date': institution_data.get(
                                'agreement_date'),
                            'address': institution_data.get('address'),
                            'type_credit_institution': type_credit_institution,
                            'cellphone': institution_data.get('cellphone'),
                            'court_day': institution_data.get('court_day'),
                            'additional_discount_percentage': institution_data.get(
                                'additional_discount_percentage'),
                            'pvp': institution_data.get('pvp', '1'),
                        })
                    results.append({
                        "id_institutions": new_institution.id_institutions,
                        "name": new_institution.name,
                        "status": "created"
                    })
                    continue

                # Agregar el resultado de la operación
                results.append({
                    "id_institutions": id_institutions,
                    "name": existing_institution.name,
                    "status": action
                })

            return {
                "status": "success",
                "message": "Institutions processed successfully",
                "data": results
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}


# API DE CONTACTOS
class ContactAPIController(http.Controller):

    @http.route('/api/contact/create_or_update', type='http', auth='public',
                methods=['POST'], csrf=False)
    def create_or_update_contact(self, **post):
        try:
            data = request.httprequest.get_json()
            contacts = data.get('data', [])
            if not contacts:
                return {'status': 'error', 'message': 'No data provided.'}

            response_list = []
            for value in contacts:
                # Obtener los datos del request
                name = value.get('name')
                email = value.get('email', '@')
                phone = value.get('phone')
                street = value.get('street')
                city = value.get('city')
                vat_number = value.get('vat_number')
                id_database_old = value.get('id_database_old')

                # Validaciones básicas
                if not vat_number:
                    response_list.append(
                        {'status': 'error', 'message': 'VAT is required.'})
                    continue  # Saltar al siguiente contacto

                # if not name or not email:
                #     response_list.append({'status': 'error',
                #                           'message': 'Name and Email are required fields.'})
                #     continue

                # Determinar tipo de identificación según la longitud del VAT
                vat_identifier = 5 if len(vat_number) == 10 else (
                    4 if len(vat_number) == 13 else 0)

                # Buscar si ya existe un contacto con ese VAT
                existing_partner = request.env['res.partner'].sudo().search(
                    [('vat', '=', vat_number)], limit=1)
                # print(existing_partner)
                # breakpoint()
                if existing_partner:
                    # Si el contacto existe, actualizar solo `id_database_old`
                    existing_partner.sudo().write(
                        {'name': name, "email": email.lower(), 'id_database_old': id_database_old,
                         'phone': phone, 'street': street})

                    response_list.append({
                        'status': 'success',
                        'message': f'Contact with VAT {vat_number} updated successfully.',
                        'contact_id': existing_partner.id
                    })

                    invoice = request.env['json.storage'].sudo().search([
                        ('client_invoice', '=', vat_number),
                        ('id_database_old_invoice_client', '=', -1),
                    ], limit=1)

                    if invoice:
                        # Cargar los datos JSON
                        obj_query = json.loads(invoice.json_data)

                        # Actualizar idcustomer a 3
                        if obj_query and 'factura' in obj_query[
                            0] and 'ccust' in obj_query[0]['factura']:
                            obj_query[0]['factura']['idcustomer'] = int(
                                id_database_old)

                        # Guardar los datos actualizados
                        invoice.sudo().write(
                            {'json_data': json.dumps(obj_query)})
                        invoice.sudo().write({
                            'id_database_old_invoice_client': int(
                                id_database_old)})


                else:
                    # Si el contacto no existe, crear uno nuevo
                    partner = request.env['res.partner'].sudo().create({
                        'name': name,
                        'email': email.lower() if email else "@",
                        'phone': phone,
                        'street': street,
                        'city': city,
                        'vat': vat_number,
                        'l10n_latam_identification_type_id': vat_identifier,
                        'id_database_old': id_database_old,
                    })

                    response_list.append({
                        'status': 'success',
                        'message': 'Contact created successfully.',
                        'contact_id': partner.id
                    })

            return Response(
                json.dumps({'status': 'error', 'message': 'Contact created successfully.', }),
                status=201, content_type='application/json')

        except Exception as e:
            return Response(json.dumps({'status': 'error', 'message': str(e)}), status=500,
                            content_type='application/json')

    @http.route('/api/identification_types', auth='public',
                methods=['GET'],
                csrf=False)
    def get_identification_types(self):
        try:
            # Buscar todos los tipos de identificación
            identification_types = request.env[
                'l10n_latam.identification.type'].sudo().search([])

            # Crear una lista con los nombres de los tipos de identificación
            result = []
            for identification_type in identification_types:
                result.append({
                    'id': identification_type.id,
                    'name': identification_type.name,
                })

            # Devolver la respuesta como JSON
            return request.make_response(json.dumps({
                'status': 'success',
                'identification_types': result
            }), headers=[('Content-Type', 'application/json')])

        except Exception as e:
            return request.make_response(json.dumps({
                'status': 'error',
                'message': str(e)
            }), headers=[('Content-Type', 'application/json')])

    # API GET NEW PARTNER
    @http.route('/api/partners/old', type='http', auth='public',
                methods=['GET'], csrf=False)
    def get_old_partners(self, **kwargs):
        # Obtener los tipos de identificación válidos
        valid_types = request.env[
            'l10n_latam.identification.type'].sudo().search([
            ('name', 'in', ['Cédula', 'RUC', 'Pasaporte'])
        ])

        # Buscar los clientes con filtros combinados
        partners = request.env['res.partner'].sudo().search([
            ('id_database_old', '=', '-1'),
            ('supplier_rank', '=', 0),
            ('l10n_latam_identification_type_id', 'in', valid_types.ids),
            ('vat', '!=', False), ('type', '=', 'contact')
        ])

        result = []
        for partner in partners:
            result.append({
                'id': partner.id,
                'name': partner.name,
                'email': partner.email or "@",
                'vat': partner.vat,
                'id_database_old': partner.id_database_old,
                'birth_date': partner.birth_date.strftime(
                    '%Y-%m-%d') if partner.birth_date else fields.date.today().strftime('%Y-%m-%d'),
                'street': partner.street,
                # 'street2': partner.street2,
                'city': partner.city or "LOJA",
                'phone': partner.phone or '0999999999',
                # 'zip': partner.zip,
                # 'state': partner.state_id.name if partner.state_id else None,
                # 'country': partner.country_id.name if partner.country_id else None,
                'identification_type': partner.l10n_latam_identification_type_id.name if partner.l10n_latam_identification_type_id else None,
            })

        return Response(
            json.dumps({'partners': result}, ensure_ascii=False),
            content_type='application/json',
            status=200
        )


a = {'iduser': '724', 'date': '20251024', 'l_close': 1, 'l_sync': 0, 'l_file': 0, 'l_void': 0,
     't_init': '2025-10-24 17:01:47', 't_close': '2025-10-24 17:14:57',
     'cash_register_total_entry_encoding': 35.550000000000004, 'b100': 0, 'b50': 0, 'b20': 4,
     'b10': 2, 'b5': 2, 'b1': 0, 'btotal': 110, 'm100': 0, 'm50': 1, 'm25': 0, 'm10': 0, 'm5': 1,
     'm1': 0, 'mtotal': 0.55, 'total_ef': 10.549999999999997}
