# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)



class PosOfflineSyncController(http.Controller):
    """
    Controladores API para sincronización POS Offline.

    Estos endpoints son consumidos tanto por el POS offline (para subir datos)
    como por el servidor cloud (para enviar actualizaciones).
    """

    # ==================== ENDPOINTS DE HEALTH CHECK ====================

    @http.route('/pos_offline_sync/ping', type='http', auth='public',
                methods=['GET', 'POST'], csrf=False, cors='*')
    def ping(self, **kwargs):
        """
        Health check para verificar conectividad.

        Returns:
            dict: Estado del servidor
        """
        data = {
            'success': True,
            'message': 'POS Offline Sync está operativo',
            'timestamp': fields.Datetime.now().isoformat(),
            'version': '17.0.1.0.0',
        }
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')]
        )

    @http.route('/pos_offline_sync/status', type='json', auth='user',
                methods=['POST'], csrf=False)
    def get_sync_status(self, warehouse_id=None, **kwargs):
        """
        Obtiene el estado de sincronización de un almacén.

        Args:
            warehouse_id: ID del almacén

        Returns:
            dict: Estado de sincronización
        """
        if not warehouse_id:
            return {'success': False, 'error': 'warehouse_id es requerido'}

        config = request.env['pos.sync.config'].sudo().get_config_for_warehouse(
            warehouse_id
        )

        if not config:
            return {
                'success': False,
                'error': 'No hay configuración de sincronización para este almacén'
            }

        pending_count = request.env['pos.sync.queue'].sudo().search_count([
            ('warehouse_id', '=', warehouse_id),
            ('state', 'in', ['pending', 'error']),
        ])

        return {
            'success': True,
            'config': {
                'id': config.id,
                'name': config.name,
                'operation_mode': config.operation_mode,
                'sync_status': config.sync_status,
                'last_sync_date': config.last_sync_date.isoformat() if config.last_sync_date else None,
            },
            'pending_count': pending_count,
            'total_synced_orders': config.total_synced_orders,
        }

    # ==================== ENDPOINTS DE PUSH (SUBIDA) ====================

    @http.route('/pos_offline_sync/push', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def push_records(self, **kwargs):
        """
        Recibe registros desde un POS offline para sincronizar.

        Payload esperado:
        {
            "model": "pos.order",
            "warehouse_id": 1,
            "warehouse_name": "Sucursal Principal",
            "records": [
                {
                    "queue_id": 123,
                    "local_id": 456,
                    "operation": "create",
                    "data": {...}
                }
            ]
        }

        Returns:
            dict: Resultado de la sincronización
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            # Validar autenticación API
            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            model_name = data.get('model')
            warehouse_id_offline = data.get('warehouse_id')
            warehouse_name = data.get('warehouse_name')
            records = data.get('records', [])

            if not model_name or not (warehouse_id_offline or warehouse_name):
                return self._json_response({
                    'success': False,
                    'error': 'model y warehouse_id o warehouse_name son requeridos'
                })

            # CRÍTICO: Resolver warehouse del ONLINE usando el nombre
            # Los IDs de warehouse son diferentes entre OFFLINE y ONLINE
            warehouse_id = self._resolve_warehouse_id(warehouse_id_offline, warehouse_name)

            if not warehouse_id:
                return self._json_response({
                    'success': False,
                    'error': f'No se encontró el almacén "{warehouse_name}" en el servidor principal'
                })

            _logger.info(f'Warehouse resuelto: offline_id={warehouse_id_offline}, name={warehouse_name}, online_id={warehouse_id}')

            results = []
            for record_data in records:
                result = self._process_push_record(model_name, record_data, warehouse_id)
                results.append(result)

            success_count = len([r for r in results if r.get('success')])

            # Registrar en log
            self._log_sync_operation(
                warehouse_id, 'push',
                f'Recibidos {len(records)} registros de {model_name}. '
                f'Exitosos: {success_count}'
            )

            return self._json_response({
                'success': True,
                'results': results,
                'summary': {
                    'total': len(records),
                    'successful': success_count,
                    'failed': len(records) - success_count,
                }
            })

        except Exception as e:
            _logger.error(f'Error en push: {str(e)}')
            return self._json_response({'success': False, 'error': str(e)})

    def _resolve_warehouse_id(self, offline_warehouse_id, warehouse_name):
        """
        Resuelve el warehouse_id del servidor ONLINE basándose en el nombre.

        CRÍTICO: Los IDs de warehouse son diferentes entre OFFLINE y ONLINE
        porque son bases de datos independientes. Se debe usar el NOMBRE
        para encontrar el warehouse correcto en el servidor principal.

        Args:
            offline_warehouse_id: ID del warehouse en el OFFLINE (para fallback)
            warehouse_name: Nombre del warehouse (prioritario)

        Returns:
            int: ID del warehouse en el servidor ONLINE, o None si no se encuentra
        """
        Warehouse = request.env['stock.warehouse'].sudo()

        # PRIORIDAD 1: Buscar por nombre exacto
        if warehouse_name:
            warehouse = Warehouse.search([
                ('name', '=', warehouse_name)
            ], limit=1)
            if warehouse:
                _logger.info(f'Warehouse encontrado por nombre: {warehouse.name} (ID: {warehouse.id})')
                return warehouse.id

            # Intentar búsqueda parcial (por si hay diferencias menores)
            warehouse = Warehouse.search([
                ('name', 'ilike', warehouse_name)
            ], limit=1)
            if warehouse:
                _logger.info(f'Warehouse encontrado por nombre parcial: {warehouse.name} (ID: {warehouse.id})')
                return warehouse.id

        # PRIORIDAD 2: Buscar por id_database_old (si está configurado)
        if offline_warehouse_id:
            warehouse = Warehouse.search([
                ('id_database_old', '=', str(offline_warehouse_id))
            ], limit=1)
            if warehouse:
                _logger.info(f'Warehouse encontrado por id_database_old: {warehouse.name} (ID: {warehouse.id})')
                return warehouse.id

        # PRIORIDAD 3: Buscar por cloud_sync_id
        if offline_warehouse_id:
            warehouse = Warehouse.search([
                ('cloud_sync_id', '=', offline_warehouse_id)
            ], limit=1)
            if warehouse:
                _logger.info(f'Warehouse encontrado por cloud_sync_id: {warehouse.name} (ID: {warehouse.id})')
                return warehouse.id

        # FALLBACK: Si el ID existe directamente (caso donde OFFLINE y ONLINE comparten IDs)
        if offline_warehouse_id:
            warehouse = Warehouse.browse(offline_warehouse_id)
            if warehouse.exists():
                _logger.warning(f'Warehouse usando ID directo (fallback): {warehouse.name} (ID: {warehouse.id})')
                return warehouse.id

        _logger.error(f'No se encontró warehouse: name={warehouse_name}, offline_id={offline_warehouse_id}')
        return None

    def _process_push_record(self, model_name, record_data, warehouse_id=None):
        """
        Procesa un registro individual de push.

        Args:
            model_name: Nombre del modelo
            record_data: Datos del registro
            warehouse_id: ID del almacén (necesario para pos.order)

        Returns:
            dict: Resultado del procesamiento
        """
        queue_id = record_data.get('queue_id')
        local_id = record_data.get('local_id')
        operation = record_data.get('operation', 'create')
        data = record_data.get('data', {})

        try:
            # Manejo especial para pos.order
            if model_name == 'pos.order' and operation == 'create':
                return self._process_pos_order(queue_id, local_id, data, warehouse_id)

            # Manejo especial para res.partner
            if model_name == 'res.partner':
                return self._process_res_partner(queue_id, local_id, data, operation)

            # Manejo especial para institution
            if model_name == 'institution':
                return self._process_institution(queue_id, local_id, data, operation)

            # Manejo especial para institution.client
            if model_name == 'institution.client':
                return self._process_institution_client(queue_id, local_id, data, operation)

            Model = request.env[model_name].sudo()
            cloud_id = None

            if operation == 'create':
                # Crear nuevo registro
                new_record = Model.create(self._prepare_create_vals(model_name, data))
                cloud_id = new_record.id

            elif operation == 'write':
                # Actualizar registro existente
                existing = self._find_existing_record(Model, data)
                if existing:
                    existing.write(self._prepare_write_vals(model_name, data))
                    cloud_id = existing.id
                else:
                    # Si no existe, crear
                    new_record = Model.create(self._prepare_create_vals(model_name, data))
                    cloud_id = new_record.id

            elif operation == 'unlink':
                # Eliminar registro
                existing = self._find_existing_record(Model, data)
                if existing:
                    cloud_id = existing.id
                    existing.unlink()

            return {
                'success': True,
                'queue_id': queue_id,
                'local_id': local_id,
                'cloud_id': cloud_id,
            }

        except Exception as e:
            _logger.error(f'Error procesando {model_name}#{local_id}: {str(e)}')
            return {
                'success': False,
                'queue_id': queue_id,
                'local_id': local_id,
                'error': str(e),
            }

    def _update_existing_order_payments(self, order, data):
        """
        Actualiza los pagos de una orden existente con los datos de cheque/tarjeta/transferencia.

        Esta función se llama cuando una orden ya existe en el servidor principal
        pero los pagos pueden no tener los campos adicionales de cheque, tarjeta o transferencia.

        Args:
            order: pos.order existente
            data: Datos de sincronización que incluyen check_info_json, card_info_json, etc.
        """
        try:
            import json as json_lib

            # Actualizar campos de transferencia en la orden
            order_update_vals = {}
            if data.get('payment_transfer_number') and not order.payment_transfer_number:
                order_update_vals['payment_transfer_number'] = data.get('payment_transfer_number')
            if data.get('payment_bank_name') and not order.payment_bank_name:
                order_update_vals['payment_bank_name'] = data.get('payment_bank_name')
            if data.get('payment_transaction_id') and not order.payment_transaction_id:
                order_update_vals['payment_transaction_id'] = data.get('payment_transaction_id')
            if data.get('orderer_identification') and not order.orderer_identification:
                order_update_vals['orderer_identification'] = data.get('orderer_identification')
            if data.get('check_info_json') and not order.check_info_json:
                order_update_vals['check_info_json'] = data.get('check_info_json')
            if data.get('card_info_json') and not order.card_info_json:
                order_update_vals['card_info_json'] = data.get('card_info_json')

            if order_update_vals:
                order.with_context(skip_sync_queue=True).write(order_update_vals)
                _logger.info(f'Orden {order.name} actualizada con campos de transferencia: {list(order_update_vals.keys())}')

            # Parsear check_info_json
            check_info_list = []
            if data.get('check_info_json'):
                try:
                    check_info_list = json_lib.loads(data.get('check_info_json')) if isinstance(data.get('check_info_json'), str) else data.get('check_info_json')
                    if not isinstance(check_info_list, list):
                        check_info_list = []
                except (json_lib.JSONDecodeError, TypeError):
                    check_info_list = []

            # Parsear card_info_json
            card_info_list = []
            if data.get('card_info_json'):
                try:
                    card_info_list = json_lib.loads(data.get('card_info_json')) if isinstance(data.get('card_info_json'), str) else data.get('card_info_json')
                    if not isinstance(card_info_list, list):
                        card_info_list = []
                except (json_lib.JSONDecodeError, TypeError):
                    card_info_list = []

            if not check_info_list and not card_info_list:
                _logger.info(f'No hay datos de cheque/tarjeta para actualizar en orden {order.name}')
                return

            _logger.info(f'Actualizando pagos de orden existente {order.name}: check_info={check_info_list}, card_info={card_info_list}')

            # Aplicar datos de cheque a los pagos
            check_info_dict = {}
            for payment in order.payment_ids:
                if payment.payment_method_id.allow_check_info:
                    for check_info in check_info_list:
                        if payment.id not in check_info_dict and check_info not in check_info_dict.values():
                            check_info_dict[payment.id] = check_info
                            break

            for payment_id, check_info in check_info_dict.items():
                payment = request.env['pos.payment'].sudo().browse(payment_id)
                if payment.exists():
                    update_vals = {}
                    # Solo actualizar si el pago no tiene el campo ya establecido
                    if check_info.get('check_number') and not payment.check_number:
                        update_vals['check_number'] = check_info.get('check_number')
                    if check_info.get('check_owner') and not payment.check_owner:
                        update_vals['check_owner'] = check_info.get('check_owner')
                    if check_info.get('check_bank_account') and not payment.check_bank_account:
                        update_vals['check_bank_account'] = check_info.get('check_bank_account')
                    if check_info.get('bank_id') and not payment.bank_id:
                        update_vals['bank_id'] = check_info.get('bank_id')
                    if update_vals:
                        payment.write(update_vals)
                        _logger.info(f'Pago {payment.id} actualizado con datos de cheque: {update_vals}')

            # Aplicar datos de tarjeta a los pagos
            card_info_dict = {}
            for payment in order.payment_ids:
                if payment.payment_method_id.allow_check_info:
                    for card_info in card_info_list:
                        if payment.id not in card_info_dict and card_info not in card_info_dict.values():
                            card_info_dict[payment.id] = card_info
                            break

            for payment_id, card_info in card_info_dict.items():
                payment = request.env['pos.payment'].sudo().browse(payment_id)
                if payment.exists():
                    update_vals = {}
                    if card_info.get('number_voucher') and not payment.number_voucher:
                        update_vals['number_voucher'] = card_info.get('number_voucher')
                    if card_info.get('type_card') and not payment.type_card:
                        update_vals['type_card'] = card_info.get('type_card')
                    if card_info.get('number_lote') and not payment.number_lote:
                        update_vals['number_lote'] = card_info.get('number_lote')
                    if card_info.get('holder_card') and not payment.holder_card:
                        update_vals['holder_card'] = card_info.get('holder_card')
                    if card_info.get('bin_tc') and not payment.bin_tc:
                        update_vals['bin_tc'] = card_info.get('bin_tc')
                    if update_vals:
                        payment.write(update_vals)
                        _logger.info(f'Pago {payment.id} actualizado con datos de tarjeta: {update_vals}')

        except Exception as e:
            _logger.error(f'Error actualizando pagos de orden existente {order.name}: {e}', exc_info=True)

    def _process_pos_order(self, queue_id, local_id, data, warehouse_id):
        """
        Procesa una orden POS completa desde el sistema offline.

        FLUJO COMPLETO:
        1. Crea la orden con líneas
        2. Crea los pagos (pos.payment)
        3. Marca la orden como pagada (action_pos_order_paid)
        4. Si hay datos de factura, crea la factura con la MISMA clave de acceso
        5. Postea la factura (genera asientos contables)
        6. Envía al SRI para autorización (automático al postear)

        Args:
            queue_id: ID en la cola de sincronización
            local_id: ID local de la orden
            data: Datos de la orden (incluyendo invoice_data con clave de acceso)
            warehouse_id: ID del almacén

        Returns:
            dict: Resultado del procesamiento
        """
        try:
            pos_reference = data.get('pos_reference')
            order_name = data.get('name')
            session_name = data.get('session_name')
            order_state = data.get('state', 'draft')
            invoice_data = data.get('invoice_data')
            json_storage_data = data.get('json_storage_data')

            _logger.info(
                f'Procesando orden POS COMPLETA: name={order_name}, '
                f'pos_reference={pos_reference}, session={session_name}, '
                f'state={order_state}, tiene_factura={bool(invoice_data)}, '
                f'tiene_json_storage={bool(json_storage_data)}'
            )

            # Verificar si la orden ya existe por pos_reference
            if pos_reference:
                existing = request.env['pos.order'].sudo().search([
                    ('pos_reference', '=', pos_reference)
                ], limit=1)

                if existing:
                    # Verificar que la orden existente tiene datos completos
                    has_payments = len(existing.payment_ids) > 0
                    has_lines = len(existing.lines) > 0
                    has_invoice = bool(existing.account_move)
                    needs_invoice = bool(invoice_data)
                    is_invoiced = existing.state == 'invoiced'

                    _logger.info(
                        f'Orden encontrada: ID={existing.id}, name={existing.name}, '
                        f'pos_reference={existing.pos_reference}, state={existing.state}, '
                        f'pagos={len(existing.payment_ids)}, lineas={len(existing.lines)}, '
                        f'factura={existing.account_move.name if existing.account_move else "N/A"}, '
                        f'necesita_factura={needs_invoice}'
                    )

                    # ACTUALIZAR CAMPOS DE PAGO PARA ÓRDENES EXISTENTES
                    # Aunque la orden exista, los pagos pueden no tener los campos de cheque/tarjeta
                    self._update_existing_order_payments(existing, data)

                    # CASO 1: Si ya tiene factura, está completa
                    # Solo necesitamos asegurar que el estado sea 'invoiced'
                    if has_invoice:
                        if not is_invoiced:
                            _logger.info(
                                f'Orden {pos_reference} tiene factura pero estado={existing.state}. '
                                f'Actualizando a invoiced...'
                            )
                            existing.with_context(skip_sync_queue=True).write({'state': 'invoiced'})
                        _logger.info(
                            f'Orden {pos_reference} ya está completa con factura: '
                            f'{existing.account_move.name}'
                        )
                        return {
                            'success': True,
                            'queue_id': queue_id,
                            'local_id': local_id,
                            'cloud_id': existing.id,
                            'message': 'Orden ya existe con factura',
                        }

                    # CASO 2: Tiene pagos y líneas pero necesita factura
                    if has_payments and has_lines and needs_invoice:
                        _logger.info(
                            f'Orden {pos_reference} existe con pagos/líneas pero sin factura. '
                            f'Intentando crear factura...'
                        )
                        try:
                            sync_manager = request.env['pos.sync.manager'].sudo()
                            success = sync_manager._create_invoice_from_offline(existing, invoice_data)
                            if success:
                                _logger.info(f'Factura creada para orden existente {pos_reference}')
                        except Exception as e:
                            _logger.error(f'Error creando factura para orden existente: {e}')
                        return {
                            'success': True,
                            'queue_id': queue_id,
                            'local_id': local_id,
                            'cloud_id': existing.id,
                            'message': 'Orden actualizada con factura',
                        }

                    # CASO 3: Tiene pagos y líneas pero no necesita factura
                    if has_payments and has_lines:
                        _logger.info(f'Orden {pos_reference} ya está completa (sin factura requerida)')
                        return {
                            'success': True,
                            'queue_id': queue_id,
                            'local_id': local_id,
                            'cloud_id': existing.id,
                            'message': 'Orden ya existe',
                        }

                    # CASO 4: Orden incompleta - retornar existente para evitar duplicados
                    _logger.warning(
                        f'Orden {pos_reference} existe pero incompleta '
                        f'(pagos={has_payments}, lineas={has_lines}). '
                        f'Retornando existente para evitar duplicados.'
                    )
                    return {
                        'success': True,
                        'queue_id': queue_id,
                        'local_id': local_id,
                        'cloud_id': existing.id,
                        'message': 'Orden ya existe (incompleta)',
                    }

            # Buscar o crear sesión para la orden
            session = self._find_or_create_session_for_sync(data, warehouse_id)

            if not session:
                return {
                    'success': False,
                    'queue_id': queue_id,
                    'local_id': local_id,
                    'error': 'No se pudo encontrar o crear una sesión POS para sincronización',
                }

            _logger.info(f'Usando sesión: {session.name} (ID: {session.id})')

            # Buscar/crear partner
            partner = None
            if data.get('partner_vat'):
                partner = request.env['res.partner'].sudo().search([
                    ('vat', '=', data['partner_vat'])
                ], limit=1)
            elif data.get('partner_id'):
                # Intentar buscar por id_database_old
                partner = request.env['res.partner'].sudo().search([
                    ('id_database_old', '=', str(data['partner_id']))
                ], limit=1)

            # Si aún no hay partner, buscar por cloud_sync_id
            if not partner and data.get('partner_cloud_sync_id'):
                partner = request.env['res.partner'].sudo().search([
                    ('cloud_sync_id', '=', data['partner_cloud_sync_id'])
                ], limit=1)

            # Preparar líneas de la orden
            lines = []
            for line_data in data.get('lines', []):
                product = None

                # Buscar producto por barcode primero
                if line_data.get('product_barcode'):
                    product = request.env['product.product'].sudo().search([
                        ('barcode', '=', line_data['product_barcode'])
                    ], limit=1)

                # Si no se encuentra, buscar por id_database_old
                if not product and line_data.get('product_id'):
                    product = request.env['product.product'].sudo().search([
                        ('id_database_old', '=', str(line_data['product_id']))
                    ], limit=1)

                # Si aún no se encuentra, buscar por ID directo
                if not product and line_data.get('product_id'):
                    product = request.env['product.product'].sudo().browse(
                        line_data['product_id']
                    )
                    if not product.exists():
                        product = None

                if product:
                    line_vals = {
                        'product_id': product.id,
                        'full_product_name': line_data.get('product_name', product.name),
                        'qty': line_data.get('qty', 1),
                        'price_unit': line_data.get('price_unit', product.lst_price),
                        'price_subtotal': line_data.get('price_subtotal', 0),
                        'price_subtotal_incl': line_data.get('price_subtotal_incl', 0),
                        'discount': line_data.get('discount', 0),
                    }
                    # Agregar tax_ids si existen
                    if line_data.get('tax_ids'):
                        line_vals['tax_ids'] = [(6, 0, line_data['tax_ids'])]
                    lines.append((0, 0, line_vals))
                else:
                    _logger.warning(
                        f"Producto no encontrado: barcode={line_data.get('product_barcode')}, "
                        f"id={line_data.get('product_id')}"
                    )

            if not lines:
                return {
                    'success': False,
                    'queue_id': queue_id,
                    'local_id': local_id,
                    'error': 'No se pudieron procesar las líneas de la orden',
                }

            # Generar pos_reference, name y sequence_number
            # IMPORTANTE: Buscar el último sequence_number de TODO el config_id (punto de venta)
            # no solo de la sesión, para mantener la secuencia global del POS
            last_seq = request.env['pos.order'].sudo().search(
                [('config_id', '=', session.config_id.id)],
                order='sequence_number desc',
                limit=1
            ).sequence_number or 0
            next_seq = last_seq + 1

            # Formato: Orden {session_id(5)}-{config_id(3)}-{sequence(4)}
            comp_seq = str(session.id).zfill(5)
            conf_seq = str(session.config_id.id).zfill(3)
            ord_seq = str(next_seq).zfill(4)
            generated_pos_reference = f"Orden {comp_seq}-{conf_seq}-{ord_seq}"
            generated_name = f"{session.config_id.name}/{ord_seq}"

            # Crear la orden en estado draft
            order_vals = {
                'session_id': session.id,
                'partner_id': partner.id if partner else False,
                'lines': lines,
                'amount_total': data.get('amount_total', 0),
                'amount_paid': data.get('amount_paid', 0),
                'amount_return': data.get('amount_return', 0),
                'amount_tax': data.get('amount_tax', 0),
                'note': data.get('note') if data.get('note') else False,
                'state': 'draft',
                # Campos generados basados en sesión PRINCIPAL
                'name': generated_name,
                'pos_reference': generated_pos_reference,
                'sequence_number': next_seq,
            }

            # Agregar posición fiscal si existe
            if data.get('fiscal_position_id'):
                fiscal_position = request.env['account.fiscal.position'].sudo().search([
                    '|',
                    ('id', '=', data.get('fiscal_position_id')),
                    ('name', '=', data.get('fiscal_position_name', ''))
                ], limit=1)
                if fiscal_position:
                    order_vals['fiscal_position_id'] = fiscal_position.id

            # Agregar lista de precios si existe
            if data.get('pricelist_id'):
                pricelist = request.env['product.pricelist'].sudo().browse(data['pricelist_id'])
                if pricelist.exists():
                    order_vals['pricelist_id'] = pricelist.id

            # Agregar empleado si existe
            if data.get('employee_name'):
                employee = request.env['hr.employee'].sudo().search([
                    ('name', '=', data['employee_name'])
                ], limit=1)
                if employee:
                    order_vals['employee_id'] = employee.id
            elif data.get('employee_id'):
                employee = request.env['hr.employee'].sudo().browse(data['employee_id'])
                if employee.exists():
                    order_vals['employee_id'] = employee.id

            # Agregar campos de transferencia bancaria
            if data.get('payment_transfer_number'):
                order_vals['payment_transfer_number'] = data.get('payment_transfer_number')
            if data.get('payment_bank_name'):
                order_vals['payment_bank_name'] = data.get('payment_bank_name')
            if data.get('payment_transaction_id'):
                order_vals['payment_transaction_id'] = data.get('payment_transaction_id')
            if data.get('orderer_identification'):
                order_vals['orderer_identification'] = data.get('orderer_identification')

            # Agregar campos JSON de cheque y tarjeta
            if data.get('check_info_json'):
                order_vals['check_info_json'] = data.get('check_info_json')
            if data.get('card_info_json'):
                order_vals['card_info_json'] = data.get('card_info_json')

            # Crear orden con contexto para evitar que se agregue a cola de sync
            order = request.env['pos.order'].sudo().with_context(
                skip_sync_queue=True
            ).create(order_vals)

            _logger.info(
                f'Orden creada en PRINCIPAL: name={order.name}, pos_reference={order.pos_reference}, '
                f'config={order.config_id.name}, employee={order.employee_id.name if order.employee_id else "N/A"} '
                f'(OFFLINE ref: {pos_reference})'
            )

            # ==================== PASO 2: SINCRONIZAR DATOS DE PAGOS ====================
            # IMPORTANTE: Los pagos (pos.payment) se crean automáticamente al crear la orden.
            # Este paso SOLO actualiza los campos de cheque/tarjeta en los pagos existentes.
            payments_data = data.get('payments', [])
            _logger.info(f'Sincronizando datos de {len(payments_data)} pagos para orden {order.name}')

            if order.payment_ids:
                _logger.info(f'Orden {order.name} tiene {len(order.payment_ids)} pagos existentes. Sincronizando campos...')
            else:
                _logger.warning(f'Orden {order.name} no tiene pagos. Los pagos deberían haberse creado automáticamente.')

            # ==================== PASO 2.5: ACTUALIZAR PAGOS CON CHECK_INFO_JSON Y CARD_INFO_JSON ====================
            # Los datos de cheque/tarjeta pueden estar en los campos JSON de la orden
            # y deben aplicarse a los pagos correspondientes
            try:
                import json as json_lib
                check_info_list = []
                card_info_list = []

                # Parsear check_info_json si existe
                if data.get('check_info_json'):
                    try:
                        check_info_list = json_lib.loads(data.get('check_info_json')) if isinstance(data.get('check_info_json'), str) else data.get('check_info_json')
                        if not isinstance(check_info_list, list):
                            check_info_list = []
                    except (json_lib.JSONDecodeError, TypeError):
                        check_info_list = []

                # Parsear card_info_json si existe
                if data.get('card_info_json'):
                    try:
                        card_info_list = json_lib.loads(data.get('card_info_json')) if isinstance(data.get('card_info_json'), str) else data.get('card_info_json')
                        if not isinstance(card_info_list, list):
                            card_info_list = []
                    except (json_lib.JSONDecodeError, TypeError):
                        card_info_list = []

                _logger.info(f'check_info_json: {check_info_list}, card_info_json: {card_info_list}')

                # Aplicar datos de cheque a los pagos correspondientes
                check_info_dict = {}
                for payment in order.payment_ids:
                    if payment.payment_method_id.allow_check_info:
                        for check_info in check_info_list:
                            if payment.id not in check_info_dict and check_info not in check_info_dict.values():
                                check_info_dict[payment.id] = check_info
                                break

                for payment_id, check_info in check_info_dict.items():
                    payment = request.env['pos.payment'].sudo().browse(payment_id)
                    if payment.exists():
                        update_vals = {}
                        if check_info.get('check_number'):
                            update_vals['check_number'] = check_info.get('check_number')
                        if check_info.get('check_owner'):
                            update_vals['check_owner'] = check_info.get('check_owner')
                        if check_info.get('check_bank_account'):
                            update_vals['check_bank_account'] = check_info.get('check_bank_account')
                        if check_info.get('bank_id'):
                            update_vals['bank_id'] = check_info.get('bank_id')
                        if update_vals:
                            payment.write(update_vals)
                            _logger.info(f'Pago {payment.id} actualizado con datos de cheque: {update_vals}')

                # Aplicar datos de tarjeta a los pagos correspondientes
                card_info_dict = {}
                for payment in order.payment_ids:
                    if payment.payment_method_id.allow_check_info:
                        for card_info in card_info_list:
                            if payment.id not in card_info_dict and card_info not in card_info_dict.values():
                                card_info_dict[payment.id] = card_info
                                break

                for payment_id, card_info in card_info_dict.items():
                    payment = request.env['pos.payment'].sudo().browse(payment_id)
                    if payment.exists():
                        update_vals = {}
                        if card_info.get('number_voucher'):
                            update_vals['number_voucher'] = card_info.get('number_voucher')
                        if card_info.get('type_card'):
                            update_vals['type_card'] = card_info.get('type_card')
                        if card_info.get('number_lote'):
                            update_vals['number_lote'] = card_info.get('number_lote')
                        if card_info.get('holder_card'):
                            update_vals['holder_card'] = card_info.get('holder_card')
                        if card_info.get('bin_tc'):
                            update_vals['bin_tc'] = card_info.get('bin_tc')
                        if update_vals:
                            payment.write(update_vals)
                            _logger.info(f'Pago {payment.id} actualizado con datos de tarjeta: {update_vals}')

            except Exception as e:
                _logger.error(f'Error actualizando pagos con check_info_json/card_info_json: {e}', exc_info=True)

            # ==================== PASO 3: MARCAR COMO PAGADA ====================
            if order.payment_ids and order_state in ['paid', 'done', 'invoiced']:
                try:
                    order.with_context(skip_sync_queue=True).action_pos_order_paid()
                    _logger.info(f'Orden {order.name} marcada como PAGADA')
                except Exception as e:
                    _logger.warning(f'Error al marcar orden como pagada: {e}')

            # ==================== PASO 4: CREAR FACTURA CON CLAVE DE ACCESO ====================
            invoice_created = False
            invoice_name = None

            if partner and invoice_data and invoice_data.get('l10n_ec_authorization_number'):
                try:
                    invoice_created = self._create_invoice_with_access_key(
                        order, invoice_data, partner
                    )
                    if order.account_move:
                        invoice_name = order.account_move.name
                        _logger.info(f'Factura creada: {invoice_name}')
                except Exception as e:
                    _logger.error(f'Error al crear factura con clave de acceso: {e}', exc_info=True)
            elif partner and order_state == 'invoiced':
                # Fallback: crear factura normal si no hay clave de acceso
                try:
                    order.with_context(skip_sync_queue=True).action_pos_order_invoice()
                    if order.account_move:
                        invoice_created = True
                        invoice_name = order.account_move.name
                        _logger.info(f'Factura normal creada: {invoice_name}')
                except Exception as e:
                    _logger.error(f'Error al crear factura normal: {e}', exc_info=True)

            # ==================== PASO 5: CREAR JSON.STORAGE ====================
            json_storage_created = False
            json_storage_id = None

            if json_storage_data:
                try:
                    json_storage_record = self._create_json_storage_for_order(
                        order, json_storage_data, session
                    )
                    if json_storage_record:
                        json_storage_created = True
                        json_storage_id = json_storage_record.id
                        _logger.info(f'json.storage creado: ID={json_storage_id}')
                except Exception as e:
                    _logger.error(f'Error al crear json.storage: {e}', exc_info=True)

            _logger.info(
                f'Orden POS COMPLETA sincronizada: {order.name} '
                f'(estado: {order.state}, pagos: {len(order.payment_ids)}, '
                f'factura: {invoice_name or "N/A"}, json_storage: {json_storage_id or "N/A"})'
            )

            return {
                'success': True,
                'queue_id': queue_id,
                'local_id': local_id,
                'cloud_id': order.id,
                'order_name': order.name,
                'order_state': order.state,
                'pos_reference': order.pos_reference,
                'session_name': session.name,
                'payments_count': len(order.payment_ids),
                'invoice_created': invoice_created,
                'invoice_name': invoice_name,
                'json_storage_created': json_storage_created,
                'json_storage_id': json_storage_id,
            }

        except Exception as e:
            _logger.error(f'Error procesando pos.order#{local_id}: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return {
                'success': False,
                'queue_id': queue_id,
                'local_id': local_id,
                'error': str(e),
            }

    def _create_invoice_with_access_key(self, order, invoice_data, partner):
        """
        Crea y POSTEA la factura para una orden sincronizada desde offline.

        FLUJO CORREGIDO (Igual al principal pos_custom_check):
        1. Crea la factura con la MISMA clave de acceso y MISMO NAME del offline
        2. POSTEA la factura (genera asientos contables)
        3. Aplica los pagos usando _apply_invoice_payments
        4. El sistema EDI ENVÍA al SRI para autorización

        CRÍTICO: El NAME de la factura DEBE coincidir con el del OFFLINE porque
        la clave de acceso se genera usando move.name.split('-')[2] en l10n_ec_edi.

        Args:
            order: pos.order
            invoice_data: Diccionario con datos de la factura del offline
            partner: res.partner (cliente)

        Returns:
            bool: True si la factura se creó correctamente
        """
        if not order.partner_id:
            _logger.warning(f'No se puede crear factura sin cliente para orden {order.name}')
            return False

        if order.account_move:
            _logger.info(f'Orden {order.name} ya tiene factura: {order.account_move.name}')
            return True

        # Obtener la clave de acceso del offline
        # Esta clave es CRÍTICA - debe ser la misma que se enviará al SRI
        l10n_ec_authorization_number = invoice_data.get('l10n_ec_authorization_number')
        invoice_state_offline = invoice_data.get('invoice_state', 'draft')

        if not l10n_ec_authorization_number:
            _logger.warning(f'No hay clave de acceso para orden {order.name}')
            return False

        invoice = None
        try:
            _logger.info(
                f'[SYNC] Creando factura para orden {order.name} con clave de acceso del offline: '
                f'{l10n_ec_authorization_number[:20]}... (estado offline: {invoice_state_offline})'
            )

            # Preparar valores de factura usando el método estándar de Odoo
            invoice_vals = order._prepare_invoice_vals()

            # CRÍTICO: Establecer la clave de acceso del OFFLINE ANTES de crear
            # Esta clave será preservada y usada para enviar al SRI
            invoice_vals['l10n_ec_authorization_number'] = l10n_ec_authorization_number

            # Establecer método de pago SRI si existe
            if invoice_data.get('l10n_ec_sri_payment_id'):
                invoice_vals['l10n_ec_sri_payment_id'] = invoice_data['l10n_ec_sri_payment_id']

            # Establecer fecha de factura del offline
            if invoice_data.get('invoice_date'):
                try:
                    from datetime import datetime
                    inv_date = invoice_data['invoice_date']
                    if isinstance(inv_date, str):
                        inv_date = datetime.fromisoformat(inv_date).date()
                    invoice_vals['invoice_date'] = inv_date
                except Exception:
                    pass

            # Crear la factura con contexto especial
            # El ONLINE generará SU propio número de factura, pero usará la clave de acceso del OFFLINE
            invoice = request.env['account.move'].sudo().with_context(
                skip_sync_queue=True,
                skip_l10n_ec_authorization=True,  # No regenerar clave - usar la del offline
            ).create(invoice_vals)

            _logger.info(
                f'[SYNC] Factura creada: name={invoice.name}, '
                f'clave_acceso={invoice.l10n_ec_authorization_number[:20] if invoice.l10n_ec_authorization_number else "N/A"}...'
            )

            # Vincular factura a la orden y guardar clave de acceso en key_order
            order.with_context(skip_sync_queue=True).write({
                'account_move': invoice.id,
                'state': 'invoiced',
                'key_order': l10n_ec_authorization_number,  # Clave de acceso de 49 dígitos
            })

            # POSTEAR la factura con contexto especial para preservar nombre y clave
            invoice.sudo().with_company(order.company_id).with_context(
                skip_l10n_ec_authorization=True,
                skip_sync_queue=True,
                skip_invoice_sync=True,
            )._post()

            _logger.info(
                f'[SYNC] Factura {invoice.name} POSTEADA con clave de acceso: '
                f'{l10n_ec_authorization_number[:20]}...'
            )

            # Aplicar pagos usando el método nativo de POS
            # NOTA: En PRINCIPAL la sesión siempre está "abierta" (se crea para sync)
            # No aplica _create_misc_reversal_move porque eso es solo cuando
            # la sesión se cierra en el POS local
            try:
                order._apply_invoice_payments(False)
                _logger.info(f'[SYNC] Pagos aplicados a factura {invoice.name}')
            except Exception as pay_error:
                _logger.warning(f'[SYNC] Error aplicando pagos: {pay_error}')

            _logger.info(
                f'[SYNC] Orden {order.name} facturada completamente - '
                f'Factura: {invoice.name}, payment_state: {invoice.payment_state}'
            )

            return True

        except Exception as e:
            _logger.error(f'[SYNC] Error al crear/postear factura: {e}', exc_info=True)

            # Si la factura se creó pero falló, eliminarla
            if invoice and invoice.state == 'draft':
                try:
                    invoice.unlink()
                except Exception:
                    pass

            # Fallback: intentar crear factura normal
            try:
                _logger.warning(f'[SYNC] Intentando fallback: factura normal para orden {order.name}')
                order.with_context(skip_sync_queue=True).action_pos_order_invoice()
                return order.account_move is not None
            except Exception as e2:
                _logger.error(f'Error en fallback de factura: {e2}')
                return False

    def _process_res_partner(self, queue_id, local_id, data, operation):
        """
        Procesa un partner de forma especial (PUSH: offline -> cloud).

        Este método recibe partners desde el POS offline y los crea/actualiza
        en el servidor cloud. Marca el origen como 'local' ya que provienen
        del sistema offline.

        Args:
            queue_id: ID en la cola de sincronización
            local_id: ID local del partner
            data: Datos del partner
            operation: Tipo de operación ('create', 'write', 'unlink')

        Returns:
            dict: Resultado del procesamiento
        """
        try:
            Partner = request.env['res.partner'].sudo()

            partner_name = data.get('name')
            partner_vat = data.get('vat')
            partner_email = data.get('email')

            _logger.info(f'Procesando partner (PUSH): name={partner_name}, vat={partner_vat}, operation={operation}')

            # Buscar partner existente
            existing = Partner.find_or_create_from_sync(data)

            if operation == 'unlink':
                if existing:
                    cloud_id = existing.id
                    existing.unlink()
                    _logger.info(f'Partner eliminado: ID={cloud_id}')
                    return {
                        'success': True,
                        'queue_id': queue_id,
                        'local_id': local_id,
                        'cloud_id': cloud_id,
                        'message': 'Partner eliminado',
                    }
                else:
                    return {
                        'success': True,
                        'queue_id': queue_id,
                        'local_id': local_id,
                        'message': 'Partner no encontrado para eliminar',
                    }

            # Preparar valores para el partner
            vals = self._prepare_partner_vals_from_push(data)

            if existing:
                # Actualizar existente - usar skip_sync_queue porque es un PUSH desde offline
                existing.with_context(skip_sync_queue=True).write(vals)
                # Marcar como sincronizado desde local (offline)
                existing.with_context(skip_sync_queue=True).write({
                    'sync_state': 'synced',
                    'sync_source': 'local',
                    'last_sync_date': fields.Datetime.now(),
                })
                _logger.info(f'Partner actualizado (PUSH): {existing.name} (ID: {existing.id})')
                return {
                    'success': True,
                    'queue_id': queue_id,
                    'local_id': local_id,
                    'cloud_id': existing.id,
                    'partner_name': existing.name,
                    'message': 'Partner actualizado' if operation == 'write' else 'Partner ya existe',
                }

            # Crear nuevo partner - usar skip_sync_queue porque es un PUSH desde offline
            vals['type'] = vals.get('type', 'contact')
            partner = Partner.with_context(skip_sync_queue=True).create(vals)
            # Marcar como sincronizado desde local (offline)
            partner.with_context(skip_sync_queue=True).write({
                'sync_state': 'synced',
                'sync_source': 'local',
                'last_sync_date': fields.Datetime.now(),
            })

            _logger.info(f'Partner creado (PUSH): {partner.name} (ID: {partner.id})')

            return {
                'success': True,
                'queue_id': queue_id,
                'local_id': local_id,
                'cloud_id': partner.id,
                'partner_name': partner.name,
            }

        except Exception as e:
            _logger.error(f'Error procesando res.partner#{local_id}: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return {
                'success': False,
                'queue_id': queue_id,
                'local_id': local_id,
                'error': str(e),
            }

    def _process_institution(self, queue_id, local_id, data, operation):
        """
        Procesa una institución de crédito/descuento (PUSH: offline -> cloud).

        Args:
            queue_id: ID en la cola de sincronización
            local_id: ID local de la institución
            data: Datos de la institución
            operation: Tipo de operación ('create', 'write', 'unlink')

        Returns:
            dict: Resultado del procesamiento
        """
        try:
            SyncManager = request.env['pos.sync.manager'].sudo()

            _logger.info(
                f'Procesando institution (PUSH): name={data.get("name")}, '
                f'id_institutions={data.get("id_institutions")}, operation={operation}'
            )

            if operation == 'unlink':
                Institution = request.env['institution'].sudo()
                existing = None
                if data.get('id_institutions'):
                    existing = Institution.search([
                        ('id_institutions', '=', data['id_institutions'])
                    ], limit=1)
                if not existing and local_id:
                    existing = Institution.browse(local_id)
                    if not existing.exists():
                        existing = None

                if existing:
                    cloud_id = existing.id
                    existing.unlink()
                    return {
                        'success': True,
                        'queue_id': queue_id,
                        'local_id': local_id,
                        'cloud_id': cloud_id,
                        'message': 'Institution eliminada',
                    }
                return {
                    'success': True,
                    'queue_id': queue_id,
                    'local_id': local_id,
                    'message': 'Institution no encontrada para eliminar',
                }

            # Usar el deserializador del SyncManager
            data['id'] = local_id
            institution = SyncManager.deserialize_institution(data)

            return {
                'success': True,
                'queue_id': queue_id,
                'local_id': local_id,
                'cloud_id': institution.id if institution else None,
                'institution_name': institution.name if institution else None,
            }

        except Exception as e:
            _logger.error(f'Error procesando institution#{local_id}: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return {
                'success': False,
                'queue_id': queue_id,
                'local_id': local_id,
                'error': str(e),
            }

    def _process_institution_client(self, queue_id, local_id, data, operation):
        """
        Procesa una relación institución-cliente (PUSH: offline -> cloud).

        IMPORTANTE: Este método sincroniza los cambios de crédito/saldo (available_amount)
        desde el offline al cloud, asegurando que los consumos de crédito se reflejen.

        Args:
            queue_id: ID en la cola de sincronización
            local_id: ID local del registro
            data: Datos del registro
            operation: Tipo de operación ('create', 'write', 'unlink')

        Returns:
            dict: Resultado del procesamiento
        """
        try:
            SyncManager = request.env['pos.sync.manager'].sudo()

            _logger.info(
                f'=== Procesando institution.client (PUSH) ===\n'
                f'  queue_id={queue_id}, local_id={local_id}\n'
                f'  operation={operation}\n'
                f'  partner_vat={data.get("partner_vat")}\n'
                f'  institution_id_institutions={data.get("institution_id_institutions")}\n'
                f'  available_amount={data.get("available_amount")}\n'
                f'  sale={data.get("sale")}'
            )

            if operation == 'unlink':
                InstitutionClient = request.env['institution.client'].sudo()
                existing = None

                # Buscar por institution + partner
                if data.get('partner_vat') and data.get('institution_id_institutions'):
                    partner = request.env['res.partner'].sudo().search([
                        ('vat', '=', data['partner_vat'])
                    ], limit=1)
                    institution = request.env['institution'].sudo().search([
                        ('id_institutions', '=', data['institution_id_institutions'])
                    ], limit=1)
                    if partner and institution:
                        existing = InstitutionClient.search([
                            ('partner_id', '=', partner.id),
                            ('institution_id', '=', institution.id)
                        ], limit=1)

                if not existing and local_id:
                    existing = InstitutionClient.browse(local_id)
                    if not existing.exists():
                        existing = None

                if existing:
                    cloud_id = existing.id
                    existing.unlink()
                    return {
                        'success': True,
                        'queue_id': queue_id,
                        'local_id': local_id,
                        'cloud_id': cloud_id,
                        'message': 'institution.client eliminado',
                    }
                return {
                    'success': True,
                    'queue_id': queue_id,
                    'local_id': local_id,
                    'message': 'institution.client no encontrado para eliminar',
                }

            # Usar el deserializador del SyncManager
            data['id'] = local_id
            inst_client = SyncManager.deserialize_institution_client(data)

            if inst_client:
                _logger.info(
                    f'=== institution.client PROCESADO (PUSH) ===\n'
                    f'  cloud_id={inst_client.id}\n'
                    f'  partner={inst_client.partner_id.name}\n'
                    f'  institution={inst_client.institution_id.name}\n'
                    f'  available_amount={inst_client.available_amount}\n'
                    f'  sale={inst_client.sale}'
                )
                return {
                    'success': True,
                    'queue_id': queue_id,
                    'local_id': local_id,
                    'cloud_id': inst_client.id,
                    'partner_name': inst_client.partner_id.name,
                    'institution_name': inst_client.institution_id.name,
                    'available_amount': inst_client.available_amount,
                    'sale': inst_client.sale,
                }
            else:
                _logger.warning(
                    f'institution.client NO PROCESADO: deserialize_institution_client retornó None\n'
                    f'  partner_vat={data.get("partner_vat")}\n'
                    f'  institution_id_institutions={data.get("institution_id_institutions")}'
                )
                return {
                    'success': False,
                    'queue_id': queue_id,
                    'local_id': local_id,
                    'error': 'No se pudo encontrar/crear institution.client',
                }

        except Exception as e:
            _logger.error(f'Error procesando institution.client#{local_id}: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return {
                'success': False,
                'queue_id': queue_id,
                'local_id': local_id,
                'error': str(e),
            }

    def _prepare_partner_vals_from_push(self, data):
        """
        Prepara valores para crear/actualizar un partner desde PUSH (offline -> cloud).

        Args:
            data: Diccionario con datos del partner

        Returns:
            dict: Valores preparados para Odoo
        """
        vals = {}

        # Campos permitidos para sincronización desde offline
        allowed_fields = [
            'name', 'email', 'phone', 'mobile', 'vat', 'street', 'street2',
            'city', 'zip', 'comment', 'website', 'function', 'barcode', 'ref',
            'id_database_old', 'active',
        ]

        for field in allowed_fields:
            if field in data and data[field] is not None:
                vals[field] = data[field]

        # Manejar país
        if data.get('country_id'):
            if isinstance(data['country_id'], int):
                country = request.env['res.country'].sudo().browse(data['country_id'])
                if country.exists():
                    vals['country_id'] = country.id
        elif data.get('country_code'):
            country = request.env['res.country'].sudo().search([
                ('code', '=', data['country_code'])
            ], limit=1)
            if country:
                vals['country_id'] = country.id

        # Manejar estado/provincia
        if data.get('state_id'):
            if isinstance(data['state_id'], int):
                state = request.env['res.country.state'].sudo().browse(data['state_id'])
                if state.exists():
                    vals['state_id'] = state.id
        elif data.get('state_code') and vals.get('country_id'):
            state = request.env['res.country.state'].sudo().search([
                ('code', '=', data['state_code']),
                ('country_id', '=', vals['country_id'])
            ], limit=1)
            if state:
                vals['state_id'] = state.id

        # Manejar lista de precios
        if data.get('property_product_pricelist'):
            pricelist = request.env['product.pricelist'].sudo().browse(
                data['property_product_pricelist']
            )
            if pricelist.exists():
                vals['property_product_pricelist'] = pricelist.id

        # Manejar tipo de identificación LATAM
        if data.get('l10n_latam_identification_type_id') or data.get('l10n_latam_identification_type_name'):
            try:
                IdentificationType = request.env['l10n_latam.identification.type'].sudo()
                id_type = None

                if data.get('l10n_latam_identification_type_id'):
                    id_type = IdentificationType.browse(data['l10n_latam_identification_type_id'])
                    if not id_type.exists():
                        id_type = None

                if not id_type and data.get('l10n_latam_identification_type_name'):
                    id_type = IdentificationType.search([
                        ('name', '=', data['l10n_latam_identification_type_name'])
                    ], limit=1)

                if id_type:
                    vals['l10n_latam_identification_type_id'] = id_type.id
            except Exception:
                pass  # El modelo puede no existir

        return vals

    def _create_json_storage_for_order(self, order, json_storage_data, session):
        """
        Crea un registro json.storage en el servidor principal a partir de los datos
        sincronizados de la orden.

        IMPORTANTE: Este método verifica múltiples criterios para evitar duplicados:
        1. Por pos_order (orden actual en el cloud)
        2. Por cloud_sync_id (ID original del offline)
        3. Por client_invoice + pos_reference (identificador único de la transacción)

        Args:
            order: pos.order recién creado
            json_storage_data: Diccionario con datos del json.storage del offline
            session: pos.session de la orden

        Returns:
            json.storage: Registro creado o existente, o None si no debe crearse
        """
        JsonStorage = request.env['json.storage'].sudo()

        # Si el json.storage ya fue enviado/procesado en el offline, no crear en el cloud
        # El campo 'sent' indica que ya fue sincronizado con el sistema externo
        if json_storage_data.get('sent'):
            _logger.info(
                f'json.storage para orden {order.name}: ya fue enviado en offline (sent=True), '
                f'omitiendo creación en cloud'
            )
            return None

        # VERIFICACIÓN 1: Por pos_order (orden actual)
        existing = JsonStorage.search([
            ('pos_order', '=', order.id)
        ], limit=1)

        if existing:
            _logger.info(f'json.storage ya existe para orden {order.name}: ID={existing.id}')
            return existing

        # VERIFICACIÓN 2: Por ID directo del json.storage (mismo servidor/BD)
        # Si el json.storage original existe con el mismo ID, reutilizar
        original_id = json_storage_data.get('id')
        if original_id:
            # Primero buscar por cloud_sync_id
            existing_by_cloud_id = JsonStorage.search([
                ('cloud_sync_id', '=', original_id)
            ], limit=1)
            if existing_by_cloud_id:
                _logger.info(f'json.storage ya sincronizado (cloud_sync_id={original_id}): ID={existing_by_cloud_id.id}')
                # Actualizar la referencia a la orden actual si es necesario
                if existing_by_cloud_id.pos_order.id != order.id:
                    existing_by_cloud_id.write({'pos_order': order.id})
                    _logger.info(f'json.storage actualizado con nueva orden: {order.id}')
                return existing_by_cloud_id

            # Buscar por ID directo (cuando offline y cloud comparten BD)
            existing_by_id = JsonStorage.browse(original_id)
            if existing_by_id.exists():
                _logger.info(f'json.storage encontrado por ID directo={original_id}: ya existe localmente')
                # Actualizar cloud_sync_id y pos_order si es necesario
                update_vals = {}
                if not existing_by_id.cloud_sync_id:
                    update_vals['cloud_sync_id'] = original_id
                if existing_by_id.pos_order.id != order.id:
                    update_vals['pos_order'] = order.id
                if update_vals:
                    existing_by_id.with_context(skip_sync_queue=True).write(update_vals)
                return existing_by_id

        # VERIFICACIÓN 3: Por orden LOCAL original (usando id_database_old de la orden)
        # Esto detecta json.storage creado para la orden antes de sincronizar
        if order.id_database_old:
            local_order = request.env['pos.order'].sudo().search([
                ('id', '=', int(order.id_database_old))
            ], limit=1)
            if local_order:
                existing_by_local = JsonStorage.search([
                    ('pos_order', '=', local_order.id)
                ], limit=1)
                if existing_by_local:
                    _logger.info(
                        f'json.storage encontrado para orden local {local_order.name} '
                        f'(id_database_old={order.id_database_old}): ID={existing_by_local.id}'
                    )
                    # Actualizar referencia a la orden nueva
                    existing_by_local.with_context(skip_sync_queue=True).write({
                        'pos_order': order.id,
                        'cloud_sync_id': original_id if original_id else existing_by_local.cloud_sync_id,
                    })
                    return existing_by_local

        # VERIFICACIÓN 4: Por client_invoice + pos_reference EXACTO de esta orden
        # Solo buscar si hay otra orden con el MISMO pos_reference (duplicado real)
        client_invoice = json_storage_data.get('client_invoice')
        if client_invoice and order.pos_reference:
            # Buscar json.storage que ya esté vinculado a ESTA orden específica
            existing_by_ref = JsonStorage.search([
                ('client_invoice', '=', client_invoice),
                ('pos_order', '=', order.id)  # Debe ser la misma orden, no cualquier orden
            ], limit=1)
            if existing_by_ref:
                _logger.info(
                    f'json.storage encontrado para esta orden {order.name} '
                    f'con client_invoice={client_invoice}: ID={existing_by_ref.id}'
                )
                return existing_by_ref

        # NOTA: Se eliminó la verificación por client_invoice + id_database_old_invoice_client
        # porque esos valores son del CLIENTE, no de la TRANSACCIÓN, y causaba que
        # se encontraran json.storage de transacciones anteriores del mismo cliente.

        # Buscar el pos.config para el campo pos_order_id
        # Primero intentar por config_name (nombre original del POS de la sucursal)
        pos_config = None
        config_name = json_storage_data.get('config_name')
        if config_name:
            pos_config = request.env['pos.config'].sudo().search([
                ('name', '=', config_name)
            ], limit=1)
            if pos_config:
                _logger.info(f'json.storage: pos.config encontrado por nombre "{config_name}": ID={pos_config.id}')

        # Fallback a session.config_id si no se encontró por nombre
        if not pos_config:
            pos_config = session.config_id if session else None
            if pos_config:
                _logger.info(f'json.storage: usando pos.config de sesión (fallback): ID={pos_config.id}')

        # Preparar valores para crear json.storage
        storage_vals = {
            'json_data': json_storage_data.get('json_data'),
            'employee': json_storage_data.get('employee', ''),
            'id_point_of_sale': json_storage_data.get('id_point_of_sale', ''),
            'client_invoice': json_storage_data.get('client_invoice', ''),
            'id_database_old_invoice_client': json_storage_data.get('id_database_old_invoice_client', ''),
            'is_access_key': json_storage_data.get('is_access_key', False),
            'sent': json_storage_data.get('sent', False),
            'db_key': json_storage_data.get('db_key'),
            'pos_order': order.id,  # Referencia a la orden recién creada
        }

        # Agregar pos_order_id (pos.config) si tenemos uno válido
        if pos_config:
            storage_vals['pos_order_id'] = pos_config.id

        # Agregar cloud_sync_id si viene el id original
        if original_id:
            storage_vals['cloud_sync_id'] = original_id

        try:
            # Crear con skip_sync_queue para evitar que se re-agregue a la cola
            new_storage = JsonStorage.with_context(skip_sync_queue=True).create(storage_vals)

            _logger.info(
                f'json.storage creado exitosamente para orden {order.name}: '
                f'ID={new_storage.id}, cloud_sync_id={original_id}'
            )
            return new_storage

        except Exception as e:
            _logger.error(f'Error creando json.storage para orden {order.name}: {e}', exc_info=True)
            raise

    def _find_or_create_session_for_sync(self, data, warehouse_id):
        """
        Busca o crea una sesión POS para sincronización.

        LÓGICA:
        1. Encontrar el pos_config correcto (por nombre, sync_config, o warehouse)
        2. Encontrar el user_id correcto (empleado del OFFLINE)
        3. Buscar sesión ABIERTA existente con ese config_id + user_id
        4. Si existe, reutilizarla (múltiples órdenes del mismo empleado → misma sesión)
        5. Si no existe, crear una nueva

        Args:
            data: Datos de la orden (contiene session_name, config_name, user_name, employee_name)
            warehouse_id: ID del almacén

        Returns:
            pos.session: Sesión encontrada o creada
        """
        PosSession = request.env['pos.session'].sudo()
        PosConfig = request.env['pos.config'].sudo()

        session_name = data.get('session_name')
        config_name = data.get('config_name')

        _logger.info(f'Buscando sesión: session_name={session_name}, config_name={config_name}, warehouse_id={warehouse_id}')

        # ============================================================
        # PASO 1: Encontrar el pos_config correcto
        # ============================================================

        # PRIORIDAD 1: Buscar pos_config por NOMBRE de la orden
        # ESTO ES CRÍTICO: El config_name representa el POS real donde el
        # dependiente hizo la venta. Debe tener prioridad máxima.
        pos_config = None
        if config_name:
            pos_config = PosConfig.search([
                ('name', '=', config_name)
            ], limit=1)
            if pos_config:
                _logger.info(f'Config POS encontrada por nombre (prioridad 1): {pos_config.name} (ID: {pos_config.id})')

        # 3. PRIORIDAD 2: Si no hay por nombre, usar pos_config_ids del sync_config
        # Esto es el fallback cuando el nombre no coincide exactamente
        if not pos_config and warehouse_id:
            sync_config = request.env['pos.sync.config'].sudo().search([
                ('warehouse_id', '=', warehouse_id),
                ('active', '=', True),
            ], limit=1)
            if sync_config and sync_config.pos_config_ids:
                pos_config = sync_config.pos_config_ids[:1]
                if pos_config:
                    _logger.info(f'Config POS desde sync_config (prioridad 2): {pos_config.name} (ID: {pos_config.id})')

        # 4. PRIORIDAD 3: Buscar por almacén directamente
        if not pos_config and warehouse_id:
            pos_config = PosConfig.search([
                ('picking_type_id.warehouse_id', '=', warehouse_id)
            ], limit=1)
            if pos_config:
                _logger.info(f'Config POS encontrada por warehouse (prioridad 3): {pos_config.name} (ID: {pos_config.id})')

        # 5. CRÍTICO: NO buscar "cualquier config activa" como fallback
        # Esto causa que órdenes de una sucursal se asignen a otra
        if not pos_config:
            _logger.error(
                f'No se encontró configuración POS para warehouse_id={warehouse_id}, '
                f'config_name={config_name}. Verifique que pos.sync.config tenga '
                f'pos_config_ids configurados para este almacén.'
            )
            return None

        _logger.info(f'Usando pos_config: {pos_config.name} (ID: {pos_config.id}) para warehouse_id={warehouse_id}')

        # ============================================================
        # PASO 2: Encontrar el usuario correcto (empleado del OFFLINE)
        # ============================================================
        session_user_id = None
        user_name = data.get('user_name') or data.get('cashier_name')
        employee_name = data.get('employee_name')

        # Intentar encontrar usuario por nombre
        if user_name:
            user = request.env['res.users'].sudo().search([
                ('name', '=', user_name)
            ], limit=1)
            if user:
                session_user_id = user.id
                _logger.info(f'Usuario encontrado por nombre: {user.name} (ID: {user.id})')

        # Si no hay usuario, intentar por empleado
        if not session_user_id and employee_name:
            employee = request.env['hr.employee'].sudo().search([
                ('name', '=', employee_name)
            ], limit=1)
            if employee and employee.user_id:
                session_user_id = employee.user_id.id
                _logger.info(f'Usuario encontrado por empleado: {employee.user_id.name}')

        # ============================================================
        # PASO 3: Buscar sesión ABIERTA existente con config_id + user_id
        # Esto permite reutilizar la misma sesión para múltiples órdenes
        # del mismo empleado en el mismo punto de venta
        # ============================================================
        search_domain = [
            ('config_id', '=', pos_config.id),
            ('state', 'in', ['opened', 'opening_control']),
        ]

        # Si tenemos user_id, buscar sesión de ese usuario específico
        if session_user_id:
            session = PosSession.search(
                search_domain + [('user_id', '=', session_user_id)],
                limit=1,
                order='id desc'
            )
            if session:
                _logger.info(
                    f'Sesión existente encontrada para config={pos_config.name}, '
                    f'user_id={session_user_id}: {session.name} (ID: {session.id})'
                )
                return session

        # Si no encontramos con user_id específico, buscar cualquier sesión abierta del config
        session = PosSession.search(search_domain, limit=1, order='id desc')
        if session:
            _logger.info(
                f'Sesión existente encontrada para config={pos_config.name}: '
                f'{session.name} (ID: {session.id})'
            )
            return session

        # ============================================================
        # PASO 4: Crear nueva sesión (solo si no existe ninguna abierta)
        # ============================================================
        try:
            session_vals = {
                'config_id': pos_config.id,
            }
            if session_user_id:
                session_vals['user_id'] = session_user_id

            session = PosSession.with_context(
                skip_sync_queue=True,
                from_pos_offline_sync=True,
                bypass_session_check=True,
            ).create(session_vals)

            # Guardar referencia al nombre original del offline
            if session_name:
                try:
                    session.with_context(skip_sync_queue=True).write({
                        'id_database_old': session_name,
                    })
                except Exception:
                    pass

            _logger.info(
                f'Nueva sesión creada para sync: {session.name} (ID: {session.id}) '
                f'config={pos_config.name}, user_id={session_user_id}'
            )
            return session

        except Exception as e:
            _logger.error(f'Error creando sesión: {e}')
            return None

    # ==================== ENDPOINTS DE PULL (DESCARGA) ====================

    @http.route('/pos_offline_sync/pull', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_records(self, **kwargs):
        """
        Envía actualizaciones al POS offline con paginación.
        OPTIMIZADO: Soporte para paginación y límites por entidad.

        Payload esperado:
        {
            "warehouse_id": 1,
            "entities": ["product.product", "res.partner"],
            "last_sync": "2024-01-15T10:30:00",
            "limit": 500,       // Opcional: límite global por entidad
            "offset": 0,        // Opcional: offset para paginación
            "entity_limits": {  // Opcional: límites específicos por entidad
                "product.product": 1000,
                "res.partner": 500
            }
        }

        Returns:
            dict: Datos para sincronizar
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            entities = data.get('entities', [])
            last_sync = data.get('last_sync')

            # NUEVO: Parámetros de paginación
            global_limit = data.get('limit', 500)  # Límite por defecto más bajo
            offset = data.get('offset', 0)
            entity_limits = data.get('entity_limits', {})

            if not warehouse_id:
                return self._json_response({'success': False, 'error': 'warehouse_id es requerido'})

            # Convertir last_sync a datetime
            last_sync_dt = None
            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                except ValueError:
                    pass

            response_data = {}
            has_more = {}  # Indica si hay más registros disponibles
            deletions = {}  # Eliminaciones pendientes por modelo

            for entity in entities:
                # Obtener límite específico para esta entidad o usar global
                entity_limit = entity_limits.get(entity, global_limit)

                entity_data, more_available = self._get_entity_updates_paginated(
                    entity, warehouse_id, last_sync_dt, entity_limit, offset
                )
                if entity_data:
                    response_data[entity] = entity_data
                    if more_available:
                        has_more[entity] = True

                # Obtener eliminaciones pendientes para este modelo
                entity_deletions = self._get_pending_deletions(entity, warehouse_id, last_sync_dt)
                if entity_deletions:
                    deletions[entity] = entity_deletions
                    _logger.info(f'PULL: {len(entity_deletions)} eliminaciones pendientes para {entity}')

            # Registrar en log
            total_records = sum(len(v) for v in response_data.values())
            total_deletions = sum(len(v) for v in deletions.values())
            self._log_sync_operation(
                warehouse_id, 'pull',
                f'Enviados {total_records} registros y {total_deletions} eliminaciones para {len(entities)} entidades'
            )

            return self._json_response({
                'success': True,
                'data': response_data,
                'deletions': deletions,  # Eliminaciones pendientes
                'sync_date': fields.Datetime.now().isoformat(),
                'has_more': has_more,  # Indica si hay más registros
                'pagination': {
                    'limit': global_limit,
                    'offset': offset,
                }
            })

        except Exception as e:
            _logger.error(f'Error en pull: {str(e)}')
            return self._json_response({'success': False, 'error': str(e)})

    def _get_entity_updates(self, model_name, warehouse_id, last_sync_dt):
        """
        Obtiene actualizaciones de una entidad para un almacén.
        DEPRECADO: Usar _get_entity_updates_paginated para mejor rendimiento.

        Args:
            model_name: Nombre del modelo
            warehouse_id: ID del almacén
            last_sync_dt: Fecha de última sincronización

        Returns:
            list: Lista de registros actualizados
        """
        data, _ = self._get_entity_updates_paginated(
            model_name, warehouse_id, last_sync_dt, limit=1000, offset=0
        )
        return data

    def _get_entity_updates_paginated(self, model_name, warehouse_id, last_sync_dt, limit=500, offset=0):
        """
        Obtiene actualizaciones de una entidad con paginación.
        OPTIMIZADO: Soporte para paginación y procesamiento eficiente.

        Args:
            model_name: Nombre del modelo
            warehouse_id: ID del almacén
            last_sync_dt: Fecha de última sincronización
            limit: Número máximo de registros
            offset: Desplazamiento para paginación

        Returns:
            tuple: (list de registros, bool indicando si hay más)
        """
        try:
            Model = request.env[model_name].sudo()

            # Construir dominio
            domain = []
            if last_sync_dt:
                domain.append(('write_date', '>', last_sync_dt))

            # Filtrar por almacén si el modelo lo soporta
            if model_name == 'stock.quant':
                warehouse = request.env['stock.warehouse'].sudo().browse(warehouse_id)
                if warehouse.exists() and warehouse.lot_stock_id:
                    domain.append(('location_id', 'child_of', warehouse.lot_stock_id.id))

            elif model_name == 'product.product':
                domain.append(('available_in_pos', '=', True))

            elif model_name == 'loyalty.program':
                domain.append(('active', '=', True))

            elif model_name == 'product.pricelist':
                domain.append(('active', '=', True))

            # Logging específico para institution.client
            if model_name == 'institution.client':
                total_count = Model.search_count([])
                filtered_count = Model.search_count(domain) if domain else total_count
                _logger.info(
                    f'PULL institution.client: total={total_count}, '
                    f'con filtro={filtered_count}, domain={domain}, '
                    f'last_sync_dt={last_sync_dt}'
                )

            # Obtener registros con paginación
            # Pedimos 1 extra para saber si hay más
            records = Model.search(domain, limit=limit + 1, offset=offset, order='write_date asc')

            has_more = len(records) > limit
            if has_more:
                records = records[:limit]  # Quitar el registro extra

            # Serializar en lotes para evitar problemas de memoria
            return self._serialize_records_batched(model_name, records), has_more

        except Exception as e:
            _logger.error(f'Error obteniendo {model_name}: {str(e)}')
            return [], False

    def _get_pending_deletions(self, model_name, warehouse_id, last_sync_dt):
        """
        Obtiene eliminaciones pendientes de la cola de sincronización.

        Busca registros en pos.sync.queue con operation='unlink' que necesitan
        ser propagados a otros servidores.

        IMPORTANTE: Las eliminaciones son GLOBALES - no se filtra por warehouse_id.
        Si un registro se elimina en el servidor cloud, TODOS los servidores offline
        deben recibir esa eliminación.

        Args:
            model_name: Nombre del modelo
            warehouse_id: ID del almacén (usado solo para logging, no para filtrar)
            last_sync_dt: Fecha de última sincronización

        Returns:
            list: Lista de datos de registros a eliminar
        """
        try:
            SyncQueue = request.env['pos.sync.queue'].sudo()

            # Buscar eliminaciones pendientes - NO filtrar por warehouse_id
            # porque las eliminaciones son globales (aplican a todos los servidores)
            domain = [
                ('model_name', '=', model_name),
                ('operation', '=', 'unlink'),
            ]

            # Si hay fecha de última sync, solo las más recientes
            if last_sync_dt:
                domain.append(('create_date', '>', last_sync_dt))

            # Buscar eliminaciones en cualquier estado (pending, synced)
            # porque necesitamos propagarlas a otros servidores
            domain.append(('state', 'in', ['pending', 'synced', 'processing']))

            deletions = SyncQueue.search(domain, limit=100)

            _logger.info(
                f'PULL deletions: Buscando eliminaciones de {model_name}, '
                f'encontradas: {len(deletions)}, last_sync_dt: {last_sync_dt}'
            )

            result = []
            for deletion in deletions:
                try:
                    import json
                    data = json.loads(deletion.data_json) if deletion.data_json else {}
                    data['_queue_id'] = deletion.id
                    data['_operation'] = 'unlink'
                    result.append(data)

                    _logger.info(
                        f'Eliminación pendiente encontrada: {model_name} '
                        f'id={data.get("id")}, queue_id={deletion.id}, '
                        f'cloud_deletion={data.get("_cloud_deletion", False)}'
                    )
                except Exception as e:
                    _logger.error(f'Error procesando eliminación {deletion.id}: {e}')

            return result

        except Exception as e:
            _logger.error(f'Error obteniendo eliminaciones de {model_name}: {str(e)}')
            return []

    def _serialize_records_batched(self, model_name, records, batch_size=100):
        """
        Serializa registros en lotes para optimizar memoria.

        Args:
            model_name: Nombre del modelo
            records: Recordset a serializar
            batch_size: Tamaño del lote

        Returns:
            list: Lista de diccionarios
        """
        result = []
        SyncManager = request.env['pos.sync.manager'].sudo()

        # Usar serializers especializados para modelos conocidos
        if model_name == 'res.partner':
            for record in records:
                result.append(SyncManager.serialize_partner(record))
            return result

        if model_name == 'pos.order':
            for record in records:
                result.append(SyncManager.serialize_order(record))
            return result

        # Usar serializer especializado para loyalty.program (incluye rules y rewards)
        if model_name == 'loyalty.program':
            for record in records:
                result.append(SyncManager.serialize_loyalty_program(record))
            return result

        # Para product.product usar serializer especializado
        if model_name == 'product.product':
            for record in records:
                result.append(SyncManager.serialize_product(record))
            return result

        # Para product.pricelist usar serializer especializado
        if model_name == 'product.pricelist':
            for record in records:
                result.append(SyncManager.serialize_pricelist(record))
            return result

        # Para account.fiscal.position usar serializer especializado
        if model_name == 'account.fiscal.position':
            for record in records:
                result.append(SyncManager.serialize_fiscal_position(record))
            return result

        # Para institution usar serializer especializado
        if model_name == 'institution':
            for record in records:
                result.append(SyncManager.serialize_institution(record))
            return result

        # Para institution.client usar serializer especializado
        if model_name == 'institution.client':
            for record in records:
                result.append(SyncManager.serialize_institution_client(record))
            return result

        # Para otros modelos, serialización genérica en lotes
        record_ids = records.ids
        for i in range(0, len(record_ids), batch_size):
            batch_ids = record_ids[i:i + batch_size]
            batch_records = records.browse(batch_ids)

            for record in batch_records:
                data = {'id': record.id}
                for field_name, field in record._fields.items():
                    if field.store and not field.compute and field_name not in ['__last_update']:
                        try:
                            value = record[field_name]
                            if field.type == 'many2one' and value:
                                data[field_name] = value.id
                            elif field.type in ['one2many', 'many2many']:
                                data[field_name] = value.ids if value else []
                            elif field.type in ['datetime', 'date'] and value:
                                data[field_name] = value.isoformat() if hasattr(value, 'isoformat') else str(value)
                            elif field.type == 'binary':
                                pass  # Skip binary fields
                            else:
                                data[field_name] = value
                        except Exception:
                            pass
                result.append(data)

            # Limpiar cache entre lotes para liberar memoria
            records.invalidate_recordset()

        return result

    def _serialize_records(self, model_name, records):
        """
        Serializa registros para envío.

        Args:
            model_name: Nombre del modelo
            records: Recordset a serializar

        Returns:
            list: Lista de diccionarios
        """
        result = []
        SyncManager = request.env['pos.sync.manager'].sudo()

        # Usar serializers especializados para modelos conocidos
        if model_name == 'res.partner':
            for record in records:
                result.append(SyncManager.serialize_partner(record))
            return result

        if model_name == 'pos.order':
            for record in records:
                result.append(SyncManager.serialize_order(record))
            return result

        # Usar serializer especializado para loyalty.program (incluye rules y rewards)
        if model_name == 'loyalty.program':
            for record in records:
                result.append(SyncManager.serialize_loyalty_program(record))
            return result

        # Usar serializer especializado para product.product
        if model_name == 'product.product':
            for record in records:
                result.append(SyncManager.serialize_product(record))
            return result

        # Usar serializer especializado para product.pricelist
        if model_name == 'product.pricelist':
            for record in records:
                result.append(SyncManager.serialize_pricelist(record))
            return result

        # Usar serializer especializado para account.fiscal.position
        if model_name == 'account.fiscal.position':
            for record in records:
                result.append(SyncManager.serialize_fiscal_position(record))
            return result

        # Usar serializer especializado para institution
        if model_name == 'institution':
            for record in records:
                result.append(SyncManager.serialize_institution(record))
            return result

        # Usar serializer especializado para institution.client
        if model_name == 'institution.client':
            for record in records:
                result.append(SyncManager.serialize_institution_client(record))
            return result

        # Campos por modelo para otros modelos
        fields_map = {
            'product.product': [
                'id', 'name', 'default_code', 'barcode', 'list_price',
                'standard_price', 'categ_id', 'uom_id', 'available_in_pos',
            ],
            'stock.quant': [
                'id', 'product_id', 'location_id', 'quantity',
                'reserved_quantity', 'lot_id',
            ],
            'loyalty.program': [
                'id', 'name', 'program_type', 'trigger', 'applies_on',
                'date_from', 'date_to', 'limit_usage', 'max_usage',
            ],
            'hr.employee': [
                'id', 'name', 'barcode', 'pin', 'user_id',
            ],
            'pos.payment.method': [
                'id', 'name', 'is_cash_count', 'journal_id',
                'split_transactions', 'receivable_account_id',
            ],
        }

        field_list = fields_map.get(model_name, ['id', 'name'])

        for record in records:
            data = {}
            for field in field_list:
                if hasattr(record, field):
                    value = getattr(record, field)
                    # Convertir Many2one a ID
                    if hasattr(value, 'id'):
                        data[field] = value.id
                    elif isinstance(value, datetime):
                        data[field] = value.isoformat()
                    else:
                        data[field] = value
            result.append(data)

        return result

    # ==================== ENDPOINTS DE ÓRDENES ====================

    @http.route('/pos_offline_sync/push_order', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def push_order(self, **kwargs):
        """
        Endpoint especializado para sincronizar órdenes POS.

        Payload esperado:
        {
            "warehouse_id": 1,
            "order_data": {
                "name": "POS/001",
                "lines": [...],
                "payments": [...],
                ...
            }
        }

        Returns:
            dict: Resultado de la sincronización
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            order_data = data.get('order_data')

            if not warehouse_id or not order_data:
                return self._json_response({
                    'success': False,
                    'error': 'warehouse_id y order_data son requeridos'
                })

            # Obtener configuración
            config = request.env['pos.sync.config'].sudo().get_config_for_warehouse(
                warehouse_id
            )

            if not config:
                return self._json_response({
                    'success': False,
                    'error': 'No hay configuración de sincronización'
                })

            # Crear orden
            manager = request.env['pos.sync.manager'].sudo()
            order = manager.deserialize_order(order_data, config)

            return self._json_response({
                'success': True,
                'order_id': order.id,
                'order_name': order.name,
            })

        except Exception as e:
            _logger.error(f'Error sincronizando orden: {str(e)}')
            return self._json_response({'success': False, 'error': str(e)})

    @http.route('/pos_offline_sync/orders/pending', type='json', auth='user',
                methods=['POST'], csrf=False)
    def get_pending_orders(self, warehouse_id=None, limit=100, **kwargs):
        """
        Obtiene órdenes pendientes de sincronización.

        Args:
            warehouse_id: ID del almacén
            limit: Límite de registros

        Returns:
            dict: Órdenes pendientes
        """
        if not warehouse_id:
            return {'success': False, 'error': 'warehouse_id es requerido'}

        orders = request.env['pos.order'].sudo().get_pending_sync_orders(
            warehouse_id, limit=limit
        )

        manager = request.env['pos.sync.manager'].sudo()
        orders_data = [manager.serialize_order(o) for o in orders]

        return {
            'success': True,
            'count': len(orders_data),
            'orders': orders_data,
        }

    # ==================== ENDPOINTS DE PRODUCTOS ====================

    @http.route('/pos_offline_sync/products', type='json', auth='public',
                methods=['POST'], csrf=False)
    def get_products(self, warehouse_id=None, last_sync=None,
                     limit=1000, offset=0, **kwargs):
        """
        Obtiene productos para sincronización.

        Args:
            warehouse_id: ID del almacén
            last_sync: Fecha de última sincronización
            limit: Límite de registros
            offset: Offset para paginación

        Returns:
            dict: Productos
        """
        try:
            if not self._validate_api_auth(kwargs):
                return {'success': False, 'error': 'Autenticación inválida'}

            domain = [('available_in_pos', '=', True)]

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            Product = request.env['product.product'].sudo()
            total = Product.search_count(domain)
            products = Product.search(domain, limit=limit, offset=offset)

            products_data = self._serialize_records('product.product', products)

            return {
                'success': True,
                'total': total,
                'count': len(products_data),
                'offset': offset,
                'products': products_data,
            }

        except Exception as e:
            _logger.error(f'Error obteniendo productos: {str(e)}')
            return {'success': False, 'error': str(e)}

    # ==================== ENDPOINTS DE STOCK ====================

    @http.route('/pos_offline_sync/stock', type='json', auth='public',
                methods=['POST'], csrf=False)
    def get_stock(self, warehouse_id=None, product_ids=None, **kwargs):
        """
        Obtiene stock para un almacén específico.

        Args:
            warehouse_id: ID del almacén
            product_ids: Lista de IDs de productos (opcional)

        Returns:
            dict: Stock disponible
        """
        try:
            if not self._validate_api_auth(kwargs):
                return {'success': False, 'error': 'Autenticación inválida'}

            if not warehouse_id:
                return {'success': False, 'error': 'warehouse_id es requerido'}

            warehouse = request.env['stock.warehouse'].sudo().browse(warehouse_id)
            if not warehouse.exists():
                return {'success': False, 'error': 'Almacén no encontrado'}

            domain = [
                ('location_id', 'child_of', warehouse.lot_stock_id.id),
                ('quantity', '>', 0),
            ]

            if product_ids:
                domain.append(('product_id', 'in', product_ids))

            Quant = request.env['stock.quant'].sudo()
            quants = Quant.search(domain)

            stock_data = []
            for quant in quants:
                stock_data.append({
                    'product_id': quant.product_id.id,
                    'product_barcode': quant.product_id.barcode,
                    'product_name': quant.product_id.name,
                    'quantity': quant.quantity,
                    'reserved_quantity': quant.reserved_quantity,
                    'available_quantity': quant.quantity - quant.reserved_quantity,
                    'lot_id': quant.lot_id.id if quant.lot_id else None,
                    'lot_name': quant.lot_id.name if quant.lot_id else None,
                })

            return {
                'success': True,
                'warehouse_id': warehouse_id,
                'warehouse_name': warehouse.name,
                'count': len(stock_data),
                'stock': stock_data,
            }

        except Exception as e:
            _logger.error(f'Error obteniendo stock: {str(e)}')
            return {'success': False, 'error': str(e)}

    # ==================== ENDPOINTS DE CLIENTES ====================

    @http.route('/pos_offline_sync/partners', type='json', auth='public',
                methods=['POST'], csrf=False)
    def get_partners(self, last_sync=None, limit=1000, offset=0, **kwargs):
        """
        Obtiene clientes para sincronización.

        Args:
            last_sync: Fecha de última sincronización
            limit: Límite de registros
            offset: Offset para paginación

        Returns:
            dict: Clientes
        """
        try:
            if not self._validate_api_auth(kwargs):
                return {'success': False, 'error': 'Autenticación inválida'}

            domain = [('type', '=', 'contact')]

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            Partner = request.env['res.partner'].sudo()
            total = Partner.search_count(domain)
            partners = Partner.search(domain, limit=limit, offset=offset)

            partners_data = self._serialize_records('res.partner', partners)

            return {
                'success': True,
                'total': total,
                'count': len(partners_data),
                'offset': offset,
                'partners': partners_data,
            }

        except Exception as e:
            _logger.error(f'Error obteniendo clientes: {str(e)}')
            return {'success': False, 'error': str(e)}

    @http.route('/pos_offline_sync/partner/create', type='json', auth='public',
                methods=['POST'], csrf=False)
    def create_partner(self, partner_data=None, **kwargs):
        """
        Crea un nuevo cliente desde el POS offline.

        Args:
            partner_data: Datos del cliente

        Returns:
            dict: Cliente creado
        """
        try:
            if not self._validate_api_auth(kwargs):
                return {'success': False, 'error': 'Autenticación inválida'}

            if not partner_data:
                return {'success': False, 'error': 'partner_data es requerido'}

            Partner = request.env['res.partner'].sudo()

            # Verificar si ya existe por VAT
            if partner_data.get('vat'):
                existing = Partner.search([
                    ('vat', '=', partner_data['vat'])
                ], limit=1)
                if existing:
                    return {
                        'success': True,
                        'partner_id': existing.id,
                        'partner_name': existing.name,
                        'message': 'Cliente ya existe',
                    }

            # Crear nuevo cliente
            allowed_fields = [
                'name', 'email', 'phone', 'mobile', 'vat', 'street',
                'city', 'country_id', 'state_id', 'zip', 'type'
            ]
            vals = {k: v for k, v in partner_data.items() if k in allowed_fields}
            vals['type'] = 'contact'

            partner = Partner.create(vals)

            return {
                'success': True,
                'partner_id': partner.id,
                'partner_name': partner.name,
            }

        except Exception as e:
            _logger.error(f'Error creando cliente: {str(e)}')
            return {'success': False, 'error': str(e)}

    @http.route('/pos_offline_sync/push_partner', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def push_partner(self, **kwargs):
        """
        Endpoint especializado para sincronizar partners (clientes).

        Payload esperado:
        {
            "warehouse_id": 1,
            "partner_data": {
                "name": "Cliente Ejemplo",
                "vat": "123456789",
                "email": "cliente@ejemplo.com",
                ...
            }
        }

        O para múltiples partners:
        {
            "warehouse_id": 1,
            "partners": [
                {"queue_id": 1, "local_id": 10, "operation": "create", "data": {...}},
                {"queue_id": 2, "local_id": 11, "operation": "write", "data": {...}}
            ]
        }

        Returns:
            dict: Resultado de la sincronización
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')

            # Modo 1: Un solo partner
            partner_data = data.get('partner_data')
            if partner_data:
                SyncManager = request.env['pos.sync.manager'].sudo()
                partner = SyncManager.deserialize_partner(partner_data)

                return self._json_response({
                    'success': True,
                    'partner_id': partner.id,
                    'partner_name': partner.name,
                })

            # Modo 2: Múltiples partners (igual que push genérico)
            partners = data.get('partners', [])
            if not partners:
                return self._json_response({
                    'success': False,
                    'error': 'partner_data o partners es requerido'
                })

            results = []
            for partner_record in partners:
                result = self._process_res_partner(
                    partner_record.get('queue_id'),
                    partner_record.get('local_id'),
                    partner_record.get('data', {}),
                    partner_record.get('operation', 'create')
                )
                results.append(result)

            success_count = len([r for r in results if r.get('success')])

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'push_partner',
                    f'Recibidos {len(partners)} partners. Exitosos: {success_count}'
                )

            return self._json_response({
                'success': True,
                'results': results,
                'summary': {
                    'total': len(partners),
                    'successful': success_count,
                    'failed': len(partners) - success_count,
                }
            })

        except Exception as e:
            _logger.error(f'Error sincronizando partner: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    @http.route('/pos_offline_sync/pull_partners', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_partners(self, **kwargs):
        """
        Endpoint especializado para descargar partners desde el cloud.

        Payload esperado:
        {
            "warehouse_id": 1,
            "last_sync": "2024-01-15T10:30:00",
            "limit": 1000,
            "offset": 0
        }

        Returns:
            dict: Partners para sincronizar
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            last_sync = data.get('last_sync')
            limit = data.get('limit', 1000)
            offset = data.get('offset', 0)

            # Construir dominio
            domain = []
            # No filtrar solo por tipo 'contact' para incluir todos los partners útiles
            # domain.append(('type', 'in', ['contact', 'invoice', 'delivery']))

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            Partner = request.env['res.partner'].sudo()
            SyncManager = request.env['pos.sync.manager'].sudo()

            total = Partner.search_count(domain)
            partners = Partner.search(domain, limit=limit, offset=offset, order='write_date asc')

            # Serializar usando el método especializado
            partners_data = []
            for partner in partners:
                partners_data.append(SyncManager.serialize_partner(partner))

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'pull_partners',
                    f'Enviados {len(partners_data)} partners'
                )

            return self._json_response({
                'success': True,
                'total': total,
                'count': len(partners_data),
                'offset': offset,
                'partners': partners_data,
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo partners: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    @http.route('/pos_offline_sync/partner/sync', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def sync_partners_bidirectional(self, **kwargs):
        """
        Endpoint para sincronización bidireccional de partners.

        Realiza tanto push (offline -> cloud) como pull (cloud -> offline)
        en una sola operación. Esto es más eficiente que llamar a los
        endpoints push y pull por separado.

        Payload esperado:
        {
            "warehouse_id": 1,
            "last_sync": "2024-01-15T10:30:00",
            "local_partners": [
                {
                    "local_id": 123,
                    "queue_id": 456,
                    "operation": "create|write|unlink",
                    "data": {...}
                }
            ]
        }

        Returns:
            dict: Resultado de la sincronización bidireccional con:
                - push: resultados del push (offline -> cloud)
                - pull: partners del cloud (cloud -> offline)
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            last_sync = data.get('last_sync')
            local_partners = data.get('local_partners', [])

            if not warehouse_id:
                return self._json_response({
                    'success': False,
                    'error': 'warehouse_id es requerido'
                })

            # 1. PUSH: Procesar partners locales (offline -> cloud)
            push_results = []
            for partner_data in local_partners:
                result = self._process_res_partner(
                    partner_data.get('queue_id'),
                    partner_data.get('local_id'),
                    partner_data.get('data', {}),
                    partner_data.get('operation', 'create')
                )
                push_results.append(result)

            # 2. PULL: Obtener partners actualizados del cloud
            last_sync_dt = None
            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                except ValueError:
                    pass

            # Obtener partners modificados desde last_sync
            Partner = request.env['res.partner'].sudo()
            SyncManager = request.env['pos.sync.manager'].sudo()

            domain = []  # Incluir todos los tipos de partner
            if last_sync_dt:
                domain.append(('write_date', '>', last_sync_dt))

            cloud_partners = Partner.search(domain, limit=1000, order='write_date asc')
            cloud_partners_data = []
            for p in cloud_partners:
                cloud_partners_data.append(SyncManager.serialize_partner(p))

            push_success = len([r for r in push_results if r.get('success')])

            # Registrar en log
            self._log_sync_operation(
                warehouse_id, 'full_sync',
                f'Sync bidireccional partners: {push_success} push, {len(cloud_partners_data)} pull'
            )

            return self._json_response({
                'success': True,
                'push': {
                    'results': push_results,
                    'total': len(local_partners),
                    'successful': push_success,
                    'failed': len(local_partners) - push_success,
                },
                'pull': {
                    'partners': cloud_partners_data,
                    'count': len(cloud_partners_data),
                },
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error en sync bidireccional de partners: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    # ==================== ENDPOINTS DE PRODUCTOS (PULL) ====================

    @http.route('/pos_offline_sync/pull_products', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_products(self, **kwargs):
        """
        Endpoint especializado para descargar productos desde el cloud.

        Payload esperado:
        {
            "warehouse_id": 1,
            "last_sync": "2024-01-15T10:30:00",
            "limit": 1000,
            "offset": 0,
            "only_pos": true
        }

        Returns:
            dict: Productos para sincronizar
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            last_sync = data.get('last_sync')
            limit = data.get('limit', 1000)
            offset = data.get('offset', 0)
            only_pos = data.get('only_pos', True)

            # Construir dominio
            domain = []
            if only_pos:
                domain.append(('available_in_pos', '=', True))

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            Product = request.env['product.product'].sudo()
            SyncManager = request.env['pos.sync.manager'].sudo()

            total = Product.search_count(domain)
            products = Product.search(domain, limit=limit, offset=offset, order='write_date asc')

            # Serializar usando el método especializado
            products_data = []
            for product in products:
                products_data.append(SyncManager.serialize_product(product))

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'pull_products',
                    f'Enviados {len(products_data)} productos'
                )

            return self._json_response({
                'success': True,
                'total': total,
                'count': len(products_data),
                'offset': offset,
                'products': products_data,
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo productos: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    # ==================== ENDPOINTS DE LISTAS DE PRECIOS (PULL) ====================

    @http.route('/pos_offline_sync/pull_pricelists', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_pricelists(self, **kwargs):
        """
        Endpoint especializado para descargar listas de precios desde el cloud.

        Payload esperado:
        {
            "warehouse_id": 1,
            "last_sync": "2024-01-15T10:30:00",
            "limit": 100,
            "offset": 0
        }

        Returns:
            dict: Listas de precios para sincronizar
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            last_sync = data.get('last_sync')
            limit = data.get('limit', 100)
            offset = data.get('offset', 0)

            # Construir dominio
            domain = [('active', '=', True)]

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            Pricelist = request.env['product.pricelist'].sudo()
            SyncManager = request.env['pos.sync.manager'].sudo()

            total = Pricelist.search_count(domain)
            pricelists = Pricelist.search(domain, limit=limit, offset=offset, order='write_date asc')

            # Serializar usando el método especializado
            pricelists_data = []
            for pricelist in pricelists:
                pricelists_data.append(SyncManager.serialize_pricelist(pricelist))

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'pull_pricelists',
                    f'Enviadas {len(pricelists_data)} listas de precios'
                )

            return self._json_response({
                'success': True,
                'total': total,
                'count': len(pricelists_data),
                'offset': offset,
                'pricelists': pricelists_data,
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo listas de precios: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    # ==================== ENDPOINTS DE PROGRAMAS DE LEALTAD (PULL) ====================

    @http.route('/pos_offline_sync/pull_loyalty_programs', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_loyalty_programs(self, **kwargs):
        """
        Endpoint especializado para descargar programas de lealtad/promociones desde el cloud.

        Payload esperado:
        {
            "warehouse_id": 1,
            "last_sync": "2024-01-15T10:30:00",
            "limit": 100,
            "offset": 0,
            "program_types": ["promotion", "coupons", "loyalty"]
        }

        Returns:
            dict: Programas de lealtad para sincronizar
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            last_sync = data.get('last_sync')
            limit = data.get('limit', 100)
            offset = data.get('offset', 0)
            program_types = data.get('program_types', [])

            # Construir dominio
            domain = [('active', '=', True)]

            # Filtrar por tipos de programa si se especifica
            if program_types:
                domain.append(('program_type', 'in', program_types))

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            Program = request.env['loyalty.program'].sudo()
            SyncManager = request.env['pos.sync.manager'].sudo()

            total = Program.search_count(domain)
            programs = Program.search(domain, limit=limit, offset=offset, order='write_date asc')

            # Serializar usando el método especializado
            programs_data = []
            for program in programs:
                programs_data.append(SyncManager.serialize_loyalty_program(program))

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'pull_loyalty_programs',
                    f'Enviados {len(programs_data)} programas de lealtad'
                )

            return self._json_response({
                'success': True,
                'total': total,
                'count': len(programs_data),
                'offset': offset,
                'programs': programs_data,
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo programas de lealtad: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    # ==================== ENDPOINTS DE POSICIONES FISCALES (PULL) ====================

    @http.route('/pos_offline_sync/pull_fiscal_positions', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_fiscal_positions(self, **kwargs):
        """
        Endpoint especializado para descargar posiciones fiscales desde el cloud.
        Incluye descuentos institucionales.

        Payload esperado:
        {
            "warehouse_id": 1,
            "last_sync": "2024-01-15T10:30:00",
            "limit": 100,
            "offset": 0,
            "only_institutional": false
        }

        Returns:
            dict: Posiciones fiscales para sincronizar
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            last_sync = data.get('last_sync')
            limit = data.get('limit', 100)
            offset = data.get('offset', 0)
            only_institutional = data.get('only_institutional', False)

            # Construir dominio
            domain = []

            # Filtrar solo institucionales si se especifica
            if only_institutional:
                domain.append(('is_institutional', '=', True))

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            FiscalPosition = request.env['account.fiscal.position'].sudo()
            SyncManager = request.env['pos.sync.manager'].sudo()

            total = FiscalPosition.search_count(domain)
            fiscal_positions = FiscalPosition.search(domain, limit=limit, offset=offset, order='write_date asc')

            # Serializar usando el método especializado
            fiscal_positions_data = []
            for fp in fiscal_positions:
                fiscal_positions_data.append(SyncManager.serialize_fiscal_position(fp))

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'pull_fiscal_positions',
                    f'Enviadas {len(fiscal_positions_data)} posiciones fiscales'
                )

            return self._json_response({
                'success': True,
                'total': total,
                'count': len(fiscal_positions_data),
                'offset': offset,
                'fiscal_positions': fiscal_positions_data,
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo posiciones fiscales: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    # ==================== ENDPOINTS DE NOTAS DE CRÉDITO / REEMBOLSOS (PUSH) ====================

    @http.route('/pos_offline_sync/push_refund', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def push_refund(self, **kwargs):
        """
        Endpoint especializado para sincronizar notas de crédito/reembolsos.

        Payload esperado:
        {
            "warehouse_id": 1,
            "refund_data": {
                "name": "REFUND/001",
                "original_order_reference": "POS/001",
                "lines": [...],
                "payments": [...],
                ...
            }
        }

        Returns:
            dict: Resultado de la sincronización
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            refund_data = data.get('refund_data')

            if not warehouse_id or not refund_data:
                return self._json_response({
                    'success': False,
                    'error': 'warehouse_id y refund_data son requeridos'
                })

            # Buscar la orden original si se proporciona referencia
            original_order = None
            original_ref = refund_data.get('original_order_reference') or refund_data.get('original_order', {}).get('pos_reference')
            if original_ref:
                original_order = request.env['pos.order'].sudo().search([
                    ('pos_reference', '=', original_ref)
                ], limit=1)
                if not original_order:
                    # Buscar por nombre
                    original_order = request.env['pos.order'].sudo().search([
                        ('name', '=', original_ref)
                    ], limit=1)

            # Verificar si el reembolso ya existe
            pos_reference = refund_data.get('pos_reference')
            if pos_reference:
                existing = request.env['pos.order'].sudo().search([
                    ('pos_reference', '=', pos_reference)
                ], limit=1)
                if existing:
                    return self._json_response({
                        'success': True,
                        'refund_id': existing.id,
                        'refund_name': existing.name,
                        'message': 'Reembolso ya existe',
                    })

            # Obtener configuración
            config = request.env['pos.sync.config'].sudo().get_config_for_warehouse(warehouse_id)

            # Crear el reembolso como una orden normal
            result = self._process_pos_order(
                refund_data.get('queue_id'),
                refund_data.get('local_id'),
                refund_data,
                warehouse_id
            )

            if result.get('success') and original_order:
                # Vincular con la orden original si existe
                refund_order = request.env['pos.order'].sudo().browse(result.get('cloud_id'))
                if refund_order.exists() and hasattr(refund_order, 'refunded_order_ids'):
                    try:
                        refund_order.write({
                            'refunded_order_ids': [(4, original_order.id)]
                        })
                    except Exception as e:
                        _logger.warning(f'Error vinculando reembolso con orden original: {e}')

            # Registrar en log
            self._log_sync_operation(
                warehouse_id, 'push_refund',
                f'Reembolso procesado: {result.get("order_name", "")}'
            )

            return self._json_response({
                'success': result.get('success', False),
                'refund_id': result.get('cloud_id'),
                'refund_name': result.get('order_name'),
                'pos_reference': result.get('pos_reference'),
                'original_order_id': original_order.id if original_order else None,
                'error': result.get('error'),
            })

        except Exception as e:
            _logger.error(f'Error sincronizando reembolso: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    # ==================== ENDPOINTS DE SESIONES POS ====================

    @http.route('/pos_offline_sync/push_session', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def push_session(self, **kwargs):
        """
        Endpoint para sincronizar sesiones POS (apertura/cierre) al cloud.

        Payload esperado:
        {
            "warehouse_id": 1,
            "session_data": {
                "name": "POS/001",
                "state": "closed",
                "start_at": "2024-01-15T08:00:00",
                "stop_at": "2024-01-15T18:00:00",
                "cash_register_balance_start": 100.0,
                "cash_register_balance_end_real": 500.0,
                ...
            }
        }

        Returns:
            dict: Resultado de la sincronización
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            session_data = data.get('session_data')

            if not warehouse_id or not session_data:
                return self._json_response({
                    'success': False,
                    'error': 'warehouse_id y session_data son requeridos'
                })

            SyncManager = request.env['pos.sync.manager'].sudo()

            # Deserializar y crear/actualizar sesión
            session = SyncManager.deserialize_session(session_data)

            if session:
                # Registrar en log
                self._log_sync_operation(
                    warehouse_id, 'push_session',
                    f'Sesión sincronizada: {session.name}'
                )

                return self._json_response({
                    'success': True,
                    'session_id': session.id,
                    'session_name': session.name,
                    'state': session.state,
                })
            else:
                return self._json_response({
                    'success': False,
                    'error': 'No se pudo crear/actualizar la sesión'
                })

        except Exception as e:
            _logger.error(f'Error sincronizando sesión: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    @http.route('/pos_offline_sync/pull_sessions', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_sessions(self, **kwargs):
        """
        Endpoint para descargar sesiones POS desde el cloud.

        Payload esperado:
        {
            "warehouse_id": 1,
            "last_sync": "2024-01-15T10:30:00",
            "config_id": 1,
            "limit": 100,
            "offset": 0
        }

        Returns:
            dict: Sesiones para sincronizar
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            last_sync = data.get('last_sync')
            config_id = data.get('config_id')
            limit = data.get('limit', 100)
            offset = data.get('offset', 0)

            # Construir dominio
            domain = []

            if config_id:
                domain.append(('config_id', '=', config_id))

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            Session = request.env['pos.session'].sudo()
            SyncManager = request.env['pos.sync.manager'].sudo()

            total = Session.search_count(domain)
            sessions = Session.search(domain, limit=limit, offset=offset, order='write_date asc')

            # Serializar
            sessions_data = []
            for session in sessions:
                sessions_data.append(SyncManager.serialize_session(session))

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'pull_sessions',
                    f'Enviadas {len(sessions_data)} sesiones'
                )

            return self._json_response({
                'success': True,
                'total': total,
                'count': len(sessions_data),
                'offset': offset,
                'sessions': sessions_data,
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo sesiones: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    # ==================== ENDPOINTS DE TRANSFERENCIAS DE STOCK ====================

    @http.route('/pos_offline_sync/push_stock_transfer', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def push_stock_transfer(self, **kwargs):
        """
        Endpoint para sincronizar transferencias de stock al cloud.

        Payload esperado:
        {
            "warehouse_id": 1,
            "transfer_data": {
                "name": "WH/INT/001",
                "picking_type_code": "internal",
                "location_id": 1,
                "location_dest_id": 2,
                "moves": [
                    {"product_id": 1, "product_uom_qty": 10},
                    ...
                ]
            }
        }

        Returns:
            dict: Resultado de la sincronización
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            transfer_data = data.get('transfer_data')

            if not warehouse_id or not transfer_data:
                return self._json_response({
                    'success': False,
                    'error': 'warehouse_id y transfer_data son requeridos'
                })

            # Verificar si la transferencia ya existe
            if transfer_data.get('name') and transfer_data['name'] != '/':
                existing = request.env['stock.picking'].sudo().search([
                    ('name', '=', transfer_data['name'])
                ], limit=1)
                if existing:
                    return self._json_response({
                        'success': True,
                        'transfer_id': existing.id,
                        'transfer_name': existing.name,
                        'message': 'Transferencia ya existe',
                    })

            SyncManager = request.env['pos.sync.manager'].sudo()

            # Deserializar y crear/actualizar transferencia
            picking = SyncManager.deserialize_stock_picking(transfer_data)

            if picking:
                # Marcar como creada desde POS
                if hasattr(picking, 'created_from_pos'):
                    picking.write({'created_from_pos': True})

                # Registrar en log
                self._log_sync_operation(
                    warehouse_id, 'push_stock_transfer',
                    f'Transferencia sincronizada: {picking.name}'
                )

                return self._json_response({
                    'success': True,
                    'transfer_id': picking.id,
                    'transfer_name': picking.name,
                    'state': picking.state,
                })
            else:
                return self._json_response({
                    'success': False,
                    'error': 'No se pudo crear/actualizar la transferencia'
                })

        except Exception as e:
            _logger.error(f'Error sincronizando transferencia: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    @http.route('/pos_offline_sync/pull_stock_transfers', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_stock_transfers(self, **kwargs):
        """
        Endpoint para descargar transferencias de stock desde el cloud.

        Payload esperado:
        {
            "warehouse_id": 1,
            "last_sync": "2024-01-15T10:30:00",
            "picking_type_code": "internal",
            "limit": 100,
            "offset": 0
        }

        Returns:
            dict: Transferencias para sincronizar
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            last_sync = data.get('last_sync')
            picking_type_code = data.get('picking_type_code', 'internal')
            limit = data.get('limit', 100)
            offset = data.get('offset', 0)

            # Construir dominio
            domain = [('picking_type_id.code', '=', picking_type_code)]

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            Picking = request.env['stock.picking'].sudo()
            SyncManager = request.env['pos.sync.manager'].sudo()

            total = Picking.search_count(domain)
            pickings = Picking.search(domain, limit=limit, offset=offset, order='write_date asc')

            # Serializar
            pickings_data = []
            for picking in pickings:
                pickings_data.append(SyncManager.serialize_stock_picking(picking))

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'pull_stock_transfers',
                    f'Enviadas {len(pickings_data)} transferencias'
                )

            return self._json_response({
                'success': True,
                'total': total,
                'count': len(pickings_data),
                'offset': offset,
                'transfers': pickings_data,
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo transferencias: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    # ==================== ENDPOINT DE MIGRACIÓN INICIAL ====================

    @http.route('/pos_offline_sync/migration/manifest', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def get_migration_manifest(self, **kwargs):
        """
        Obtiene el manifiesto de datos para migración inicial.

        Retorna conteos de cada modelo para planificar la migración por lotes.
        NO carga datos, solo metadatos para el cliente.

        Payload esperado:
        {
            "warehouse_id": 1,
            "api_key": "xxx"
        }

        Returns:
            dict: Manifiesto con conteos por modelo
        """
        try:
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            # Conteos por modelo (sin cargar registros)
            manifest = {
                'product_categories': request.env['product.category'].sudo().search_count([]),
                'uom': request.env['uom.uom'].sudo().search_count([]),
                'taxes': request.env['account.tax'].sudo().search_count([
                    ('active', '=', True),
                    ('type_tax_use', '=', 'sale'),
                ]),
                'fiscal_positions': request.env['account.fiscal.position'].sudo().search_count([
                    ('active', '=', True)
                ]),
                'payment_methods': request.env['pos.payment.method'].sudo().search_count([
                    ('active', '=', True)
                ]),
                'partners': request.env['res.partner'].sudo().search_count([
                    ('active', '=', True)
                ]),
                'pricelists': request.env['product.pricelist'].sudo().search_count([
                    ('active', '=', True)
                ]),
                'product_templates': request.env['product.template'].sudo().search_count([
                    ('available_in_pos', '=', True)
                ]),
                'products': request.env['product.product'].sudo().search_count([
                    ('available_in_pos', '=', True)
                ]),
                'pricelist_items': request.env['product.pricelist.item'].sudo().search_count([]),
                'loyalty_programs': request.env['loyalty.program'].sudo().search_count([
                    ('active', '=', True)
                ]) if 'loyalty.program' in request.env else 0,
                'loyalty_rules': request.env['loyalty.rule'].sudo().search_count([
                ]) if 'loyalty.rule' in request.env else 0,
                'loyalty_rewards': request.env['loyalty.reward'].sudo().search_count([
                ]) if 'loyalty.reward' in request.env else 0,
            }

            # Orden recomendado de sincronización (dependencias primero)
            sync_order = [
                'product_categories',   # Sin dependencias
                'uom',                  # Sin dependencias
                'taxes',                # Sin dependencias
                'fiscal_positions',     # Sin dependencias
                'payment_methods',      # Sin dependencias (journal se resuelve por nombre)
                'partners',             # Sin dependencias
                'pricelists',           # Sin dependencias
                'product_templates',    # Depende de: categories, taxes, uom
                'products',             # Depende de: templates
                'pricelist_items',      # Depende de: pricelists, products
                'loyalty_programs',     # Sin dependencias
                'loyalty_rules',        # Depende de: programs
                'loyalty_rewards',      # Depende de: programs
            ]

            return self._json_response({
                'success': True,
                'manifest': manifest,
                'sync_order': sync_order,
                'recommended_batch_size': 500,
                'server_time': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo manifiesto: {str(e)}')
            return self._json_response({'success': False, 'error': str(e)})

    @http.route('/pos_offline_sync/migration/pull_batch', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_migration_batch(self, **kwargs):
        """
        Descarga un lote de datos para migración.

        Endpoint unificado que descarga cualquier modelo por lotes.
        Optimizado para migración inicial (sin verificar write_date).

        Payload esperado:
        {
            "model": "product.product",
            "limit": 500,
            "offset": 0,
            "warehouse_id": 1,
            "api_key": "xxx"
        }

        Returns:
            dict: Lote de registros serializados
        """
        try:
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            model_name = data.get('model')
            limit = min(data.get('limit', 500), 1000)  # Máximo 1000 por lote
            offset = data.get('offset', 0)

            if not model_name:
                return self._json_response({'success': False, 'error': 'model es requerido'})

            # Mapeo de modelos permitidos y sus dominios
            allowed_models = {
                'product.category': [],
                'uom.uom': [],
                'account.tax': [('active', '=', True), ('type_tax_use', '=', 'sale')],
                'account.fiscal.position': [('active', '=', True)],
                'pos.payment.method': [('active', '=', True)],
                'res.partner': [('active', '=', True)],
                'product.pricelist': [('active', '=', True)],
                'product.template': [('available_in_pos', '=', True)],
                'product.product': [('available_in_pos', '=', True)],
                'product.pricelist.item': [],
                'loyalty.program': [('active', '=', True)],
                'loyalty.rule': [],
                'loyalty.reward': [],
            }

            if model_name not in allowed_models:
                return self._json_response({
                    'success': False,
                    'error': f'Modelo {model_name} no permitido para migración'
                })

            # Verificar que el modelo existe
            if model_name not in request.env:
                return self._json_response({
                    'success': False,
                    'error': f'Modelo {model_name} no existe'
                })

            Model = request.env[model_name].sudo()
            domain = allowed_models[model_name]

            total = Model.search_count(domain)

            # Para categorías, ordenar por jerarquía (padres primero)
            if model_name == 'product.category':
                order = 'parent_path asc, id asc'
            else:
                order = 'id asc'

            records = Model.search(domain, limit=limit, offset=offset, order=order)

            # Serializar registros
            SyncManager = request.env['pos.sync.manager'].sudo()
            records_data = []

            for record in records:
                records_data.append(
                    self._serialize_for_migration(record, model_name, SyncManager)
                )

            return self._json_response({
                'success': True,
                'model': model_name,
                'total': total,
                'count': len(records_data),
                'offset': offset,
                'has_more': (offset + len(records_data)) < total,
                'records': records_data,
            })

        except Exception as e:
            _logger.error(f'Error en pull_migration_batch: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    def _serialize_for_migration(self, record, model_name, SyncManager):
        """
        Serializa un registro para migración.
        Usa métodos especializados cuando existen, o serialización genérica.
        """
        # Métodos especializados por modelo
        if model_name == 'product.product':
            data = SyncManager.serialize_product(record)
            # Agregar campos adicionales para migración
            data['default_code'] = record.default_code
            data['taxes_id'] = [{'id': t.id, 'name': t.name} for t in record.taxes_id]
            return data
        elif model_name == 'product.template':
            return self._serialize_product_template(record)
        elif model_name == 'res.partner':
            return SyncManager.serialize_partner(record)
        elif model_name == 'product.pricelist':
            return SyncManager.serialize_pricelist(record)
        elif model_name == 'account.fiscal.position':
            return SyncManager.serialize_fiscal_position(record)
        elif model_name == 'loyalty.program':
            return SyncManager.serialize_loyalty_program(record)
        elif model_name == 'institution':
            return SyncManager.serialize_institution(record)
        elif model_name == 'institution.client':
            return SyncManager.serialize_institution_client(record)

        # Serialización genérica para otros modelos
        return self._serialize_generic(record, model_name)

    def _serialize_product_template(self, record):
        """Serializa un product.template para migración."""
        return {
            'id': record.id,
            'id_database_old': record.id,
            'name': record.name,
            'default_code': record.default_code,
            'type': record.type,
            'categ_id': record.categ_id.id if record.categ_id else False,
            'categ_name': record.categ_id.complete_name if record.categ_id else False,
            'list_price': record.list_price,
            'standard_price': record.standard_price,
            'uom_id': record.uom_id.id if record.uom_id else False,
            'uom_name': record.uom_id.name if record.uom_id else False,
            'uom_po_id': record.uom_po_id.id if record.uom_po_id else False,
            'uom_po_name': record.uom_po_id.name if record.uom_po_id else False,
            'available_in_pos': record.available_in_pos,
            'sale_ok': record.sale_ok,
            'purchase_ok': record.purchase_ok,
            'active': record.active,
            'taxes_id': [{'id': t.id, 'name': t.name} for t in record.taxes_id],
            'barcode': record.barcode if hasattr(record, 'barcode') else False,
            'pos_categ_ids': [c.id for c in record.pos_categ_ids] if hasattr(record, 'pos_categ_ids') else [],
        }

    def _serialize_generic(self, record, model_name):
        """
        Serialización genérica para modelos sin método especializado.
        Solo incluye campos básicos para evitar problemas.
        """
        data = {
            'id': record.id,
            'id_database_old': record.id,
        }

        # Campos comunes
        if hasattr(record, 'name'):
            data['name'] = record.name
        if hasattr(record, 'active'):
            data['active'] = record.active
        if hasattr(record, 'sequence'):
            data['sequence'] = record.sequence
        if hasattr(record, 'write_date'):
            data['write_date'] = record.write_date.isoformat() if record.write_date else None

        # Campos específicos por modelo
        if model_name == 'product.category':
            data['complete_name'] = record.complete_name
            data['parent_id'] = record.parent_id.id if record.parent_id else False
            data['parent_name'] = record.parent_id.complete_name if record.parent_id else False

        elif model_name == 'uom.uom':
            data['category_id'] = record.category_id.id if record.category_id else False
            data['category_name'] = record.category_id.name if record.category_id else False
            data['factor'] = record.factor
            data['factor_inv'] = record.factor_inv
            data['uom_type'] = record.uom_type
            data['rounding'] = record.rounding

        elif model_name == 'account.tax':
            data['amount'] = record.amount
            data['amount_type'] = record.amount_type
            data['type_tax_use'] = record.type_tax_use
            data['price_include'] = record.price_include
            data['include_base_amount'] = record.include_base_amount
            data['description'] = record.description

        elif model_name == 'pos.payment.method':
            data['is_cash_count'] = record.is_cash_count
            data['split_transactions'] = record.split_transactions
            # Incluir nombre del journal para buscar por nombre en destino
            data['journal_id'] = record.journal_id.id if record.journal_id else False
            data['journal_name'] = record.journal_id.name if record.journal_id else False
            data['journal_code'] = record.journal_id.code if record.journal_id else False

        elif model_name == 'product.pricelist.item':
            data['pricelist_id'] = record.pricelist_id.id if record.pricelist_id else False
            data['pricelist_name'] = record.pricelist_id.name if record.pricelist_id else False
            data['product_tmpl_id'] = record.product_tmpl_id.id if record.product_tmpl_id else False
            data['product_id'] = record.product_id.id if record.product_id else False
            data['categ_id'] = record.categ_id.id if record.categ_id else False
            data['min_quantity'] = record.min_quantity
            data['applied_on'] = record.applied_on
            data['compute_price'] = record.compute_price
            data['fixed_price'] = record.fixed_price
            data['percent_price'] = record.percent_price
            data['date_start'] = record.date_start.isoformat() if record.date_start else None
            data['date_end'] = record.date_end.isoformat() if record.date_end else None

        elif model_name in ('loyalty.rule', 'loyalty.reward'):
            data['program_id'] = record.program_id.id if record.program_id else False
            data['program_name'] = record.program_id.name if record.program_id else False

        return data

    # ==================== ENDPOINTS DE INSTITUCIONES (CRÉDITOS) ====================

    @http.route('/pos_offline_sync/pull_institutions', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_institutions(self, **kwargs):
        """
        Endpoint para descargar instituciones (créditos/descuentos) desde el cloud.

        Las instituciones tienen información sobre:
        - Descuentos adicionales para clientes institucionales
        - Créditos con día de corte y cupo asignado
        - Relación con puntos de venta autorizados

        Payload esperado:
        {
            "warehouse_id": 1,
            "last_sync": "2024-01-15T10:30:00",
            "limit": 100,
            "offset": 0,
            "pos_config_id": 1  // Opcional: filtrar por POS específico
        }

        Returns:
            dict: Instituciones con sus clientes asociados
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            last_sync = data.get('last_sync')
            limit = data.get('limit', 100)
            offset = data.get('offset', 0)
            pos_config_id = data.get('pos_config_id')

            # Construir dominio
            domain = [('pvp', '=', '1')]  # Solo instituciones activas

            # Filtrar por pos.config si se especifica
            if pos_config_id:
                domain.append(('pos_ids', 'in', [pos_config_id]))

            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    domain.append(('write_date', '>', last_sync_dt))
                except ValueError:
                    pass

            Institution = request.env['institution'].sudo()

            total = Institution.search_count(domain)
            institutions = Institution.search(domain, limit=limit, offset=offset, order='write_date asc')

            # Serializar instituciones
            institutions_data = []
            for inst in institutions:
                inst_data = {
                    'id': inst.id,
                    'id_institutions': inst.id_institutions,
                    'name': inst.name,
                    'ruc_institution': inst.ruc_institution,
                    'agreement_date': inst.agreement_date.isoformat() if inst.agreement_date else None,
                    'address': inst.address,
                    'type_credit_institution': inst.type_credit_institution,
                    'cellphone': inst.cellphone,
                    'court_day': inst.court_day,
                    'additional_discount_percentage': inst.additional_discount_percentage,
                    'pvp': inst.pvp,
                    'pos_ids': inst.pos_ids.ids,
                    'write_date': inst.write_date.isoformat() if inst.write_date else None,
                    # Lista de clientes asociados con sus cupos
                    'clients': []
                }

                # Agregar clientes de la institución
                for client in inst.institution_client_ids:
                    client_data = {
                        'id': client.id,
                        'partner_id': client.partner_id.id,
                        'partner_vat': client.partner_id.vat,
                        'partner_name': client.partner_id.name,
                        'available_amount': client.available_amount,
                        'sale': client.sale,
                    }
                    inst_data['clients'].append(client_data)

                institutions_data.append(inst_data)

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'pull_institutions',
                    f'Enviadas {len(institutions_data)} instituciones'
                )

            return self._json_response({
                'success': True,
                'total': total,
                'count': len(institutions_data),
                'offset': offset,
                'institutions': institutions_data,
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo instituciones: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    @http.route('/pos_offline_sync/pull_institution_clients', type='http', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def pull_institution_clients(self, **kwargs):
        """
        Endpoint para descargar clientes de instituciones específicas.

        Útil para sincronizar solo los clientes de una institución sin
        descargar toda la información de instituciones.

        Payload esperado:
        {
            "warehouse_id": 1,
            "institution_id": 5,  // ID de la institución
            "partner_vat": "1234567890"  // Opcional: filtrar por VAT del cliente
        }

        Returns:
            dict: Clientes de la institución
        """
        try:
            # Parsear JSON del body
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = kwargs

            if not self._validate_api_auth(data):
                return self._json_response({'success': False, 'error': 'Autenticación inválida'})

            warehouse_id = data.get('warehouse_id')
            institution_id = data.get('institution_id')
            partner_vat = data.get('partner_vat')

            InstitutionClient = request.env['institution.client'].sudo()

            # Construir dominio
            domain = []

            if institution_id:
                domain.append(('institution_id', '=', institution_id))

            if partner_vat:
                domain.append(('partner_id.vat', '=', partner_vat))

            clients = InstitutionClient.search(domain)

            # Serializar clientes
            clients_data = []
            for client in clients:
                client_data = {
                    'id': client.id,
                    'institution_id': client.institution_id.id,
                    'institution_name': client.institution_id.name,
                    'institution_type': client.institution_id.type_credit_institution,
                    'institution_discount': client.institution_id.additional_discount_percentage,
                    'court_day': client.institution_id.court_day,
                    'partner_id': client.partner_id.id,
                    'partner_vat': client.partner_id.vat,
                    'partner_name': client.partner_id.name,
                    'available_amount': client.available_amount,
                    'sale': client.sale,
                }
                clients_data.append(client_data)

            # Registrar en log
            if warehouse_id:
                self._log_sync_operation(
                    warehouse_id, 'pull_institution_clients',
                    f'Enviados {len(clients_data)} clientes institucionales'
                )

            return self._json_response({
                'success': True,
                'count': len(clients_data),
                'clients': clients_data,
                'sync_date': fields.Datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f'Error obteniendo clientes institucionales: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            return self._json_response({'success': False, 'error': str(e)})

    # ==================== MÉTODOS AUXILIARES ====================

    def _json_response(self, data):
        """
        Crea una respuesta HTTP con formato JSON.

        Args:
            data: Diccionario a convertir en JSON

        Returns:
            werkzeug.wrappers.Response: Respuesta HTTP
        """
        return request.make_response(
            json.dumps(data, default=str),
            headers=[('Content-Type', 'application/json')]
        )

    def _validate_api_auth(self, kwargs):
        """
        Valida la autenticación de la API.

        Args:
            kwargs: Parámetros de la solicitud

        Returns:
            bool: True si la autenticación es válida
        """
        # Obtener API key del header o parámetros
        api_key = kwargs.get('api_key')
        if not api_key:
            auth_header = request.httprequest.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                api_key = auth_header[7:]

        if not api_key:
            # Si no hay API key, permitir en desarrollo
            # En producción, descomentar el return False
            # return False
            return True

        # Validar API key contra configuraciones
        config = request.env['pos.sync.config'].sudo().search([
            ('api_key', '=', api_key),
            ('active', '=', True),
        ], limit=1)

        return bool(config)

    def _prepare_create_vals(self, model_name, data):
        """
        Prepara valores para crear un registro.

        Args:
            model_name: Nombre del modelo
            data: Datos del registro

        Returns:
            dict: Valores preparados
        """
        vals = dict(data)

        # Remover campos internos
        for key in list(vals.keys()):
            if key.startswith('_'):
                del vals[key]

        return vals

    def _prepare_write_vals(self, model_name, data):
        """
        Prepara valores para actualizar un registro.

        Args:
            model_name: Nombre del modelo
            data: Datos del registro

        Returns:
            dict: Valores preparados
        """
        vals = dict(data)

        # Remover campos que no deben actualizarse
        readonly_fields = ['id', 'create_date', 'create_uid', 'write_date', 'write_uid']
        for field in readonly_fields:
            vals.pop(field, None)

        # Remover campos internos
        for key in list(vals.keys()):
            if key.startswith('_'):
                del vals[key]

        return vals

    def _find_existing_record(self, Model, data):
        """
        Busca un registro existente por diferentes criterios.

        Args:
            Model: Modelo Odoo
            data: Datos del registro

        Returns:
            record: Registro encontrado o None
        """
        # Por cloud_sync_id
        if hasattr(Model, 'cloud_sync_id') and data.get('cloud_sync_id'):
            record = Model.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)
            if record:
                return record

        # Por id_database_old
        if hasattr(Model, 'id_database_old') and data.get('id_database_old'):
            record = Model.search([
                ('id_database_old', '=', data['id_database_old'])
            ], limit=1)
            if record:
                return record

        # Por VAT para partners
        if Model._name == 'res.partner' and data.get('vat'):
            record = Model.search([('vat', '=', data['vat'])], limit=1)
            if record:
                return record

        # Por barcode para productos
        if Model._name == 'product.product' and data.get('barcode'):
            record = Model.search([('barcode', '=', data['barcode'])], limit=1)
            if record:
                return record

        # Por pos_reference para órdenes
        if Model._name == 'pos.order' and data.get('pos_reference'):
            record = Model.search([
                ('pos_reference', '=', data['pos_reference'])
            ], limit=1)
            if record:
                return record

        return None

    def _log_sync_operation(self, warehouse_id, action, message):
        """
        Registra una operación de sincronización en el log.

        Args:
            warehouse_id: ID del almacén
            action: Tipo de acción
            message: Mensaje descriptivo
        """
        try:
            config = request.env['pos.sync.config'].sudo().get_config_for_warehouse(
                warehouse_id
            )
            if config:
                request.env['pos.sync.log'].sudo().log(
                    sync_config_id=config.id,
                    action=action,
                    message=message,
                    level='info',
                )
        except Exception as e:
            _logger.error(f'Error registrando log: {str(e)}')
