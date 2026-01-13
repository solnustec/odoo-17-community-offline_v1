# -*- coding: utf-8 -*-
import json
import logging
import requests
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosSyncManager(models.Model):
    """
    Gestor de sincronización para POS Offline.

    Coordina la sincronización bidireccional entre el POS offline
    y el servidor cloud.
    """
    _name = 'pos.sync.manager'
    _description = 'Gestor de Sincronización POS'

    # Mapeo de modelos para sincronización
    MODEL_PRIORITY = {
        'res.partner': 1,
        'product.product': 2,
        'product.template': 2,
        'stock.quant': 3,
        'loyalty.program': 4,
        'loyalty.rule': 5,
        'loyalty.reward': 6,
        'hr.employee': 7,
        'pos.payment.method': 8,
        'institution': 9,  # Instituciones de crédito/descuento
        'institution.client': 10,  # Relación cliente-institución con saldo
        'pos.session': 11,
        'pos.order': 12,
        'json.storage': 13,  # Sincronizar después de pos.order
        'json.note.credit': 14,
    }

    # Campos para serialización por modelo
    MODEL_FIELDS = {
        'pos.order': [
            'name', 'date_order', 'pos_reference', 'partner_id',
            'amount_total', 'amount_paid', 'amount_return', 'amount_tax',
            'state', 'note', 'fiscal_position_id', 'pricelist_id',
            'session_id', 'employee_id', 'lines', 'payment_ids',
            'check_info_json', 'card_info_json', 'key_order',
        ],
        'pos.order.line': [
            'full_product_name', 'product_id', 'qty', 'price_unit',
            'price_subtotal', 'price_subtotal_incl', 'discount',
            'tax_ids', 'pack_lot_ids', 'reward_product_id', 'product_free',
        ],
        'res.partner': [
            'name', 'email', 'phone', 'mobile', 'vat', 'street',
            'city', 'country_id', 'state_id', 'zip', 'type',
            'id_database_old',
        ],
        'product.product': [
            'name', 'default_code', 'barcode', 'list_price',
            'standard_price', 'categ_id', 'type', 'uom_id',
            'available_in_pos', 'id_database_old',
        ],
        'stock.quant': [
            'product_id', 'location_id', 'quantity', 'reserved_quantity',
            'lot_id',
        ],
        'json.storage': [
            'json_data', 'pos_order_id', 'pos_order', 'employee',
            'id_point_of_sale', 'sync_date', 'db_key', 'sent',
            'client_invoice', 'id_database_old_invoice_client', 'is_access_key',
        ],
        'json.note.credit': [
            'json_data', 'pos_order_id', 'id_point_of_sale',
            'sync_date', 'date_invoices', 'db_key', 'sent', 'is_access_key',
        ],
    }

    @api.model
    def execute_sync(self, sync_config):
        """
        Ejecuta el proceso de sincronización completo.

        Args:
            sync_config: Registro pos.sync.config

        Returns:
            dict: Resultado de la sincronización
        """
        _logger.info(f'Iniciando sincronización para {sync_config.name}')

        result = {
            'success': True,
            'uploaded': 0,
            'downloaded': 0,
            'errors': [],
            'start_time': datetime.now(),
        }

        sync_config_id = sync_config.id
        error_occurred = False
        error_message = None

        try:
            # Usar sudo() para evitar problemas de permisos
            sync_config_sudo = sync_config.sudo()
            sync_config_sudo.write({'sync_status': 'syncing'})

            # 0. Limpiar registros json.storage de la cola (ahora se sincronizan como parte de pos.order)
            try:
                SyncQueue = self.env['pos.sync.queue'].sudo()
                cleaned = SyncQueue.cleanup_json_storage_queue()
                if cleaned > 0:
                    _logger.info(f'Limpiados {cleaned} registros json.storage/json.note.credit de la cola')
            except Exception as e:
                _logger.warning(f'Error limpiando cola de json.storage: {e}')

            # 1. Subir datos locales al cloud (PUSH)
            if sync_config.operation_mode in ['hybrid', 'sync_on_demand']:
                push_result = self._push_to_cloud(sync_config)
                result['uploaded'] = push_result.get('count', 0)
                if push_result.get('errors'):
                    result['errors'].extend(push_result['errors'])

            # 2. Descargar datos del cloud (PULL)
            if sync_config.operation_mode in ['hybrid', 'sync_on_demand']:
                pull_result = self._pull_from_cloud(sync_config)
                result['downloaded'] = pull_result.get('count', 0)
                if pull_result.get('errors'):
                    result['errors'].extend(pull_result['errors'])

            # Actualizar estado exitoso
            sync_config_sudo.write({
                'sync_status': 'success' if not result['errors'] else 'error',
                'last_sync_date': fields.Datetime.now(),
                'last_error_message': '\n'.join(result['errors']) if result['errors'] else False,
                'total_synced_orders': sync_config.total_synced_orders + result['uploaded'],
            })

            result['end_time'] = datetime.now()
            result['duration'] = (result['end_time'] - result['start_time']).total_seconds()

            _logger.info(
                f'Sincronización completada: {result["uploaded"]} subidos, '
                f'{result["downloaded"]} descargados, {len(result["errors"])} errores'
            )

        except Exception as e:
            _logger.error(f'Error en sincronización: {str(e)}')
            error_occurred = True
            error_message = str(e)
            result['success'] = False
            result['errors'].append(str(e))

        # Si hubo error, intentar actualizar el estado usando un nuevo cursor
        # para evitar problemas con transacciones abortadas
        if error_occurred:
            try:
                # Intentar rollback para limpiar la transacción abortada
                self.env.cr.rollback()
                # Ahora podemos escribir el estado de error
                sync_config_fresh = self.env['pos.sync.config'].sudo().browse(sync_config_id)
                if sync_config_fresh.exists():
                    sync_config_fresh.write({
                        'sync_status': 'error',
                        'last_error_message': error_message,
                    })
            except Exception as write_error:
                _logger.error(f'No se pudo actualizar estado de error: {str(write_error)}')

        # Registrar en log
        try:
            self._create_sync_log(sync_config, result)
        except Exception as log_error:
            _logger.error(f'Error creando log de sincronización: {str(log_error)}')

        return result

    def _push_to_cloud(self, sync_config):
        """
        Sube registros pendientes al servidor cloud.

        Args:
            sync_config: Registro pos.sync.config

        Returns:
            dict: Resultado del push
        """
        result = {'count': 0, 'errors': []}
        SyncQueue = self.env['pos.sync.queue']

        # Obtener registros listos para sincronizar
        pending = SyncQueue.get_ready_for_sync(
            sync_config.warehouse_id.id,
            limit=sync_config.batch_size
        )

        if not pending:
            _logger.info('No hay registros pendientes para sincronizar')
            return result

        # Agrupar por modelo para optimizar
        by_model = {}
        for record in pending:
            if record.model_name not in by_model:
                by_model[record.model_name] = []
            by_model[record.model_name].append(record)

        # Procesar en orden de prioridad
        sorted_models = sorted(
            by_model.keys(),
            key=lambda m: self.MODEL_PRIORITY.get(m, 99)
        )

        for model_name in sorted_models:
            records = by_model[model_name]
            try:
                model_result = self._push_model_records(
                    sync_config, model_name, records
                )
                result['count'] += model_result.get('count', 0)
                if model_result.get('errors'):
                    result['errors'].extend(model_result['errors'])
            except Exception as e:
                error_msg = f'Error sincronizando {model_name}: {str(e)}'
                _logger.error(error_msg)
                result['errors'].append(error_msg)
                # Marcar registros con error
                for record in records:
                    record.mark_as_error(str(e))

        return result

    def _push_model_records(self, sync_config, model_name, queue_records):
        """
        Sincroniza un lote de registros de un modelo específico.

        Args:
            sync_config: Registro pos.sync.config
            model_name: Nombre del modelo
            queue_records: Lista de registros pos.sync.queue

        Returns:
            dict: Resultado de la sincronización
        """
        result = {'count': 0, 'errors': []}

        # Preparar payload
        payload = {
            'model': model_name,
            'warehouse_id': sync_config.warehouse_id.id,
            'warehouse_name': sync_config.warehouse_id.name,
            'records': [],
        }

        for queue_record in queue_records:
            queue_record.mark_as_processing()
            payload['records'].append({
                'queue_id': queue_record.id,
                'local_id': queue_record.record_id,
                'operation': queue_record.operation,
                'data': queue_record.get_data(),
            })

        # Enviar al cloud
        try:
            response = self._send_to_cloud(
                sync_config,
                '/pos_offline_sync/push',
                payload
            )

            if response.get('success'):
                # Procesar respuestas individuales
                for item in response.get('results', []):
                    queue_id = item.get('queue_id')
                    queue_record = self.env['pos.sync.queue'].browse(queue_id)

                    if item.get('success'):
                        queue_record.mark_as_synced(
                            cloud_record_id=item.get('cloud_id'),
                            response=item
                        )
                        result['count'] += 1
                    else:
                        queue_record.mark_as_error(item.get('error', 'Error desconocido'))
                        result['errors'].append(
                            f'{model_name}#{item.get("local_id")}: {item.get("error")}'
                        )
            else:
                error_msg = response.get('error', 'Error en respuesta del servidor')
                for queue_record in queue_records:
                    queue_record.mark_as_error(error_msg)
                result['errors'].append(error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = f'Error de conexión: {str(e)}'
            for queue_record in queue_records:
                queue_record.mark_as_error(error_msg)
            result['errors'].append(error_msg)

        return result

    def _pull_from_cloud(self, sync_config):
        """
        Descarga actualizaciones desde el servidor cloud.

        Args:
            sync_config: Registro pos.sync.config

        Returns:
            dict: Resultado del pull
        """
        result = {'count': 0, 'errors': []}

        entities = sync_config.get_sync_entities()
        if not entities:
            return result

        payload = {
            'warehouse_id': sync_config.warehouse_id.id,
            'entities': entities,
            'last_sync': sync_config.last_sync_date.isoformat() if sync_config.last_sync_date else None,
        }

        try:
            response = self._send_to_cloud(
                sync_config,
                '/pos_offline_sync/pull',
                payload
            )

            if response.get('success'):
                # Procesar actualizaciones normales
                for model_name, records in response.get('data', {}).items():
                    try:
                        count = self._apply_cloud_updates(model_name, records, sync_config)
                        result['count'] += count
                    except Exception as e:
                        error_msg = f'Error aplicando {model_name}: {str(e)}'
                        _logger.error(error_msg)
                        result['errors'].append(error_msg)

                # Procesar eliminaciones
                for model_name, deletions in response.get('deletions', {}).items():
                    try:
                        deleted_count = self._apply_cloud_deletions(model_name, deletions, sync_config)
                        _logger.info(f'Aplicadas {deleted_count} eliminaciones de {model_name}')
                    except Exception as e:
                        error_msg = f'Error aplicando eliminaciones de {model_name}: {str(e)}'
                        _logger.error(error_msg)
                        result['errors'].append(error_msg)
            else:
                result['errors'].append(response.get('error', 'Error en pull'))

        except requests.exceptions.RequestException as e:
            result['errors'].append(f'Error de conexión: {str(e)}')

        return result

    def _apply_cloud_updates(self, model_name, records, sync_config):
        """
        Aplica las actualizaciones recibidas del cloud con transacciones atómicas.
        OPTIMIZADO: Usa savepoint para garantizar atomicidad por lote.

        Args:
            model_name: Nombre del modelo
            records: Lista de registros a aplicar
            sync_config: Configuración de sincronización

        Returns:
            int: Número de registros procesados
        """
        if not records:
            return 0

        Model = self.env[model_name].sudo()
        count = 0

        # OPTIMIZACIÓN: Deduplicar usando dict comprehension (más eficiente en memoria)
        # Para pos.order usa pos_reference como clave alternativa si no hay id
        unique_records = {}
        for record_data in records:
            record_id = record_data.get('id')
            # Fallback para pos.order: usar pos_reference como clave única
            if not record_id and model_name == 'pos.order':
                record_id = record_data.get('pos_reference') or record_data.get('name')
            if record_id:
                unique_records[record_id] = record_data  # El último sobrescribe
            else:
                # Si no hay clave única, agregar de todos modos con índice
                unique_records[f'_no_key_{len(unique_records)}'] = record_data

        unique_records_list = list(unique_records.values())

        _logger.info(f'Procesando {len(unique_records_list)} registros únicos de {model_name} (de {len(records)} totales)')

        # Logging específico para institution.client
        if model_name == 'institution.client' and unique_records_list:
            _logger.info(
                f'=== PULL institution.client - Recibidos {len(unique_records_list)} registros ===\n'
                f'  IDs: {[r.get("id") for r in unique_records_list[:10]]}...'
            )
            for rec in unique_records_list[:5]:  # Mostrar primeros 5
                _logger.info(
                    f'  - id={rec.get("id")}, partner_vat={rec.get("partner_vat")}, '
                    f'institution={rec.get("institution_id_institutions")}, '
                    f'amount={rec.get("available_amount")}'
                )

        # OPTIMIZACIÓN: Procesar en lotes con savepoint para atomicidad
        # Usar batch_size configurable (default 50 si no está configurado)
        batch_size = sync_config.batch_size if sync_config and sync_config.batch_size else 50
        for i in range(0, len(unique_records_list), batch_size):
            batch = unique_records_list[i:i + batch_size]
            try:
                # Usar savepoint para atomicidad del lote
                with self.env.cr.savepoint():
                    for record_data in batch:
                        count += self._apply_single_record(
                            Model, model_name, record_data, sync_config
                        )
            except Exception as e:
                _logger.error(f'Error en lote {i//batch_size + 1} de {model_name}: {str(e)}')
                # Procesar registros individualmente si el lote falla
                for record_data in batch:
                    try:
                        with self.env.cr.savepoint():
                            count += self._apply_single_record(
                                Model, model_name, record_data, sync_config
                            )
                    except Exception as e2:
                        _logger.error(f'Error procesando {model_name}: {str(e2)}')
                        continue

        return count

    def _apply_single_record(self, Model, model_name, record_data, sync_config):
        """
        Aplica un solo registro del cloud.

        Args:
            Model: Modelo Odoo
            model_name: Nombre del modelo
            record_data: Datos del registro
            sync_config: Configuración de sincronización

        Returns:
            int: 1 si se procesó correctamente, 0 si no
        """
        # Hacer una copia para no modificar el original
        data = dict(record_data)
        cloud_id = data.pop('id', None)
        operation = data.pop('_operation', 'create_or_update')

        if operation == 'unlink':
            # Buscar y eliminar
            local = self._find_local_record(Model, cloud_id, data)
            if local:
                local.unlink()
                return 1
            return 0

        # Manejo especial para pos.order - usar deserialize_order
        if model_name == 'pos.order':
            data['id'] = cloud_id
            self.deserialize_order(data, sync_config)
            return 1

        # Manejo especial para res.partner - usar deserialize_partner
        if model_name == 'res.partner':
            data['id'] = cloud_id
            self.deserialize_partner(data, sync_config)
            return 1

        # Manejo especial para product.product
        if model_name == 'product.product':
            data['id'] = cloud_id
            self.deserialize_product(data, sync_config)
            return 1

        # Manejo especial para product.pricelist
        if model_name == 'product.pricelist':
            data['id'] = cloud_id
            self.deserialize_pricelist(data, sync_config)
            return 1

        # Manejo especial para loyalty.program
        if model_name == 'loyalty.program':
            data['id'] = cloud_id
            self.deserialize_loyalty_program(data, sync_config)
            return 1

        # Manejo especial para account.fiscal.position
        if model_name == 'account.fiscal.position':
            data['id'] = cloud_id
            self.deserialize_fiscal_position(data, sync_config)
            return 1

        # Manejo especial para pos.session
        if model_name == 'pos.session':
            data['id'] = cloud_id
            self.deserialize_session(data, sync_config)
            return 1

        # Manejo especial para stock.picking (transferencias)
        if model_name == 'stock.picking':
            data['id'] = cloud_id
            self.deserialize_stock_picking(data, sync_config)
            return 1

        # Manejo especial para json.storage
        if model_name == 'json.storage':
            data['id'] = cloud_id
            self.deserialize_json_storage(data, sync_config)
            return 1

        # Manejo especial para json.note.credit
        if model_name == 'json.note.credit':
            data['id'] = cloud_id
            self.deserialize_json_note_credit(data, sync_config)
            return 1

        # Manejo especial para institution
        if model_name == 'institution':
            data['id'] = cloud_id
            self.deserialize_institution(data, sync_config)
            return 1

        # Manejo especial para institution.client
        if model_name == 'institution.client':
            data['id'] = cloud_id
            self.deserialize_institution_client(data, sync_config)
            return 1

        # Crear o actualizar otros modelos
        local = self._find_local_record(Model, cloud_id, data)
        if local:
            vals = self._prepare_write_vals(model_name, data)
            if vals:
                local.write(vals)
        else:
            vals = self._prepare_create_vals(model_name, data, cloud_id)
            if vals:
                Model.create(vals)
        return 1

    def _apply_cloud_deletions(self, model_name, deletions, sync_config):
        """
        Aplica eliminaciones recibidas del cloud.

        Args:
            model_name: Nombre del modelo
            deletions: Lista de registros a eliminar
            sync_config: Configuración de sincronización

        Returns:
            int: Número de registros eliminados
        """
        if not deletions:
            return 0

        count = 0
        Model = self.env[model_name].sudo()

        for deletion_data in deletions:
            try:
                # Buscar el registro local usando los identificadores
                local_record = None

                if model_name == 'institution.client':
                    # Buscar por institution + partner
                    partner_vat = deletion_data.get('partner_vat')
                    institution_code = deletion_data.get('institution_id_institutions')

                    if partner_vat and institution_code:
                        partner = self.env['res.partner'].sudo().search([
                            ('vat', '=', partner_vat)
                        ], limit=1)
                        institution = self.env['institution'].sudo().search([
                            ('id_institutions', '=', institution_code)
                        ], limit=1)

                        if partner and institution:
                            local_record = Model.search([
                                ('partner_id', '=', partner.id),
                                ('institution_id', '=', institution.id)
                            ], limit=1)

                    # Fallback: buscar por cloud_sync_id
                    if not local_record and deletion_data.get('id'):
                        if 'cloud_sync_id' in Model._fields:
                            local_record = Model.search([
                                ('cloud_sync_id', '=', deletion_data['id'])
                            ], limit=1)
                else:
                    # Para otros modelos, buscar por id o cloud_sync_id
                    record_id = deletion_data.get('id')
                    if record_id:
                        if 'cloud_sync_id' in Model._fields:
                            local_record = Model.search([
                                ('cloud_sync_id', '=', record_id)
                            ], limit=1)
                        if not local_record:
                            local_record = Model.browse(record_id)
                            if not local_record.exists():
                                local_record = None

                if local_record:
                    record_ref = f'{local_record.partner_id.name} - {local_record.institution_id.name}' if model_name == 'institution.client' else str(local_record.id)
                    _logger.info(
                        f'Eliminando {model_name} local: {record_ref} '
                        f'(recibido del cloud)'
                    )
                    local_record.with_context(skip_sync_queue=True).unlink()
                    count += 1
                else:
                    _logger.debug(
                        f'Registro {model_name} a eliminar no encontrado localmente: '
                        f'{deletion_data}'
                    )

            except Exception as e:
                _logger.error(f'Error eliminando {model_name}: {str(e)}')
                continue

        return count

    def _find_local_record(self, Model, cloud_id, record_data):
        """Busca un registro local por diferentes criterios."""
        # Primero por cloud_id si existe el campo en el modelo
        if 'cloud_sync_id' in Model._fields and cloud_id:
            record = Model.search([('cloud_sync_id', '=', cloud_id)], limit=1)
            if record:
                return record

        # Por id_database_old
        if 'id_database_old' in Model._fields and record_data.get('id_database_old'):
            record = Model.search([
                ('id_database_old', '=', str(record_data['id_database_old']))
            ], limit=1)
            if record:
                return record

        # Por identificadores únicos según el modelo
        if Model._name == 'res.partner' and record_data.get('vat'):
            record = Model.search([('vat', '=', record_data['vat'])], limit=1)
            if record:
                return record

        if Model._name == 'product.product' and record_data.get('barcode'):
            record = Model.search([('barcode', '=', record_data['barcode'])], limit=1)
            if record:
                return record

        # Para product.product, buscar por default_code o ID
        if Model._name == 'product.product':
            if record_data.get('default_code'):
                record = Model.search([('default_code', '=', record_data['default_code'])], limit=1)
                if record:
                    return record
            # Buscar por ID directo (si es el mismo sistema)
            if cloud_id:
                record = Model.browse(cloud_id)
                if record.exists():
                    return record

        # Para stock.quant, buscar por product_id y location_id
        if Model._name == 'stock.quant':
            product_id = record_data.get('product_id')
            location_id = record_data.get('location_id')
            if product_id and location_id:
                record = Model.search([
                    ('product_id', '=', product_id),
                    ('location_id', '=', location_id),
                ], limit=1)
                if record:
                    return record

        return None

    def _prepare_write_vals(self, model_name, data):
        """Prepara valores para escritura, filtrando campos no permitidos."""
        vals = {}
        allowed_fields = self.MODEL_FIELDS.get(model_name, [])

        # Campos de fecha/datetime que necesitan conversión
        datetime_fields = {'date_order', 'create_date', 'write_date', 'date', 'last_sync_date'}

        # Campos complejos que no se pueden escribir directamente (listas de dicts, etc.)
        # Estos deben manejarse de forma especial por deserialize_order/deserialize_partner
        skip_fields = {
            'lines', 'payments', 'payment_ids', 'tax_ids', 'pack_lot_ids',
            'order_line', 'invoice_line_ids', 'move_ids', 'picking_ids',
            # Campos informativos que no deben escribirse
            'partner_vat', 'session_name', 'config_name', 'employee_name',
            'country_name', 'country_code', 'state_name', 'state_code',
            'payment_method_name', 'product_barcode', 'product_name',
            'property_product_pricelist_name', 'display_name',
            'l10n_latam_identification_type_name',
        }

        for key, value in data.items():
            # Saltar campos que empiezan con _
            if key.startswith('_'):
                continue

            # Saltar campos complejos
            if key in skip_fields:
                continue

            # Saltar si el valor es una lista de dicts (relaciones complejas)
            if isinstance(value, list) and value and isinstance(value[0], dict):
                continue

            # Filtrar por campos permitidos si están definidos
            if allowed_fields and key not in allowed_fields:
                continue

            # Convertir fechas en formato ISO a formato Odoo
            if key in datetime_fields and value and isinstance(value, str):
                value = self._parse_datetime(value)

            vals[key] = value

        return vals

    def _parse_datetime(self, value):
        """
        Convierte un string de fecha a formato compatible con Odoo.

        Args:
            value: String de fecha en formato ISO u otro formato

        Returns:
            str: Fecha en formato '%Y-%m-%d %H:%M:%S' o el valor original
        """
        if not value:
            return value

        try:
            # Intentar parsear formato ISO con 'T'
            if 'T' in value:
                # Manejar diferentes formatos ISO
                if '.' in value:
                    # Con microsegundos: 2025-12-10T17:33:27.123456
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                else:
                    # Sin microsegundos: 2025-12-10T17:33:27
                    dt = datetime.fromisoformat(value)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                # Ya está en formato Odoo o similar
                return value
        except (ValueError, TypeError):
            # Si falla el parsing, retornar el valor original
            return value

    def _prepare_create_vals(self, model_name, data, cloud_id=None):
        """Prepara valores para creación."""
        vals = self._prepare_write_vals(model_name, data)

        # Solo agregar cloud_sync_id si el modelo tiene el campo
        if cloud_id:
            Model = self.env[model_name]
            if 'cloud_sync_id' in Model._fields:
                vals['cloud_sync_id'] = cloud_id

        return vals

    def _send_to_cloud(self, sync_config, endpoint, payload):
        """
        Envía datos al servidor cloud.

        Args:
            sync_config: Configuración de sincronización
            endpoint: Endpoint de la API
            payload: Datos a enviar

        Returns:
            dict: Respuesta del servidor
        """
        if not sync_config.cloud_url:
            raise UserError('No se ha configurado la URL del servidor cloud.')

        url = f'{sync_config.cloud_url.rstrip("/")}{endpoint}'

        headers = {
            'Content-Type': 'application/json',
        }
        if sync_config.api_key:
            headers['Authorization'] = f'Bearer {sync_config.api_key}'

        _logger.debug(f'Enviando a {url}: {json.dumps(payload, default=str)[:500]}...')

        # Usar data= con json.dumps(default=str) para manejar objetos no serializables
        response = requests.post(
            url,
            data=json.dumps(payload, default=str),
            headers=headers,
            timeout=sync_config.sync_timeout
        )
        response.raise_for_status()

        return response.json()

    def _create_sync_log(self, sync_config, result):
        """Crea un registro de log para la sincronización."""
        self.env['pos.sync.log'].create({
            'sync_config_id': sync_config.id,
            'action': 'full_sync',
            'message': (
                f'Sincronización completada. '
                f'Subidos: {result["uploaded"]}, '
                f'Descargados: {result["downloaded"]}, '
                f'Errores: {len(result["errors"])}'
            ),
            'level': 'error' if result['errors'] else 'info',
            'details': json.dumps({
                'uploaded': result['uploaded'],
                'downloaded': result['downloaded'],
                'errors': result['errors'],
                'duration': result.get('duration'),
            }, default=str),
        })

    @api.model
    def cron_sync_all(self):
        """
        Cron job para sincronizar todas las configuraciones activas.
        """
        configs = self.env['pos.sync.config'].get_active_configs()

        for config in configs:
            if config.operation_mode == 'offline':
                continue

            try:
                self.execute_sync(config)
            except Exception as e:
                _logger.error(f'Error en cron sync para {config.name}: {str(e)}')

    @api.model
    def serialize_order(self, order):
        """
        Serializa una orden POS para sincronización.
        MEJORADO: Incluye campos adicionales para reembolsos y posición fiscal.

        Args:
            order: Registro pos.order

        Returns:
            dict: Datos serializados
        """
        # Obtener el nombre correcto de la orden
        order_name = order.name
        if not order_name or order_name == '/':
            # Si el name es "/" intentar obtenerlo de pos_reference o construirlo
            if order.pos_reference:
                order_name = order.pos_reference
            elif order.session_id and order.config_id:
                # Construir nombre basado en config y secuencia
                order_name = f"{order.config_id.name}/{order.id}"

        data = {
            'id': order.id,  # CRÍTICO: Necesario para deduplicación en sincronización
            'name': order_name,
            'pos_reference': order.pos_reference,
            'date_order': order.date_order.isoformat() if order.date_order else None,
            'partner_id': order.partner_id.id if order.partner_id else None,
            'partner_vat': order.partner_id.vat if order.partner_id else None,
            'partner_cloud_sync_id': order.partner_id.cloud_sync_id if order.partner_id and hasattr(order.partner_id, 'cloud_sync_id') else None,
            'amount_total': order.amount_total,
            'amount_paid': order.amount_paid,
            'amount_return': order.amount_return,
            'amount_tax': order.amount_tax,
            'state': order.state,
            'note': order.note,
            # Datos de sesión - incluir ID, nombre y USUARIO
            'session_id': order.session_id.id if order.session_id else None,
            'session_name': order.session_id.name if order.session_id else None,
            'config_id': order.config_id.id if order.config_id else None,
            'config_name': order.config_id.name if order.config_id else None,
            # CRÍTICO: Usuario de la sesión (dependiente que hizo la venta)
            'user_id': order.session_id.user_id.id if order.session_id and order.session_id.user_id else None,
            'user_name': order.session_id.user_id.name if order.session_id and order.session_id.user_id else None,
            'user_login': order.session_id.user_id.login if order.session_id and order.session_id.user_id else None,
            # Empleado de la orden (puede ser diferente al usuario de sesión)
            'employee_id': order.employee_id.id if order.employee_id else None,
            'employee_name': order.employee_id.name if order.employee_id else None,
            # Cajero (para compatibilidad)
            'cashier_name': order.user_id.name if hasattr(order, 'user_id') and order.user_id else None,
            # Campos adicionales para pos_custom_check
            'check_info_json': order.check_info_json if hasattr(order, 'check_info_json') else None,
            'card_info_json': order.card_info_json if hasattr(order, 'card_info_json') else None,
            'key_order': order.key_order if hasattr(order, 'key_order') else None,
            # Campos de transferencia bancaria (almacenados en pos.order)
            'payment_transfer_number': order.payment_transfer_number if hasattr(order, 'payment_transfer_number') else None,
            'payment_bank_name': order.payment_bank_name if hasattr(order, 'payment_bank_name') else None,
            'payment_transaction_id': order.payment_transaction_id if hasattr(order, 'payment_transaction_id') else None,
            'orderer_identification': order.orderer_identification if hasattr(order, 'orderer_identification') else None,
            # NUEVOS CAMPOS: Posición fiscal y reembolsos
            'fiscal_position_id': order.fiscal_position_id.id if order.fiscal_position_id else None,
            'fiscal_position_name': order.fiscal_position_id.name if order.fiscal_position_id else None,
            'pricelist_id': order.pricelist_id.id if order.pricelist_id else None,
            'pricelist_name': order.pricelist_id.name if order.pricelist_id else None,
            # Campos de reembolso
            'is_refund': getattr(order, 'is_refund', False) or order.amount_total < 0,
            'refund_order_id': order.refund_order_id.id if hasattr(order, 'refund_order_id') and order.refund_order_id else None,
            'refund_order_pos_reference': order.refund_order_id.pos_reference if hasattr(order, 'refund_order_id') and order.refund_order_id else None,
            # Campos de trazabilidad
            'cloud_sync_id': order.cloud_sync_id if hasattr(order, 'cloud_sync_id') else None,
            'id_database_old': order.id_database_old if hasattr(order, 'id_database_old') else None,
            # Timestamps
            'create_date': order.create_date.isoformat() if order.create_date else None,
            'write_date': order.write_date.isoformat() if order.write_date else None,
            'lines': [],
            'payments': [],
        }

        # NUEVO: Datos de factura electrónica Ecuador (clave de acceso y autorización)
        # Incluye facturas en BORRADOR (draft) con clave de acceso generada en offline
        data['invoice_data'] = None
        if order.account_move:
            try:
                invoice = order.account_move
                # Extraer valores de forma segura
                auth_number = None
                auth_date = None
                inv_date = None
                latam_doc_number = None
                sri_payment_id = None
                edi_state_val = None
                invoice_state = invoice.state  # 'draft', 'posted', 'cancel'

                if hasattr(invoice, 'l10n_ec_authorization_number'):
                    auth_number = invoice.l10n_ec_authorization_number or None

                if hasattr(invoice, 'l10n_ec_authorization_date') and invoice.l10n_ec_authorization_date:
                    try:
                        auth_date = invoice.l10n_ec_authorization_date.isoformat()
                    except Exception:
                        auth_date = str(invoice.l10n_ec_authorization_date)

                if invoice.invoice_date:
                    try:
                        inv_date = invoice.invoice_date.isoformat()
                    except Exception:
                        inv_date = str(invoice.invoice_date)

                if hasattr(invoice, 'l10n_latam_document_number'):
                    latam_doc_number = invoice.l10n_latam_document_number or None

                if hasattr(invoice, 'l10n_ec_sri_payment_id') and invoice.l10n_ec_sri_payment_id:
                    sri_payment_id = invoice.l10n_ec_sri_payment_id.id

                if hasattr(invoice, 'edi_state'):
                    edi_state_val = invoice.edi_state or None

                # Solo incluir si hay clave de acceso (importante para el flujo offline)
                if auth_number:
                    data['invoice_data'] = {
                        'l10n_ec_authorization_number': auth_number,
                        'l10n_ec_authorization_date': auth_date,
                        'invoice_date': inv_date,
                        'invoice_name': invoice.name,
                        'l10n_latam_document_number': latam_doc_number,
                        'l10n_ec_sri_payment_id': sri_payment_id,
                        'edi_state': edi_state_val,
                        'invoice_state': invoice_state,  # NUEVO: incluir estado de factura
                    }
                    _logger.info(
                        f'Datos de factura serializados para orden {order.name}: '
                        f'estado={invoice_state}, clave={auth_number[:20]}...'
                    )
            except Exception as e:
                _logger.warning(f'Error serializando datos de factura para orden {order.name}: {e}')
                data['invoice_data'] = None

        # Serializar líneas con información adicional
        for line in order.lines:
            line_data = {
                'product_id': line.product_id.id,
                'product_barcode': line.product_id.barcode,
                'product_default_code': line.product_id.default_code,
                'product_name': line.full_product_name,
                'qty': line.qty,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
                'price_subtotal_incl': line.price_subtotal_incl,
                'discount': line.discount,
                'tax_ids': line.tax_ids.ids,
            }
            # Campos opcionales de promociones/lealtad
            if hasattr(line, 'reward_id') and line.reward_id:
                line_data['reward_id'] = line.reward_id.id
            if hasattr(line, 'is_reward_line'):
                line_data['is_reward_line'] = line.is_reward_line
            if hasattr(line, 'coupon_id') and line.coupon_id:
                line_data['coupon_id'] = line.coupon_id.id

            data['lines'].append(line_data)

        # Serializar pagos con todos los campos adicionales (cheque, tarjeta, crédito)
        # Los datos pueden estar en los campos del pago O en check_info_json/card_info_json de la orden
        _logger.debug(f'Serializando {len(order.payment_ids)} pagos para orden {order.name}')

        # Parsear check_info_json y card_info_json de la orden para usar como fallback
        import json as json_lib
        check_info_list = []
        card_info_list = []

        if hasattr(order, 'check_info_json') and order.check_info_json:
            try:
                check_info_list = json_lib.loads(order.check_info_json) if isinstance(order.check_info_json, str) else order.check_info_json
                if not isinstance(check_info_list, list):
                    check_info_list = []
            except (json_lib.JSONDecodeError, TypeError):
                check_info_list = []

        if hasattr(order, 'card_info_json') and order.card_info_json:
            try:
                card_info_list = json_lib.loads(order.card_info_json) if isinstance(order.card_info_json, str) else order.card_info_json
                if not isinstance(card_info_list, list):
                    card_info_list = []
            except (json_lib.JSONDecodeError, TypeError):
                card_info_list = []

        _logger.debug(f'check_info_json tiene {len(check_info_list)} registros, card_info_json tiene {len(card_info_list)} registros')

        check_info_idx = 0
        card_info_idx = 0

        for payment in order.payment_ids:

            # Datos básicos del pago
            payment_data = {
                'payment_method_id': payment.payment_method_id.id,
                'payment_method_name': payment.payment_method_id.name,
                'amount': payment.amount,
                'payment_date': payment.payment_date.isoformat() if hasattr(payment, 'payment_date') and payment.payment_date else None,
            }

            # Obtener datos de cheque: primero del pago, luego de check_info_json
            # Usar directamente el valor del campo, sin convertir False a None
            check_number = payment.check_number if payment.check_number else None
            check_bank_account = payment.check_bank_account if payment.check_bank_account else None
            check_owner = payment.check_owner if payment.check_owner else None
            bank_id = payment.bank_id.id if payment.bank_id else None
            bank_name = payment.bank_id.name if payment.bank_id else None

            # Si no hay datos en el pago, buscar en check_info_json
            if not check_number and check_info_idx < len(check_info_list):
                check_info = check_info_list[check_info_idx]
                check_number = check_info.get('check_number')
                check_bank_account = check_info.get('check_bank_account')
                check_owner = check_info.get('check_owner')
                bank_id = check_info.get('bank_id')
                # Buscar nombre del banco si tenemos ID
                if bank_id and not bank_name:
                    bank = self.env['res.bank'].sudo().browse(bank_id)
                    if bank.exists():
                        bank_name = bank.name
                check_info_idx += 1
                _logger.debug(f'Usando datos de check_info_json: check_number={check_number}, check_owner={check_owner}')

            payment_data.update({
                'check_number': check_number,
                'check_bank_account': check_bank_account,
                'check_owner': check_owner,
                'bank_id': bank_id,
                'bank_name': bank_name,
                'date': payment.date.isoformat() if payment.date else None,
                'institution_cheque': payment.institution_cheque if payment.institution_cheque else None,
                'institution_discount': payment.institution_discount if payment.institution_discount else None,
            })

            # Obtener datos de tarjeta: primero del pago, luego de card_info_json
            # Usar directamente el valor del campo
            number_voucher = payment.number_voucher if payment.number_voucher else None
            type_card = payment.type_card.id if payment.type_card else None
            type_card_name = payment.type_card.name if payment.type_card else None
            number_lote = payment.number_lote if payment.number_lote else None
            holder_card = payment.holder_card if payment.holder_card else None
            bin_tc = payment.bin_tc if payment.bin_tc else None

            # Si no hay datos en el pago, buscar en card_info_json
            if not number_voucher and card_info_idx < len(card_info_list):
                card_info = card_info_list[card_info_idx]
                number_voucher = card_info.get('number_voucher')
                type_card = card_info.get('type_card')
                number_lote = card_info.get('number_lote')
                holder_card = card_info.get('holder_card')
                bin_tc = card_info.get('bin_tc')
                # Buscar nombre del tipo de tarjeta si tenemos ID
                if type_card and not type_card_name:
                    credit_card = self.env['credit.card'].sudo().browse(type_card)
                    if credit_card.exists():
                        type_card_name = credit_card.name
                card_info_idx += 1
                _logger.debug(f'Usando datos de card_info_json: number_voucher={number_voucher}, holder_card={holder_card}')

            payment_data.update({
                'number_voucher': number_voucher,
                'type_card': type_card,
                'type_card_name': type_card_name,
                'number_lote': number_lote,
                'holder_card': holder_card,
                'bin_tc': bin_tc,
                'institution_card': payment.institution_card if payment.institution_card else None,
                'selecteInstitutionCredit': payment.selecteInstitutionCredit if payment.selecteInstitutionCredit else None,
            })

            data['payments'].append(payment_data)
            _logger.debug(f'Pago serializado: método={payment.payment_method_id.name}, monto={payment.amount}')

        _logger.info(f'Orden {order.name} serializada con {len(data["payments"])} pagos, estado: {order.state}')

        # NUEVO: Serializar json.storage (registro de factura para sistema externo)
        # Incluido en la orden para evitar problemas de foreign key al sincronizar
        data['json_storage_data'] = None
        try:
            JsonStorage = self.env['json.storage'].sudo()
            json_storage_record = JsonStorage.search([
                ('pos_order', '=', order.id)
            ], limit=1)

            if json_storage_record:
                data['json_storage_data'] = {
                    'id': json_storage_record.id,
                    'json_data': json_storage_record.json_data,
                    'employee': json_storage_record.employee,
                    'id_point_of_sale': json_storage_record.id_point_of_sale,
                    'client_invoice': json_storage_record.client_invoice,
                    'id_database_old_invoice_client': json_storage_record.id_database_old_invoice_client,
                    'is_access_key': json_storage_record.is_access_key,
                    'sent': json_storage_record.sent,
                    'db_key': json_storage_record.db_key,
                    'pos_order_id': json_storage_record.pos_order_id.id if json_storage_record.pos_order_id else False,
                    # NUEVO: Agregar nombre del pos.config para identificarlo en el cloud
                    'config_name': json_storage_record.pos_order_id.name if json_storage_record.pos_order_id else None,
                    'create_date': json_storage_record.create_date.isoformat() if json_storage_record.create_date else None,
                }
                _logger.info(f'json.storage serializado para orden {order.name}: id={json_storage_record.id}')
        except Exception as e:
            _logger.warning(f'Error serializando json.storage para orden {order.name}: {e}')

        return data

    @api.model
    def deserialize_order(self, data, sync_config):
        """
        Deserializa datos de orden para crear en el sistema.
        MEJORADO v2.5: Procesa orden completa con pagos y factura electrónica.

        Args:
            data: Diccionario con datos de la orden
            sync_config: Configuración de sincronización

        Returns:
            pos.order: Orden creada y procesada
        """
        PosOrder = self.env['pos.order'].sudo()
        PosSession = self.env['pos.session'].sudo()
        PosConfig = self.env['pos.config'].sudo()
        PosPayment = self.env['pos.payment'].sudo()

        pos_reference = data.get('pos_reference')
        order_name = data.get('name')
        session_name = data.get('session_name')
        config_name = data.get('config_name')
        order_state = data.get('state', 'draft')
        invoice_data = data.get('invoice_data')

        # Verificar si la orden ya existe
        if pos_reference:
            existing = PosOrder.search([
                ('pos_reference', '=', pos_reference)
            ], limit=1)
            if existing:
                # Verificar si la orden está completa
                has_payments = len(existing.payment_ids) > 0
                has_lines = len(existing.lines) > 0
                has_invoice = bool(existing.account_move)
                needs_invoice = bool(invoice_data)
                is_invoiced = existing.state == 'invoiced'

                _logger.info(
                    f'Orden encontrada: {pos_reference} - '
                    f'pagos={has_payments}, lineas={has_lines}, factura={has_invoice}, '
                    f'state={existing.state}, needs_invoice={needs_invoice}'
                )

                # ACTUALIZAR PAGOS EXISTENTES con datos de cheque/tarjeta
                # Esto se hace en todos los casos donde la orden ya existe
                payments_data = data.get('payments', [])
                if has_payments and payments_data:
                    _logger.info(f'Actualizando pagos existentes de orden {pos_reference}')
                    self._update_existing_payments(existing, payments_data)

                # Actualizar campos de transferencia en la orden si faltan
                order_update_vals = {}
                if data.get('payment_transfer_number') and not existing.payment_transfer_number:
                    order_update_vals['payment_transfer_number'] = data.get('payment_transfer_number')
                if data.get('payment_bank_name') and not existing.payment_bank_name:
                    order_update_vals['payment_bank_name'] = data.get('payment_bank_name')
                if data.get('payment_transaction_id') and not existing.payment_transaction_id:
                    order_update_vals['payment_transaction_id'] = data.get('payment_transaction_id')
                if data.get('orderer_identification') and not existing.orderer_identification:
                    order_update_vals['orderer_identification'] = data.get('orderer_identification')
                if data.get('check_info_json') and not existing.check_info_json:
                    order_update_vals['check_info_json'] = data.get('check_info_json')
                if data.get('card_info_json') and not existing.card_info_json:
                    order_update_vals['card_info_json'] = data.get('card_info_json')

                if order_update_vals:
                    existing.with_context(skip_sync_queue=True).write(order_update_vals)
                    _logger.info(f'Orden {pos_reference} actualizada con campos: {list(order_update_vals.keys())}')

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
                    return existing

                # CASO 2: Tiene pagos y líneas pero necesita factura
                if has_payments and has_lines and needs_invoice:
                    _logger.info(
                        f'Orden {pos_reference} existe pero sin factura, intentando crear...'
                    )
                    try:
                        self._create_invoice_from_offline(existing, invoice_data)
                        _logger.info(f'Factura creada para orden existente {pos_reference}')
                    except Exception as e:
                        _logger.error(f'Error creando factura para orden existente: {e}')
                    return existing

                # CASO 3: Tiene pagos y líneas pero no necesita factura
                if has_payments and has_lines and not needs_invoice:
                    _logger.info(
                        f'Orden {pos_reference} ya está completa (sin factura requerida)'
                    )
                    return existing

                # CASO 4: Orden incompleta - faltan pagos o líneas
                # En este caso, NO deberíamos crear una nueva orden
                # Devolvemos la existente para evitar duplicados
                _logger.warning(
                    f'Orden {pos_reference} existe pero incompleta '
                    f'(pagos={has_payments}, lineas={has_lines}). '
                    f'Retornando existente para evitar duplicados.'
                )
                return existing

        # Buscar sesión por nombre exacto
        session = None
        if session_name:
            session = PosSession.search([
                ('name', '=', session_name)
            ], limit=1)

        # Si no existe, buscar o crear
        if not session:
            # PRIORIDAD 1: Buscar por NOMBRE de configuración de la orden
            # CRÍTICO: config_name representa el POS real donde el dependiente
            # hizo la venta. Debe tener prioridad máxima.
            pos_config = None
            if config_name:
                pos_config = PosConfig.search([
                    ('name', '=', config_name)
                ], limit=1)
                if pos_config:
                    _logger.info(f'Config POS por nombre (prioridad 1): {pos_config.name} (ID: {pos_config.id})')

            # PRIORIDAD 2: Si no hay por nombre, usar pos_config_ids del sync_config
            if not pos_config and sync_config.pos_config_ids:
                pos_config = sync_config.pos_config_ids[:1]
                if pos_config:
                    _logger.info(f'Config POS desde sync_config (prioridad 2): {pos_config.name} (ID: {pos_config.id})')

            # PRIORIDAD 3: Buscar por almacén
            if not pos_config and sync_config.warehouse_id:
                pos_config = PosConfig.search([
                    ('picking_type_id.warehouse_id', '=', sync_config.warehouse_id.id)
                ], limit=1)
                if pos_config:
                    _logger.info(f'Config POS por warehouse (prioridad 3): {pos_config.name} (ID: {pos_config.id})')

            # CRÍTICO: NO buscar "cualquier config activa" como fallback
            # Esto causa que órdenes de una sucursal se asignen a otra
            if not pos_config:
                raise UserError(
                    f'No se encontró configuración POS para este almacén. '
                    f'Verifique que pos.sync.config tenga pos_config_ids configurados.'
                )

            _logger.info(f'Usando pos_config: {pos_config.name} (ID: {pos_config.id})')

            # Buscar el usuario correcto para la sesión
            # El usuario debe ser el del OFFLINE (dependiente), no el admin
            session_user_id = None
            user_name = data.get('user_name') or data.get('cashier_name')
            user_login = data.get('user_login')
            employee_name = data.get('employee_name')

            # Intentar encontrar usuario por login primero (más preciso)
            if user_login:
                user = self.env['res.users'].sudo().search([
                    ('login', '=', user_login)
                ], limit=1)
                if user:
                    session_user_id = user.id
                    _logger.info(f'Usuario encontrado por login: {user.name}')

            # Si no hay por login, buscar por nombre
            if not session_user_id and user_name:
                user = self.env['res.users'].sudo().search([
                    ('name', '=', user_name)
                ], limit=1)
                if user:
                    session_user_id = user.id
                    _logger.info(f'Usuario encontrado por nombre: {user.name}')

            # Si no hay usuario, intentar por empleado
            if not session_user_id and employee_name:
                employee = self.env['hr.employee'].sudo().search([
                    ('name', '=', employee_name)
                ], limit=1)
                if employee and employee.user_id:
                    session_user_id = employee.user_id.id
                    _logger.info(f'Usuario encontrado por empleado: {employee.user_id.name}')

            # ============================================================
            # BUSCAR SESIÓN ABIERTA EXISTENTE (config_id + user_id)
            # Esto permite reutilizar la misma sesión para múltiples órdenes
            # del mismo empleado en el mismo punto de venta
            # ============================================================
            session = None  # Inicializar
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

            # Si no encontramos con user_id específico, buscar cualquier sesión abierta del config
            if not session:
                session = PosSession.search(search_domain, limit=1, order='id desc')
                if session:
                    _logger.info(
                        f'Sesión existente encontrada para config={pos_config.name}: '
                        f'{session.name} (ID: {session.id})'
                    )

            # CREAR nueva sesión solo si no existe ninguna abierta
            if not session:
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

                    if session_name:
                        try:
                            session.write({'id_database_old': session_name})
                        except Exception:
                            pass

                    _logger.info(
                        f'Nueva sesión creada para sync: {session.name} (ID: {session.id}) '
                        f'config={pos_config.name}, user={session.user_id.name}'
                    )

                except Exception as e:
                    _logger.error(f'Error creando sesión: {e}')
                    raise UserError(f'No se pudo crear sesión para {pos_config.name}')

        # Buscar/crear partner
        partner = None
        if data.get('partner_vat'):
            partner = self.env['res.partner'].search([
                ('vat', '=', data['partner_vat'])
            ], limit=1)

        # Preparar líneas
        lines = []
        for line_data in data.get('lines', []):
            product = self.env['product.product'].search([
                ('barcode', '=', line_data.get('product_barcode'))
            ], limit=1)

            if not product and line_data.get('product_id'):
                product = self.env['product.product'].search([
                    ('id_database_old', '=', line_data.get('product_id'))
                ], limit=1)

            if not product and line_data.get('product_id'):
                product = self.env['product.product'].browse(line_data.get('product_id'))
                if not product.exists():
                    product = None

            if product:
                line_vals = {
                    'product_id': product.id,
                    'full_product_name': line_data.get('product_name', product.name),
                    'name': line_data.get('product_name', product.name),
                    'qty': line_data.get('qty', 1),
                    'price_unit': line_data.get('price_unit'),
                    'discount': line_data.get('discount', 0),
                    'price_subtotal': line_data.get('price_subtotal', 0.0),
                    'price_subtotal_incl': line_data.get('price_subtotal_incl', 0.0),
                }
                # Agregar product_free si existe
                if 'product_free' in line_data:
                    line_vals['product_free'] = line_data.get('product_free', False)
                lines.append((0, 0, line_vals))

        # Generar pos_reference, name y sequence_number
        # IMPORTANTE: Buscar el último sequence_number de TODO el config_id (punto de venta)
        # no solo de la sesión, para mantener la secuencia global del POS
        last_seq = PosOrder.sudo().search(
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

        # Crear orden
        # IMPORTANTE: to_invoice=True para que se pueda generar factura
        # is_delivery_order=False para que NO sea orden de entrega
        order_vals = {
            'session_id': session.id,
            'partner_id': partner.id if partner else None,
            'lines': lines,
            'amount_total': data.get('amount_total', 0.0),
            'amount_tax': data.get('amount_tax', 0.0),  # REQUIRED: NOT NULL constraint
            'amount_paid': data.get('amount_paid', 0.0),
            'amount_return': data.get('amount_return', 0.0),
            'note': data.get('note'),
            'to_invoice': True,  # Permitir facturación
            'is_delivery_order': False,  # NO es orden de entrega
            # Campos generados basados en sesión PRINCIPAL
            'name': generated_name,
            'pos_reference': generated_pos_reference,
            'sequence_number': next_seq,
        }

        # Añadir posición fiscal si existe
        if data.get('fiscal_position_id'):
            fiscal_position = self.env['account.fiscal.position'].search([
                '|',
                ('id', '=', data.get('fiscal_position_id')),
                ('name', '=', data.get('fiscal_position_name'))
            ], limit=1)
            if fiscal_position:
                order_vals['fiscal_position_id'] = fiscal_position.id

        # CRÍTICO: Agregar empleado del OFFLINE (debe coincidir en PRINCIPAL)
        if data.get('employee_name'):
            employee = self.env['hr.employee'].sudo().search([
                ('name', '=', data['employee_name'])
            ], limit=1)
            if employee:
                order_vals['employee_id'] = employee.id
        elif data.get('employee_id'):
            employee = self.env['hr.employee'].sudo().browse(data['employee_id'])
            if employee.exists():
                order_vals['employee_id'] = employee.id

        # CRÍTICO: Guardar el ID original del offline para poder vincular json.storage
        if data.get('id'):
            order_vals['id_database_old'] = str(data['id'])

        order = PosOrder.with_context(skip_sync_queue=True).create(order_vals)

        _logger.info(
            f'Orden creada en PRINCIPAL: name={order.name}, pos_reference={order.pos_reference}, '
            f'session={session.name}, config={session.config_id.name}, '
            f'employee={order.employee_id.name if order.employee_id else "N/A"} '
            f'(OFFLINE ref: {pos_reference}, state: {order_state})'
        )

        # ============================================================
        # FLUJO DE SINCRONIZACIÓN: Nuevo → Pagado → Registrado
        # ============================================================
        # 1. La orden se crea como DRAFT (Nuevo)
        # 2. Se agregan los pagos
        # 3. Se llama a action_pos_order_paid() → estado PAID (Pagado)
        # 4. Se genera la factura con clave de acceso → estado INVOICED (Registrado)
        # ============================================================

        _logger.info(f'=== PASO 1: Orden {order.name} creada como DRAFT (Nuevo) ===')

        # PASO 2: Crear pagos
        payments_data = data.get('payments', [])
        _logger.info(f'=== PASO 2: Creando {len(payments_data)} pagos para orden {order.name} ===')

        if payments_data:
            self._create_order_payments(order, payments_data, session)
            _logger.info(f'Pagos creados exitosamente. Total: {len(order.payment_ids)}')
        else:
            _logger.warning(f'No hay datos de pagos para orden {order.name}')

        # PASO 3: Marcar como PAGADA (si tiene pagos)
        if order_state in ['paid', 'done', 'invoiced'] and order.payment_ids:
            try:
                _logger.info(f'=== PASO 3: Marcando orden {order.name} como PAGADA ===')
                order.with_context(skip_sync_queue=True).action_pos_order_paid()
                _logger.info(f'Orden {order.name} ahora está en estado: {order.state}')
            except Exception as e:
                _logger.error(f'Error al marcar orden como pagada: {e}')

        # PASO 4: Generar factura (si hay cliente y clave de acceso)
        # El flujo estándar de Odoo: _generate_pos_order_invoice() postea la factura
        # y cambia el estado de la orden a 'invoiced'
        if partner and order.state == 'paid':
            try:
                _logger.info(f'=== PASO 4: Generando factura para orden {order.name} ===')

                if invoice_data and invoice_data.get('l10n_ec_authorization_number'):
                    access_key = invoice_data.get('l10n_ec_authorization_number', '')
                    _logger.info(
                        f'Usando clave de acceso del offline: {access_key[:20]}...'
                    )
                    # Crear factura con la clave de acceso del offline
                    self._create_invoice_from_offline(order, invoice_data)
                else:
                    # Generar factura normal (nueva clave de acceso)
                    # Sigue el flujo del principal: estado cambia a 'invoiced' inmediatamente
                    _logger.info(f'Generando factura con nueva clave de acceso')
                    order.with_context(skip_sync_queue=True)._generate_pos_order_invoice()

                if order.account_move:
                    _logger.info(
                        f'Factura generada: {order.account_move.name}, '
                        f'Estado factura: {order.account_move.state}, '
                        f'Estado orden: {order.state}'
                    )
                    # Verificar clave de acceso
                    if hasattr(order.account_move, 'l10n_ec_authorization_number'):
                        auth_num = order.account_move.l10n_ec_authorization_number
                        _logger.info(f'Clave de acceso final: {auth_num[:20] if auth_num else "N/A"}...')
                else:
                    _logger.warning(f'No se pudo generar factura para orden {order.name}')

            except Exception as e:
                _logger.error(f'Error al generar factura: {e}', exc_info=True)

        elif not partner:
            _logger.info(f'Orden {order.name} sin cliente - no se genera factura')

        # Asegurar que is_delivery_order sea False
        if order.is_delivery_order:
            order.with_context(skip_sync_queue=True).write({'is_delivery_order': False})

        _logger.info(
            f'=== SINCRONIZACIÓN COMPLETADA: {order.name} ===\n'
            f'   Estado final: {order.state}\n'
            f'   Factura: {order.account_move.name if order.account_move else "N/A"}\n'
            f'   Pagos: {len(order.payment_ids)}'
        )

        # ============================================================
        # PASO 5: Crear json.storage si viene en los datos de la orden
        # Esto evita problemas de foreign key al sincronizar separadamente
        # ============================================================
        json_storage_data = data.get('json_storage_data')
        if json_storage_data:
            try:
                _logger.info(f'=== PASO 5: Creando json.storage para orden {order.name} ===')
                self._create_json_storage_from_order(order, json_storage_data, session)
            except Exception as e:
                _logger.error(f'Error creando json.storage para orden {order.name}: {e}', exc_info=True)

        return order

    def _create_order_payments(self, order, payments_data, session):
        """
        Sincroniza los datos de pago (cheque/tarjeta) para una orden.

        IMPORTANTE: Este método NUNCA crea nuevos pagos.
        Los pagos (pos.payment) se crean automáticamente cuando se crea la orden.
        Este método solo actualiza los pagos existentes con los datos de cheque/tarjeta.

        Args:
            order: pos.order (ya tiene pagos creados automáticamente)
            payments_data: Lista de diccionarios con datos de pagos sincronizados
            session: pos.session
        """
        _logger.info(f'Sincronizando datos de {len(payments_data)} pagos para orden {order.name}')

        # Verificar que la orden tenga pagos
        if not order.payment_ids:
            _logger.warning(
                f'Orden {order.name} no tiene pagos. '
                f'Los pagos deberían haberse creado automáticamente al crear la orden.'
            )
            return

        _logger.info(f'Orden {order.name} tiene {len(order.payment_ids)} pagos existentes. Sincronizando campos...')

        # Actualizar los pagos existentes con los datos de cheque/tarjeta
        self._update_existing_payments(order, payments_data)

        _logger.info(f'Pagos sincronizados exitosamente. Total: {len(order.payment_ids)}')

    def _update_existing_payments(self, order, payments_data):
        """
        Actualiza los pagos existentes de una orden con los datos de cheque/tarjeta.

        Este método se llama cuando la orden ya tiene pagos creados (por ejemplo,
        después de facturar) y necesitamos actualizar los campos adicionales.

        Args:
            order: pos.order con pagos existentes
            payments_data: Lista de diccionarios con datos de pagos sincronizados
        """
        _logger.info(f'Actualizando {len(order.payment_ids)} pagos existentes para orden {order.name}')

        # Mapear pagos por método de pago y monto para encontrar correspondencias
        existing_payments = list(order.payment_ids)
        used_payments = set()

        for payment_data in payments_data:
            payment_method_name = payment_data.get('payment_method_name')
            payment_amount = payment_data.get('amount', 0)

            # Buscar el pago existente que coincida
            matching_payment = None
            for payment in existing_payments:
                if payment.id not in used_payments:
                    # Coincidir por método de pago y monto (con tolerancia de 0.01)
                    if (payment.payment_method_id.name == payment_method_name and
                            abs(payment.amount - payment_amount) < 0.01):
                        matching_payment = payment
                        used_payments.add(payment.id)
                        break

            # Si no coincide exactamente, usar el primer pago no usado
            if not matching_payment:
                for payment in existing_payments:
                    if payment.id not in used_payments:
                        matching_payment = payment
                        used_payments.add(payment.id)
                        break

            if matching_payment:
                update_vals = {}

                # Campos de CHEQUE
                if payment_data.get('check_number') and not matching_payment.check_number:
                    update_vals['check_number'] = payment_data.get('check_number')
                if payment_data.get('check_bank_account') and not matching_payment.check_bank_account:
                    update_vals['check_bank_account'] = payment_data.get('check_bank_account')
                if payment_data.get('check_owner') and not matching_payment.check_owner:
                    update_vals['check_owner'] = payment_data.get('check_owner')
                if payment_data.get('institution_cheque') and not matching_payment.institution_cheque:
                    update_vals['institution_cheque'] = payment_data.get('institution_cheque')
                if payment_data.get('institution_discount') and not matching_payment.institution_discount:
                    update_vals['institution_discount'] = payment_data.get('institution_discount')

                # Buscar y asignar banco
                if payment_data.get('bank_name') and not matching_payment.bank_id:
                    bank = self.env['res.bank'].sudo().search([
                        ('name', '=', payment_data.get('bank_name'))
                    ], limit=1)
                    if bank:
                        update_vals['bank_id'] = bank.id
                elif payment_data.get('bank_id') and not matching_payment.bank_id:
                    bank = self.env['res.bank'].sudo().browse(payment_data['bank_id'])
                    if bank.exists():
                        update_vals['bank_id'] = bank.id

                # Campos de TARJETA
                if payment_data.get('number_voucher') and not matching_payment.number_voucher:
                    update_vals['number_voucher'] = payment_data.get('number_voucher')
                if payment_data.get('number_lote') and not matching_payment.number_lote:
                    update_vals['number_lote'] = payment_data.get('number_lote')
                if payment_data.get('holder_card') and not matching_payment.holder_card:
                    update_vals['holder_card'] = payment_data.get('holder_card')
                if payment_data.get('bin_tc') and not matching_payment.bin_tc:
                    update_vals['bin_tc'] = payment_data.get('bin_tc')
                if payment_data.get('institution_card') and not matching_payment.institution_card:
                    update_vals['institution_card'] = payment_data.get('institution_card')

                # Buscar y asignar tipo de tarjeta
                if payment_data.get('type_card_name') and not matching_payment.type_card:
                    credit_card = self.env['credit.card'].sudo().search([
                        ('name', '=', payment_data.get('type_card_name'))
                    ], limit=1)
                    if credit_card:
                        update_vals['type_card'] = credit_card.id
                elif payment_data.get('type_card') and not matching_payment.type_card:
                    credit_card = self.env['credit.card'].sudo().browse(payment_data['type_card'])
                    if credit_card.exists():
                        update_vals['type_card'] = credit_card.id

                # Campos de CREDITO
                if payment_data.get('selecteInstitutionCredit') and not matching_payment.selecteInstitutionCredit:
                    update_vals['selecteInstitutionCredit'] = payment_data.get('selecteInstitutionCredit')

                if update_vals:
                    matching_payment.write(update_vals)
                    _logger.info(
                        f'Pago {matching_payment.id} actualizado con datos de cheque/tarjeta: '
                        f'{list(update_vals.keys())}'
                    )
                else:
                    _logger.info(f'Pago {matching_payment.id} no requiere actualización')
            else:
                _logger.warning(f'No se encontró pago existente para actualizar: {payment_data}')

    def _create_json_storage_from_order(self, order, json_storage_data, session):
        """
        Crea un registro json.storage en el servidor principal a partir de los datos
        sincronizados de la orden.

        IMPORTANTE: Este método verifica múltiples criterios para evitar duplicados:
        1. Por pos_order (orden actual)
        2. Por cloud_sync_id (ID original del offline)
        3. Por client_invoice + pos_reference (identificador único de la transacción)

        Args:
            order: pos.order recién creado
            json_storage_data: Diccionario con datos del json.storage del offline
            session: pos.session de la orden

        Returns:
            json.storage: Registro creado o existente, o None si no debe crearse
        """
        JsonStorage = self.env['json.storage'].sudo()

        # Si el json.storage ya fue enviado/procesado en el offline, no crear
        if json_storage_data.get('sent'):
            _logger.info(
                f'json.storage para orden {order.name}: ya fue enviado en offline (sent=True), '
                f'omitiendo creación'
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
            local_order = self.env['pos.order'].sudo().search([
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

        # VERIFICACIÓN 4: Por client_invoice + esta orden específica
        # Solo buscar si ya hay un json.storage vinculado a ESTA orden
        client_invoice = json_storage_data.get('client_invoice')
        if client_invoice and order:
            existing_by_order = JsonStorage.search([
                ('client_invoice', '=', client_invoice),
                ('pos_order', '=', order.id)  # Debe ser la misma orden
            ], limit=1)
            if existing_by_order:
                _logger.info(
                    f'json.storage encontrado para esta orden {order.name} '
                    f'con client_invoice={client_invoice}: ID={existing_by_order.id}'
                )
                return existing_by_order

        # NOTA: Se eliminó la verificación por client_invoice + id_database_old_invoice_client
        # porque esos valores son del CLIENTE, no de la TRANSACCIÓN

        # Buscar el pos.config para el campo pos_order_id
        # Primero intentar por config_name (nombre original del POS de la sucursal)
        pos_config = None
        config_name = json_storage_data.get('config_name')
        if config_name:
            pos_config = self.env['pos.config'].sudo().search([
                ('name', '=', config_name)
            ], limit=1)
            if pos_config:
                _logger.info(f'json.storage: pos.config encontrado por nombre "{config_name}": ID={pos_config.id}')

        # Si no se encontró por nombre, intentar por pos_order_id
        if not pos_config and json_storage_data.get('pos_order_id'):
            offline_pos_config_id = json_storage_data.get('pos_order_id')
            pos_config = self.env['pos.config'].sudo().search([
                '|',
                ('id', '=', offline_pos_config_id),
                ('point_of_sale_id', '=', offline_pos_config_id)
            ], limit=1)
            if pos_config:
                _logger.info(f'json.storage: pos.config encontrado por ID {offline_pos_config_id}: {pos_config.name}')

        # Fallback a session.config_id si no se encontró
        if not pos_config:
            pos_config = session.config_id if session else None
            if pos_config:
                _logger.info(f'json.storage: usando pos.config de sesión (fallback): {pos_config.name}')

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
            'pos_order': order.id,  # CRÍTICO: Referencia a la orden recién creada
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

            # Marcar como sincronizado
            new_storage.with_context(skip_sync_queue=True).write({
                'sync_state': 'synced',
                'last_sync_date': fields.Datetime.now(),
            })

            _logger.info(
                f'json.storage creado exitosamente para orden {order.name}: '
                f'ID={new_storage.id}, cloud_sync_id={original_id}'
            )
            return new_storage

        except Exception as e:
            _logger.error(f'Error creando json.storage para orden {order.name}: {e}', exc_info=True)
            raise

    def _create_invoice_from_offline(self, order, invoice_data):
        """
        Crea y POSTEA la factura para una orden sincronizada desde offline.

        FLUJO CORREGIDO (Igual al principal pos_custom_check):
        1. Se crea factura usando _create_invoice (obtiene el name correcto del OFFLINE)
        2. Se vincula la factura a la orden y se cambia estado a 'invoiced'
        3. Se postea la factura con skip_l10n_ec_authorization para preservar clave
        4. Se aplican los pagos usando _apply_invoice_payments (método nativo POS)

        CRÍTICO: El NAME de la factura DEBE coincidir con el del OFFLINE porque
        la clave de acceso se genera usando move.name.split('-')[2] en l10n_ec_edi.

        Args:
            order: pos.order
            invoice_data: Diccionario con datos de la factura del offline

        Returns:
            bool: True si la factura se creó correctamente, False en caso contrario
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
            _logger.warning(f'No hay clave de acceso para orden {order.name}, generando factura normal')
            try:
                order.with_context(skip_sync_queue=True).action_pos_order_invoice()
                return True
            except Exception as e:
                _logger.error(f'Error generando factura normal: {e}')
                return False

        invoice = None
        try:
            _logger.info(
                f'[SYNC] Creando factura para orden {order.name} con clave de acceso del offline '
                f'(estado offline: {invoice_state_offline})'
            )

            # Preparar valores de factura usando el método estándar de Odoo
            invoice_vals = order._prepare_invoice_vals()

            # CRÍTICO: Establecer la clave de acceso del OFFLINE ANTES de crear
            # Esta clave será preservada y usada para enviar al SRI
            invoice_vals['l10n_ec_authorization_number'] = l10n_ec_authorization_number

            # Establecer método de pago SRI si existe
            if invoice_data.get('l10n_ec_sri_payment_id'):
                invoice_vals['l10n_ec_sri_payment_id'] = invoice_data['l10n_ec_sri_payment_id']

            # Establecer fecha de factura del offline si existe
            if invoice_data.get('invoice_date'):
                try:
                    inv_date = invoice_data['invoice_date']
                    if isinstance(inv_date, str):
                        inv_date = datetime.fromisoformat(inv_date).date()
                    invoice_vals['invoice_date'] = inv_date
                except Exception as e:
                    _logger.warning(f'No se pudo parsear fecha de factura: {e}')

            # Crear la factura con el contexto especial
            # El ONLINE generará SU propio número de factura, pero usará la clave de acceso del OFFLINE
            invoice = self.env['account.move'].sudo().with_context(
                skip_sync_queue=True,
                skip_l10n_ec_authorization=True,  # No regenerar clave - usar la del offline
            ).create(invoice_vals)

            _logger.info(
                f'[SYNC] Factura creada: name={invoice.name}, '
                f'clave_acceso={invoice.l10n_ec_authorization_number[:20] if invoice.l10n_ec_authorization_number else "N/A"}...'
            )

            # FLUJO IGUAL AL PRINCIPAL (pos_custom_check/_generate_pos_order_invoice):
            # 1. Vincular factura a la orden ANTES de postear
            # 2. Cambiar estado a 'invoiced' (Registrado)
            # 3. Guardar clave de acceso en key_order
            order.with_context(skip_sync_queue=True).write({
                'account_move': invoice.id,
                'state': 'invoiced',
                'key_order': l10n_ec_authorization_number,  # Clave de acceso de 49 dígitos
            })

            # 3. Postear la factura (crea asientos contables)
            # CRÍTICO: skip_l10n_ec_authorization=True para NO regenerar clave
            invoice.sudo().with_company(order.company_id).with_context(
                skip_l10n_ec_authorization=True,
                skip_sync_queue=True,
                skip_invoice_sync=True,
            )._post()

            _logger.info(
                f'[SYNC] Factura {invoice.name} POSTEADA con clave de acceso: '
                f'{l10n_ec_authorization_number[:20]}...'
            )

            # 4. Aplicar pagos usando el método nativo de POS
            # NOTA: En PRINCIPAL la sesión siempre está "abierta" (se crea para sync)
            # No aplica _create_misc_reversal_move porque eso es solo cuando
            # la sesión se cierra en el POS local
            try:
                order._apply_invoice_payments(False)
                _logger.info(f'[SYNC] Pagos aplicados a factura {invoice.name}')
            except Exception as pay_error:
                _logger.warning(
                    f'[SYNC] Error aplicando pagos nativos: {pay_error}, '
                    f'intentando método alternativo...'
                )
                try:
                    self._register_invoice_payment_fallback(order, invoice)
                except Exception as fb_error:
                    _logger.warning(f'[SYNC] Error en fallback de pagos: {fb_error}')

            _logger.info(
                f'[SYNC] Orden {order.name} procesada completamente - '
                f'Factura: {invoice.name}, payment_state: {invoice.payment_state}'
            )
            return True

        except Exception as e:
            _logger.error(f'[SYNC] Error al crear/postear factura: {e}', exc_info=True)

            # Si la factura se creó pero falló al postear, eliminarla
            if invoice and invoice.state == 'draft':
                try:
                    invoice.unlink()
                    _logger.info(f'[SYNC] Factura borrador eliminada después de error')
                except Exception as e3:
                    _logger.warning(f'No se pudo eliminar factura borrador: {e3}')

            # Fallback: crear factura normal (generará nueva clave)
            try:
                _logger.warning(f'[SYNC] Intentando fallback: factura normal para orden {order.name}')
                order.with_context(skip_sync_queue=True).action_pos_order_invoice()
                return True
            except Exception as e2:
                _logger.error(f'Error en fallback de factura: {e2}')
                # La orden quedará en estado 'paid' sin factura
                _logger.warning(f'Orden {order.name} quedará en estado paid sin factura')
                return False

    def _register_invoice_payment_fallback(self, order, invoice):
        """
        Método de fallback para registrar el pago de la orden POS en la factura.

        Este método se usa como fallback cuando _apply_invoice_payments falla.
        Usa account.payment.register para crear el pago.

        NOTA: El método preferido es _apply_invoice_payments del POS que maneja
        correctamente los pagos POS. Este es solo un fallback.

        Args:
            order: pos.order - La orden POS con los pagos
            invoice: account.move - La factura a la que se registrará el pago
        """
        if not order.payment_ids:
            _logger.warning(f'Orden {order.name} no tiene pagos para registrar')
            return

        if invoice.payment_state == 'paid':
            _logger.info(f'Factura {invoice.name} ya está pagada')
            return

        # Calcular el monto total de pagos
        total_payment = sum(order.payment_ids.mapped('amount'))

        if total_payment <= 0:
            _logger.warning(f'Monto de pago inválido para orden {order.name}: {total_payment}')
            return

        _logger.info(
            f'Registrando pago de {total_payment} en factura {invoice.name} '
            f'para orden {order.name}'
        )

        # Buscar el diario de pago desde los pagos de la orden
        # Usar el primer método de pago que tenga un diario configurado
        journal = None
        payment_method_line = None

        for payment in order.payment_ids:
            if payment.payment_method_id and payment.payment_method_id.journal_id:
                journal = payment.payment_method_id.journal_id
                # Buscar la línea de método de pago del diario
                payment_method_line = self.env['account.payment.method.line'].sudo().search([
                    ('journal_id', '=', journal.id),
                    ('payment_type', '=', 'inbound'),
                ], limit=1)
                if payment_method_line:
                    break

        # Si no se encontró diario, usar el diario de efectivo por defecto
        if not journal:
            journal = self.env['account.journal'].sudo().search([
                ('type', '=', 'cash'),
                ('company_id', '=', order.company_id.id),
            ], limit=1)

            if journal:
                payment_method_line = self.env['account.payment.method.line'].sudo().search([
                    ('journal_id', '=', journal.id),
                    ('payment_type', '=', 'inbound'),
                ], limit=1)

        if not journal:
            _logger.error(f'No se encontró diario de pago para orden {order.name}')
            return

        if not payment_method_line:
            _logger.error(f'No se encontró línea de método de pago para diario {journal.name}')
            return

        try:
            # Crear el registro de pago usando el wizard
            payment_register = self.env['account.payment.register'].with_context(
                active_model='account.move',
                active_ids=[invoice.id],
            ).sudo().create({
                'amount': total_payment,
                'payment_date': invoice.invoice_date or fields.Date.today(),
                'journal_id': journal.id,
                'payment_method_line_id': payment_method_line.id,
                'partner_id': order.partner_id.id,
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'communication': invoice.name,
            })

            # Crear y validar el pago
            payment = payment_register._create_payments()

            _logger.info(
                f'Pago registrado exitosamente: ID={payment.id}, monto={total_payment}, '
                f'factura={invoice.name}, payment_state={invoice.payment_state}'
            )

            # Refrescar la factura para obtener el estado actualizado
            invoice.invalidate_recordset(['payment_state', 'amount_residual'])
            _logger.info(
                f'Estado de pago de factura {invoice.name}: {invoice.payment_state}, '
                f'residual: {invoice.amount_residual}'
            )

        except Exception as e:
            _logger.error(f'Error registrando pago en factura {invoice.name}: {e}', exc_info=True)
            raise

    @api.model
    def serialize_partner(self, partner):
        """
        Serializa un partner para sincronización.

        Args:
            partner: Registro res.partner

        Returns:
            dict: Datos serializados
        """
        data = {
            'id': partner.id,
            'name': partner.name,
            'display_name': partner.display_name,
            'email': partner.email,
            'phone': partner.phone,
            'mobile': partner.mobile,
            'vat': partner.vat,
            'street': partner.street,
            'street2': partner.street2,
            'city': partner.city,
            'zip': partner.zip,
            'country_id': partner.country_id.id if partner.country_id else None,
            'country_name': partner.country_id.name if partner.country_id else None,
            'country_code': partner.country_id.code if partner.country_id else None,
            'state_id': partner.state_id.id if partner.state_id else None,
            'state_name': partner.state_id.name if partner.state_id else None,
            'state_code': partner.state_id.code if partner.state_id else None,
            'type': partner.type,
            'lang': partner.lang,
            'comment': partner.comment,
            'barcode': partner.barcode,
            'ref': partner.ref,
            'active': partner.active,
            # Campos de sincronización
            'id_database_old': partner.id_database_old if hasattr(partner, 'id_database_old') else None,
            'cloud_sync_id': partner.cloud_sync_id if hasattr(partner, 'cloud_sync_id') else None,
            # Campos relacionados a POS
            'property_product_pricelist': partner.property_product_pricelist.id if partner.property_product_pricelist else None,
            'property_product_pricelist_name': partner.property_product_pricelist.name if partner.property_product_pricelist else None,
        }

        # Agregar campos de facturación si existen
        if hasattr(partner, 'l10n_latam_identification_type_id'):
            data['l10n_latam_identification_type_id'] = partner.l10n_latam_identification_type_id.id if partner.l10n_latam_identification_type_id else None
            data['l10n_latam_identification_type_name'] = partner.l10n_latam_identification_type_id.name if partner.l10n_latam_identification_type_id else None

        return data

    @api.model
    def deserialize_partner(self, data, sync_config=None):
        """
        Deserializa datos de partner para crear/actualizar en el sistema.

        IMPORTANTE: Este método se usa cuando recibimos datos del cloud,
        por lo que usamos skip_sync_queue=True para evitar que los cambios
        se vuelvan a agregar a la cola de sincronización (evitar loop).

        Args:
            data: Diccionario con datos del partner
            sync_config: Configuración de sincronización (opcional)

        Returns:
            res.partner: Partner creado o actualizado
        """
        Partner = self.env['res.partner'].sudo()

        # Buscar partner existente
        partner = Partner.find_or_create_from_sync(data)

        # Preparar valores
        vals = self._prepare_partner_vals(data)

        if partner:
            # Actualizar existente - USAR skip_sync_queue para evitar loop
            partner.with_context(skip_sync_queue=True).write(vals)
            _logger.info(f'Partner actualizado desde cloud: {partner.name} (ID: {partner.id})')
        else:
            # Crear nuevo - USAR skip_sync_queue para evitar loop
            partner = Partner.with_context(skip_sync_queue=True).create(vals)
            _logger.info(f'Partner creado desde cloud: {partner.name} (ID: {partner.id})')

        # Marcar el cloud_sync_id y el origen como cloud
        update_vals = {
            'sync_state': 'synced',
            'sync_source': 'cloud',
            'last_sync_date': fields.Datetime.now(),
        }
        if data.get('id') and not partner.cloud_sync_id:
            update_vals['cloud_sync_id'] = data['id']

        partner.with_context(skip_sync_queue=True).write(update_vals)

        return partner

    # ==================== SERIALIZADORES DE PRODUCTO ====================

    @api.model
    def serialize_product(self, product):
        """
        Serializa un producto para sincronización.

        Args:
            product: Registro product.product

        Returns:
            dict: Datos serializados
        """
        # Obtener el template relacionado
        template = product.product_tmpl_id

        data = {
            'id': product.id,
            'name': product.name,
            'display_name': product.display_name,
            'default_code': product.default_code,
            'barcode': product.barcode,
            'list_price': product.list_price,
            'lst_price': product.lst_price,
            'standard_price': product.standard_price,
            'type': product.type,
            'detailed_type': product.detailed_type if hasattr(product, 'detailed_type') else None,
            'available_in_pos': product.available_in_pos,
            'sale_ok': product.sale_ok,
            'purchase_ok': product.purchase_ok,
            'active': product.active,
            'categ_id': product.categ_id.id if product.categ_id else None,
            'categ_name': product.categ_id.complete_name if product.categ_id else None,
            'uom_id': product.uom_id.id if product.uom_id else None,
            'uom_name': product.uom_id.name if product.uom_id else None,
            'uom_po_id': product.uom_po_id.id if product.uom_po_id else None,
            'uom_po_name': product.uom_po_id.name if product.uom_po_id else None,
            'description': product.description,
            'description_sale': product.description_sale,
            'weight': product.weight,
            'volume': product.volume,
            # Campos de sincronización del producto
            'cloud_sync_id': product.cloud_sync_id if hasattr(product, 'cloud_sync_id') else None,
            'id_database_old': product.id_database_old if hasattr(product, 'id_database_old') else None,
            # Campos de sincronización del template
            'product_tmpl_id': template.id if template else None,
            'template_cloud_sync_id': template.cloud_sync_id if template and hasattr(template, 'cloud_sync_id') else None,
            'template_id_database_old': template.id_database_old if template and hasattr(template, 'id_database_old') else None,
            # Impuestos
            'taxes_id': product.taxes_id.ids if product.taxes_id else [],
            'supplier_taxes_id': product.supplier_taxes_id.ids if product.supplier_taxes_id else [],
            # Imagen (solo si es pequeña o necesaria)
            'image_128': product.image_128.decode('utf-8') if product.image_128 else None,
        }

        # Campos específicos de POS si existen
        if hasattr(product, 'pos_categ_ids'):
            data['pos_categ_ids'] = product.pos_categ_ids.ids

        if hasattr(product, 'to_weight'):
            data['to_weight'] = product.to_weight

        return data

    @api.model
    def serialize_product_template(self, template):
        """
        Serializa un product.template para sincronización.

        Args:
            template: Registro product.template

        Returns:
            dict: Datos serializados
        """
        data = {
            'id': template.id,
            'name': template.name,
            'display_name': template.display_name,
            'default_code': template.default_code,
            'barcode': template.barcode if hasattr(template, 'barcode') else None,
            'list_price': template.list_price,
            'standard_price': template.standard_price,
            'type': template.type,
            'detailed_type': template.detailed_type if hasattr(template, 'detailed_type') else None,
            'available_in_pos': template.available_in_pos,
            'sale_ok': template.sale_ok,
            'purchase_ok': template.purchase_ok,
            'active': template.active,
            'categ_id': template.categ_id.id if template.categ_id else None,
            'categ_name': template.categ_id.complete_name if template.categ_id else None,
            'uom_id': template.uom_id.id if template.uom_id else None,
            'uom_name': template.uom_id.name if template.uom_id else None,
            'uom_po_id': template.uom_po_id.id if template.uom_po_id else None,
            'uom_po_name': template.uom_po_id.name if template.uom_po_id else None,
            'description': template.description,
            'description_sale': template.description_sale,
            'weight': template.weight,
            'volume': template.volume,
            # Campos de sincronización
            'cloud_sync_id': template.cloud_sync_id if hasattr(template, 'cloud_sync_id') else None,
            'id_database_old': template.id_database_old if hasattr(template, 'id_database_old') else None,
            # Impuestos
            'taxes_id': template.taxes_id.ids if template.taxes_id else [],
            'supplier_taxes_id': template.supplier_taxes_id.ids if template.supplier_taxes_id else [],
            # Imagen
            'image_128': template.image_128.decode('utf-8') if template.image_128 else None,
        }

        # Campos específicos de POS si existen
        if hasattr(template, 'pos_categ_ids'):
            data['pos_categ_ids'] = template.pos_categ_ids.ids

        if hasattr(template, 'to_weight'):
            data['to_weight'] = template.to_weight

        # Incluir IDs de variantes (product.product) asociadas
        if template.product_variant_ids:
            data['product_variant_ids'] = template.product_variant_ids.ids

        return data

    @api.model
    def deserialize_product(self, data, sync_config=None):
        """
        Deserializa datos de producto para crear/actualizar en el sistema.

        Args:
            data: Diccionario con datos del producto
            sync_config: Configuración de sincronización (opcional)

        Returns:
            product.product: Producto creado o actualizado
        """
        Product = self.env['product.product'].sudo()

        # Buscar producto existente
        product = Product.find_or_create_from_sync(data)

        # Preparar valores
        vals = self._prepare_product_vals(data)

        if product:
            # Actualizar existente
            product.write(vals)
            _logger.info(f'Producto actualizado: {product.name} (ID: {product.id})')
        else:
            # Crear nuevo
            product = Product.create(vals)
            _logger.info(f'Producto creado: {product.name} (ID: {product.id})')

        # Marcar el cloud_sync_id si viene del cloud
        if data.get('id') and not product.cloud_sync_id:
            product.write({'cloud_sync_id': data['id']})

        # Sincronizar también el product.template
        # En Odoo, product.product hereda de product.template via _inherits
        # Por lo que debemos actualizar los campos de sincronización en el template
        if product.product_tmpl_id:
            template = product.product_tmpl_id
            template_vals = {}

            # Actualizar cloud_sync_id del template si viene
            template_cloud_id = data.get('template_cloud_sync_id') or data.get('product_tmpl_id')
            if template_cloud_id and not template.cloud_sync_id:
                template_vals['cloud_sync_id'] = template_cloud_id

            # Actualizar id_database_old del template si viene
            template_db_old = data.get('template_id_database_old')
            if template_db_old and not template.id_database_old:
                template_vals['id_database_old'] = str(template_db_old)

            # Marcar como sincronizado
            template_vals['sync_state'] = 'synced'
            template_vals['last_sync_date'] = fields.Datetime.now()

            if template_vals:
                template.write(template_vals)
                _logger.info(
                    f'Template actualizado: {template.name} (ID: {template.id}), '
                    f'cloud_sync_id={template.cloud_sync_id}'
                )

        return product

    def _prepare_product_vals(self, data):
        """
        Prepara los valores para crear/actualizar un producto.

        Args:
            data: Diccionario con datos del producto

        Returns:
            dict: Valores preparados para Odoo
        """
        vals = {
            'name': data.get('name'),
            'default_code': data.get('default_code'),
            'barcode': data.get('barcode'),
            'list_price': data.get('list_price'),
            'standard_price': data.get('standard_price'),
            'type': data.get('type', 'consu'),
            'available_in_pos': data.get('available_in_pos', True),
            'sale_ok': data.get('sale_ok', True),
            'purchase_ok': data.get('purchase_ok', True),
            'description': data.get('description'),
            'description_sale': data.get('description_sale'),
            'weight': data.get('weight'),
            'volume': data.get('volume'),
        }

        # Manejar detailed_type si existe
        if data.get('detailed_type'):
            vals['detailed_type'] = data['detailed_type']

        # Manejar categoría
        if data.get('categ_id'):
            categ = self.env['product.category'].sudo().browse(data['categ_id'])
            if categ.exists():
                vals['categ_id'] = categ.id
        elif data.get('categ_name'):
            categ = self.env['product.category'].sudo().search([
                ('complete_name', '=', data['categ_name'])
            ], limit=1)
            if categ:
                vals['categ_id'] = categ.id

        # Manejar UoM
        if data.get('uom_id'):
            uom = self.env['uom.uom'].sudo().browse(data['uom_id'])
            if uom.exists():
                vals['uom_id'] = uom.id
                vals['uom_po_id'] = uom.id
        elif data.get('uom_name'):
            uom = self.env['uom.uom'].sudo().search([
                ('name', '=', data['uom_name'])
            ], limit=1)
            if uom:
                vals['uom_id'] = uom.id
                vals['uom_po_id'] = uom.id

        # Manejar impuestos
        if data.get('taxes_id'):
            vals['taxes_id'] = [(6, 0, data['taxes_id'])]

        # Manejar id_database_old
        if data.get('id_database_old'):
            vals['id_database_old'] = str(data['id_database_old'])

        # Manejar categorías POS
        if data.get('pos_categ_ids'):
            vals['pos_categ_ids'] = [(6, 0, data['pos_categ_ids'])]

        # Limpiar valores None
        vals = {k: v for k, v in vals.items() if v is not None}

        return vals

    @api.model
    def deserialize_product_template(self, data, sync_config=None):
        """
        Deserializa datos de product.template para crear/actualizar en el sistema.

        Args:
            data: Diccionario con datos del product.template
            sync_config: Configuración de sincronización (opcional)

        Returns:
            product.template: Template creado o actualizado
        """
        ProductTemplate = self.env['product.template'].sudo()

        # Buscar template existente
        template = self._find_product_template(data)

        # Preparar valores
        vals = self._prepare_product_template_vals(data)

        if template:
            # Actualizar existente
            template.write(vals)
            _logger.info(f'Product template actualizado: {template.name} (ID: {template.id})')
        else:
            # Crear nuevo
            template = ProductTemplate.create(vals)
            _logger.info(f'Product template creado: {template.name} (ID: {template.id})')

        # Marcar el cloud_sync_id si viene del cloud
        if data.get('id') and not template.cloud_sync_id:
            template.write({'cloud_sync_id': data['id']})

        # Marcar como sincronizado
        template.write({
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now()
        })

        return template

    def _find_product_template(self, data):
        """
        Busca un product.template existente por diferentes criterios.

        Args:
            data: Diccionario con datos del template

        Returns:
            product.template: Template encontrado o None
        """
        ProductTemplate = self.env['product.template'].sudo()
        template = None

        # 1. Buscar por cloud_sync_id
        if data.get('cloud_sync_id'):
            template = ProductTemplate.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)
            if template:
                _logger.info(f'Template encontrado por cloud_sync_id: {template.name}')
                return template

        # 2. Buscar por id (el ID del servidor principal)
        if data.get('id'):
            template = ProductTemplate.search([
                ('cloud_sync_id', '=', data['id'])
            ], limit=1)
            if template:
                _logger.info(f'Template encontrado por id como cloud_sync_id: {template.name}')
                return template

        # 3. Buscar por barcode
        if data.get('barcode'):
            template = ProductTemplate.search([
                ('barcode', '=', data['barcode'])
            ], limit=1)
            if template:
                _logger.info(f'Template encontrado por barcode: {template.name}')
                return template

        # 4. Buscar por default_code
        if data.get('default_code'):
            template = ProductTemplate.search([
                ('default_code', '=', data['default_code'])
            ], limit=1)
            if template:
                _logger.info(f'Template encontrado por default_code: {template.name}')
                return template

        # 5. Buscar por id_database_old + name
        if data.get('id_database_old'):
            domain = [('id_database_old', '=', str(data['id_database_old']))]
            if data.get('name'):
                domain.append(('name', '=', data['name']))
            template = ProductTemplate.search(domain, limit=1)
            if template:
                _logger.info(f'Template encontrado por id_database_old: {template.name}')
                return template

        _logger.info(f'No se encontró template existente para: {data.get("name")}')
        return None

    def _prepare_product_template_vals(self, data):
        """
        Prepara los valores para crear/actualizar un product.template.

        Args:
            data: Diccionario con datos del template

        Returns:
            dict: Valores preparados para Odoo
        """
        vals = {
            'name': data.get('name'),
            'default_code': data.get('default_code'),
            'barcode': data.get('barcode'),
            'list_price': data.get('list_price'),
            'standard_price': data.get('standard_price'),
            'type': data.get('type', 'consu'),
            'available_in_pos': data.get('available_in_pos', True),
            'sale_ok': data.get('sale_ok', True),
            'purchase_ok': data.get('purchase_ok', True),
            'description': data.get('description'),
            'description_sale': data.get('description_sale'),
            'weight': data.get('weight'),
            'volume': data.get('volume'),
        }

        # Manejar detailed_type si existe
        if data.get('detailed_type'):
            vals['detailed_type'] = data['detailed_type']

        # Manejar categoría
        if data.get('categ_id'):
            categ = self.env['product.category'].sudo().browse(data['categ_id'])
            if categ.exists():
                vals['categ_id'] = categ.id
        elif data.get('categ_name'):
            categ = self.env['product.category'].sudo().search([
                ('complete_name', '=', data['categ_name'])
            ], limit=1)
            if categ:
                vals['categ_id'] = categ.id

        # Manejar UoM
        if data.get('uom_id'):
            uom = self.env['uom.uom'].sudo().browse(data['uom_id'])
            if uom.exists():
                vals['uom_id'] = uom.id
                vals['uom_po_id'] = uom.id
        elif data.get('uom_name'):
            uom = self.env['uom.uom'].sudo().search([
                ('name', '=', data['uom_name'])
            ], limit=1)
            if uom:
                vals['uom_id'] = uom.id
                vals['uom_po_id'] = uom.id

        # Manejar impuestos
        if data.get('taxes_id'):
            vals['taxes_id'] = [(6, 0, data['taxes_id'])]

        # Manejar id_database_old
        if data.get('id_database_old'):
            vals['id_database_old'] = str(data['id_database_old'])

        # Manejar categorías POS
        if data.get('pos_categ_ids'):
            vals['pos_categ_ids'] = [(6, 0, data['pos_categ_ids'])]

        # Limpiar valores None
        vals = {k: v for k, v in vals.items() if v is not None}

        return vals

    # ==================== SERIALIZADORES DE LISTA DE PRECIOS ====================

    @api.model
    def serialize_pricelist(self, pricelist):
        """
        Serializa una lista de precios para sincronización.

        Args:
            pricelist: Registro product.pricelist

        Returns:
            dict: Datos serializados
        """
        data = {
            'id': pricelist.id,
            'name': pricelist.name,
            'active': pricelist.active,
            'currency_id': pricelist.currency_id.id if pricelist.currency_id else None,
            'currency_name': pricelist.currency_id.name if pricelist.currency_id else None,
            'company_id': pricelist.company_id.id if pricelist.company_id else None,
            'discount_policy': pricelist.discount_policy if hasattr(pricelist, 'discount_policy') else None,
            # Campos de sincronización
            'cloud_sync_id': pricelist.cloud_sync_id if hasattr(pricelist, 'cloud_sync_id') else None,
            'id_database_old': pricelist.id_database_old if hasattr(pricelist, 'id_database_old') else None,
            # Items de la lista de precios
            'items': [],
        }

        # Serializar items
        for item in pricelist.item_ids:
            item_data = {
                'id': item.id,
                'applied_on': item.applied_on,
                'product_tmpl_id': item.product_tmpl_id.id if item.product_tmpl_id else None,
                'product_id': item.product_id.id if item.product_id else None,
                'categ_id': item.categ_id.id if item.categ_id else None,
                'min_quantity': item.min_quantity,
                'date_start': item.date_start.isoformat() if item.date_start else None,
                'date_end': item.date_end.isoformat() if item.date_end else None,
                'compute_price': item.compute_price,
                'fixed_price': item.fixed_price,
                'percent_price': item.percent_price,
                'price_discount': item.price_discount if hasattr(item, 'price_discount') else None,
                'price_surcharge': item.price_surcharge if hasattr(item, 'price_surcharge') else None,
                'base': item.base if hasattr(item, 'base') else None,
            }
            data['items'].append(item_data)

        return data

    @api.model
    def deserialize_pricelist(self, data, sync_config=None):
        """
        Deserializa datos de lista de precios para crear/actualizar en el sistema.

        Args:
            data: Diccionario con datos de la lista de precios
            sync_config: Configuración de sincronización (opcional)

        Returns:
            product.pricelist: Lista de precios creada o actualizada
        """
        Pricelist = self.env['product.pricelist'].sudo()

        # Buscar lista de precios existente
        pricelist = Pricelist.find_or_create_from_sync(data)

        # Preparar valores
        vals = self._prepare_pricelist_vals(data)

        if pricelist:
            # Actualizar existente
            pricelist.write(vals)
            _logger.info(f'Lista de precios actualizada: {pricelist.name} (ID: {pricelist.id})')
        else:
            # Crear nueva
            pricelist = Pricelist.create(vals)
            _logger.info(f'Lista de precios creada: {pricelist.name} (ID: {pricelist.id})')

        # Marcar el cloud_sync_id si viene del cloud
        if data.get('id') and not pricelist.cloud_sync_id:
            pricelist.write({'cloud_sync_id': data['id']})

        # Procesar items
        if data.get('items'):
            self._process_pricelist_items(pricelist, data['items'])

        return pricelist

    def _prepare_pricelist_vals(self, data):
        """Prepara valores para crear/actualizar una lista de precios."""
        vals = {
            'name': data.get('name'),
            'active': data.get('active', True),
        }

        # Manejar moneda
        if data.get('currency_id'):
            currency = self.env['res.currency'].sudo().browse(data['currency_id'])
            if currency.exists():
                vals['currency_id'] = currency.id
        elif data.get('currency_name'):
            currency = self.env['res.currency'].sudo().search([
                ('name', '=', data['currency_name'])
            ], limit=1)
            if currency:
                vals['currency_id'] = currency.id

        # Manejar id_database_old
        if data.get('id_database_old'):
            vals['id_database_old'] = str(data['id_database_old'])

        # Limpiar valores None
        vals = {k: v for k, v in vals.items() if v is not None}

        return vals

    def _process_pricelist_items(self, pricelist, items_data):
        """
        Procesa los items de una lista de precios.

        Args:
            pricelist: Lista de precios
            items_data: Lista de datos de items
        """
        PricelistItem = self.env['product.pricelist.item'].sudo()

        for item_data in items_data:
            # Buscar item existente por cloud_sync_id o id_database_old
            existing_item = None
            if item_data.get('id'):
                existing_item = PricelistItem.search([
                    ('pricelist_id', '=', pricelist.id),
                    ('cloud_sync_id', '=', item_data['id'])
                ], limit=1)

            vals = {
                'pricelist_id': pricelist.id,
                'applied_on': item_data.get('applied_on', '3_global'),
                'min_quantity': item_data.get('min_quantity', 1),
                'compute_price': item_data.get('compute_price', 'fixed'),
                'fixed_price': item_data.get('fixed_price', 0),
                'percent_price': item_data.get('percent_price', 0),
            }

            # Manejar producto
            if item_data.get('product_id'):
                vals['product_id'] = item_data['product_id']
            if item_data.get('product_tmpl_id'):
                vals['product_tmpl_id'] = item_data['product_tmpl_id']
            if item_data.get('categ_id'):
                vals['categ_id'] = item_data['categ_id']

            # Manejar fechas
            if item_data.get('date_start'):
                vals['date_start'] = self._parse_datetime(item_data['date_start'])
            if item_data.get('date_end'):
                vals['date_end'] = self._parse_datetime(item_data['date_end'])

            if existing_item:
                existing_item.write(vals)
            else:
                vals['cloud_sync_id'] = item_data.get('id')
                PricelistItem.create(vals)

    # ==================== SERIALIZADORES DE PROGRAMAS DE LEALTAD ====================

    @api.model
    def serialize_loyalty_program(self, program):
        """
        Serializa un programa de lealtad para sincronización.

        Args:
            program: Registro loyalty.program

        Returns:
            dict: Datos serializados
        """
        data = {
            'id': program.id,
            'name': program.name,
            'active': program.active,
            'program_type': program.program_type,
            'applies_on': program.applies_on if hasattr(program, 'applies_on') else None,
            'trigger': program.trigger if hasattr(program, 'trigger') else None,
            'portal_visible': program.portal_visible if hasattr(program, 'portal_visible') else None,
            'portal_point_name': program.portal_point_name if hasattr(program, 'portal_point_name') else None,
            'date_from': program.date_from.isoformat() if program.date_from else None,
            'date_to': program.date_to.isoformat() if program.date_to else None,
            'limit_usage': program.limit_usage if hasattr(program, 'limit_usage') else None,
            'max_usage': program.max_usage if hasattr(program, 'max_usage') else None,
            'company_id': program.company_id.id if program.company_id else None,
            'currency_id': program.currency_id.id if program.currency_id else None,
            # Campos de sincronización
            'cloud_sync_id': program.cloud_sync_id if hasattr(program, 'cloud_sync_id') else None,
            'id_database_old': program.id_database_old if hasattr(program, 'id_database_old') else None,
            # Reglas y recompensas
            'rules': [],
            'rewards': [],
        }

        # Serializar reglas
        for rule in program.rule_ids:
            data['rules'].append(self.serialize_loyalty_rule(rule))

        # Serializar recompensas
        for reward in program.reward_ids:
            data['rewards'].append(self.serialize_loyalty_reward(reward))

        return data

    @api.model
    def serialize_loyalty_rule(self, rule):
        """
        Serializa una regla de lealtad.

        Args:
            rule: Registro loyalty.rule

        Returns:
            dict: Datos serializados
        """
        data = {
            'id': rule.id,
            'program_id': rule.program_id.id if rule.program_id else None,
            'mode': rule.mode if hasattr(rule, 'mode') else None,
            'minimum_qty': rule.minimum_qty if hasattr(rule, 'minimum_qty') else None,
            'minimum_amount': rule.minimum_amount if hasattr(rule, 'minimum_amount') else None,
            'minimum_amount_tax_mode': rule.minimum_amount_tax_mode if hasattr(rule, 'minimum_amount_tax_mode') else None,
            'reward_point_mode': rule.reward_point_mode if hasattr(rule, 'reward_point_mode') else None,
            'reward_point_amount': rule.reward_point_amount if hasattr(rule, 'reward_point_amount') else None,
            'product_ids': rule.product_ids.ids if rule.product_ids else [],
            'product_category_id': rule.product_category_id.id if hasattr(rule, 'product_category_id') and rule.product_category_id else None,
            'product_domain': rule.product_domain if hasattr(rule, 'product_domain') else None,
            # Campos de sincronización
            'cloud_sync_id': rule.cloud_sync_id if hasattr(rule, 'cloud_sync_id') else None,
            'id_database_old': rule.id_database_old if hasattr(rule, 'id_database_old') else None,
        }
        return data

    @api.model
    def serialize_loyalty_reward(self, reward):
        """
        Serializa una recompensa de lealtad.

        Args:
            reward: Registro loyalty.reward

        Returns:
            dict: Datos serializados
        """
        data = {
            'id': reward.id,
            'program_id': reward.program_id.id if reward.program_id else None,
            'description': reward.description if hasattr(reward, 'description') else None,
            'reward_type': reward.reward_type if hasattr(reward, 'reward_type') else None,
            'discount': reward.discount if hasattr(reward, 'discount') else None,
            'discount_mode': reward.discount_mode if hasattr(reward, 'discount_mode') else None,
            'discount_applicability': reward.discount_applicability if hasattr(reward, 'discount_applicability') else None,
            'discount_max_amount': reward.discount_max_amount if hasattr(reward, 'discount_max_amount') else None,
            'discount_product_ids': reward.discount_product_ids.ids if hasattr(reward, 'discount_product_ids') and reward.discount_product_ids else [],
            'discount_product_category_id': reward.discount_product_category_id.id if hasattr(reward, 'discount_product_category_id') and reward.discount_product_category_id else None,
            'discount_product_domain': reward.discount_product_domain if hasattr(reward, 'discount_product_domain') else None,
            'reward_product_id': reward.reward_product_id.id if hasattr(reward, 'reward_product_id') and reward.reward_product_id else None,
            'reward_product_qty': reward.reward_product_qty if hasattr(reward, 'reward_product_qty') else None,
            'required_points': reward.required_points if hasattr(reward, 'required_points') else None,
            'clear_wallet': reward.clear_wallet if hasattr(reward, 'clear_wallet') else None,
            # Campos de sincronización
            'cloud_sync_id': reward.cloud_sync_id if hasattr(reward, 'cloud_sync_id') else None,
            'id_database_old': reward.id_database_old if hasattr(reward, 'id_database_old') else None,
        }
        return data

    @api.model
    def deserialize_loyalty_program(self, data, sync_config=None):
        """
        Deserializa datos de programa de lealtad (PULL: cloud -> offline).

        Este método se usa para sincronización unidireccional del cloud al offline.
        Los programas de lealtad, reglas y recompensas se crean/actualizan localmente.

        Args:
            data: Diccionario con datos del programa
            sync_config: Configuración de sincronización (opcional)

        Returns:
            loyalty.program: Programa creado o actualizado
        """
        Program = self.env['loyalty.program'].sudo()

        # Debug: log incoming data
        cloud_id = data.get('id')
        _logger.info(
            "deserialize_loyalty_program: cloud_id=%s, name=%s, data_keys=%s",
            cloud_id, data.get('name'), list(data.keys())
        )

        # Buscar programa existente
        program = Program.find_or_create_from_sync(data)

        # Debug: verificar si se encontró y qué cloud_sync_id tiene
        if program:
            _logger.info(
                "Programa existente encontrado: ID=%s, cloud_sync_id=%s, name=%s",
                program.id, program.cloud_sync_id, program.name
            )
        else:
            # Buscar programas con mismo cloud_sync_id para debug
            if cloud_id:
                existing = Program.search([('cloud_sync_id', '=', cloud_id)], limit=1)
                _logger.info(
                    "No se encontró programa. Búsqueda por cloud_sync_id=%s resultó: %s",
                    cloud_id, existing.id if existing else "No encontrado"
                )

        # Preparar valores
        vals = self._prepare_loyalty_program_vals(data)

        if program:
            program.write(vals)
            _logger.info(f'Programa de lealtad actualizado desde cloud: {program.name} (ID: {program.id})')
        else:
            program = Program.create(vals)
            _logger.info(f'Programa de lealtad creado desde cloud: {program.name} (ID: {program.id})')

        # Marcar cloud_sync_id y estado de sincronización
        sync_vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }

        # Siempre establecer cloud_sync_id si viene en los datos
        # Esto asegura que programas existentes sin cloud_sync_id lo reciban
        if data.get('id'):
            cloud_sync_id_value = int(data['id'])
            if not program.cloud_sync_id or program.cloud_sync_id != cloud_sync_id_value:
                sync_vals['cloud_sync_id'] = cloud_sync_id_value
                _logger.info(
                    "Estableciendo cloud_sync_id=%s para programa %s (anterior: %s)",
                    cloud_sync_id_value, program.id, program.cloud_sync_id
                )

        program.write(sync_vals)
        _logger.info(
            "Programa %s guardado con cloud_sync_id=%s, sync_state=%s",
            program.id, program.cloud_sync_id, program.sync_state
        )

        # Procesar reglas
        if data.get('rules'):
            self._process_loyalty_rules(program, data['rules'])

        # Procesar recompensas
        if data.get('rewards'):
            self._process_loyalty_rewards(program, data['rewards'])

        _logger.info(f'Programa {program.name}: {len(data.get("rules", []))} reglas, {len(data.get("rewards", []))} recompensas procesadas')

        return program

    def _prepare_loyalty_program_vals(self, data):
        """Prepara valores para crear/actualizar un programa de lealtad."""
        vals = {
            'name': data.get('name'),
            'active': data.get('active', True),
            'program_type': data.get('program_type', 'promotion'),
        }

        if data.get('applies_on'):
            vals['applies_on'] = data['applies_on']
        if data.get('trigger'):
            vals['trigger'] = data['trigger']
        if data.get('date_from'):
            vals['date_from'] = self._parse_datetime(data['date_from'])
        if data.get('date_to'):
            vals['date_to'] = self._parse_datetime(data['date_to'])
        if data.get('id_database_old'):
            vals['id_database_old'] = str(data['id_database_old'])

        # Limpiar valores None
        vals = {k: v for k, v in vals.items() if v is not None}

        return vals

    def _process_loyalty_rules(self, program, rules_data):
        """Procesa las reglas de un programa de lealtad (PULL: cloud -> offline)."""
        LoyaltyRule = self.env['loyalty.rule'].sudo()

        for rule_data in rules_data:
            existing_rule = None
            if rule_data.get('id'):
                existing_rule = LoyaltyRule.search([
                    ('program_id', '=', program.id),
                    ('cloud_sync_id', '=', rule_data['id'])
                ], limit=1)

            vals = {
                'program_id': program.id,
            }

            # Agregar campos si existen
            for field in ['mode', 'minimum_qty', 'minimum_amount', 'minimum_amount_tax_mode',
                         'reward_point_mode', 'reward_point_amount', 'product_domain']:
                if rule_data.get(field) is not None:
                    vals[field] = rule_data[field]

            # Manejar product_ids - mapear por cloud_sync_id o barcode si es necesario
            if rule_data.get('product_ids'):
                # Intentar mapear productos por sus IDs
                product_ids = []
                for pid in rule_data['product_ids']:
                    # Buscar producto por cloud_sync_id primero
                    product = self.env['product.product'].sudo().search([
                        ('cloud_sync_id', '=', pid)
                    ], limit=1)
                    if not product:
                        # Si no existe por cloud_sync_id, buscar por ID directo
                        product = self.env['product.product'].sudo().browse(pid)
                        if product.exists():
                            product_ids.append(product.id)
                    else:
                        product_ids.append(product.id)
                if product_ids:
                    vals['product_ids'] = [(6, 0, product_ids)]

            if existing_rule:
                existing_rule.write(vals)
                # Marcar como sincronizado
                existing_rule.write({
                    'sync_state': 'synced',
                    'last_sync_date': fields.Datetime.now(),
                })
            else:
                vals['cloud_sync_id'] = rule_data.get('id')
                vals['sync_state'] = 'synced'
                vals['last_sync_date'] = fields.Datetime.now()
                LoyaltyRule.create(vals)

    def _process_loyalty_rewards(self, program, rewards_data):
        """Procesa las recompensas de un programa de lealtad (PULL: cloud -> offline)."""
        LoyaltyReward = self.env['loyalty.reward'].sudo()

        for reward_data in rewards_data:
            existing_reward = None
            if reward_data.get('id'):
                existing_reward = LoyaltyReward.search([
                    ('program_id', '=', program.id),
                    ('cloud_sync_id', '=', reward_data['id'])
                ], limit=1)

            vals = {
                'program_id': program.id,
            }

            # Agregar campos si existen
            for field in ['description', 'reward_type', 'discount', 'discount_mode',
                         'discount_applicability', 'discount_max_amount', 'reward_product_qty',
                         'required_points', 'clear_wallet', 'discount_product_domain']:
                if reward_data.get(field) is not None:
                    vals[field] = reward_data[field]

            # Manejar reward_product_id - mapear por cloud_sync_id
            if reward_data.get('reward_product_id'):
                product = self.env['product.product'].sudo().search([
                    ('cloud_sync_id', '=', reward_data['reward_product_id'])
                ], limit=1)
                if not product:
                    product = self.env['product.product'].sudo().browse(reward_data['reward_product_id'])
                    if product.exists():
                        vals['reward_product_id'] = product.id
                else:
                    vals['reward_product_id'] = product.id

            # Manejar discount_product_ids - mapear por cloud_sync_id
            if reward_data.get('discount_product_ids'):
                product_ids = []
                for pid in reward_data['discount_product_ids']:
                    product = self.env['product.product'].sudo().search([
                        ('cloud_sync_id', '=', pid)
                    ], limit=1)
                    if not product:
                        product = self.env['product.product'].sudo().browse(pid)
                        if product.exists():
                            product_ids.append(product.id)
                    else:
                        product_ids.append(product.id)
                if product_ids:
                    vals['discount_product_ids'] = [(6, 0, product_ids)]

            if existing_reward:
                existing_reward.write(vals)
                # Marcar como sincronizado
                existing_reward.write({
                    'sync_state': 'synced',
                    'last_sync_date': fields.Datetime.now(),
                })
            else:
                vals['cloud_sync_id'] = reward_data.get('id')
                vals['sync_state'] = 'synced'
                vals['last_sync_date'] = fields.Datetime.now()
                LoyaltyReward.create(vals)

    # ==================== SERIALIZADORES DE POSICIÓN FISCAL ====================

    @api.model
    def serialize_fiscal_position(self, fiscal_position):
        """
        Serializa una posición fiscal para sincronización.

        Args:
            fiscal_position: Registro account.fiscal.position

        Returns:
            dict: Datos serializados
        """
        data = {
            'id': fiscal_position.id,
            'name': fiscal_position.name,
            'active': fiscal_position.active if hasattr(fiscal_position, 'active') else True,
            'sequence': fiscal_position.sequence if hasattr(fiscal_position, 'sequence') else 10,
            'auto_apply': fiscal_position.auto_apply if hasattr(fiscal_position, 'auto_apply') else False,
            'company_id': fiscal_position.company_id.id if fiscal_position.company_id else None,
            'country_id': fiscal_position.country_id.id if fiscal_position.country_id else None,
            'country_group_id': fiscal_position.country_group_id.id if hasattr(fiscal_position, 'country_group_id') and fiscal_position.country_group_id else None,
            'state_ids': fiscal_position.state_ids.ids if hasattr(fiscal_position, 'state_ids') and fiscal_position.state_ids else [],
            'zip_from': fiscal_position.zip_from if hasattr(fiscal_position, 'zip_from') else None,
            'zip_to': fiscal_position.zip_to if hasattr(fiscal_position, 'zip_to') else None,
            'vat_required': fiscal_position.vat_required if hasattr(fiscal_position, 'vat_required') else False,
            'note': fiscal_position.note if hasattr(fiscal_position, 'note') else None,
            # Campos de sincronización
            'cloud_sync_id': fiscal_position.cloud_sync_id if hasattr(fiscal_position, 'cloud_sync_id') else None,
            'id_database_old': fiscal_position.id_database_old if hasattr(fiscal_position, 'id_database_old') else None,
            # Campos adicionales para descuentos institucionales
            'is_institutional': fiscal_position.is_institutional if hasattr(fiscal_position, 'is_institutional') else False,
            'institutional_discount': fiscal_position.institutional_discount if hasattr(fiscal_position, 'institutional_discount') else 0,
            # Mapeos de impuestos
            'tax_mappings': [],
            'account_mappings': [],
        }

        # Serializar mapeos de impuestos
        for tax_map in fiscal_position.tax_ids:
            data['tax_mappings'].append({
                'id': tax_map.id,
                'tax_src_id': tax_map.tax_src_id.id if tax_map.tax_src_id else None,
                'tax_src_name': tax_map.tax_src_id.name if tax_map.tax_src_id else None,
                'tax_dest_id': tax_map.tax_dest_id.id if tax_map.tax_dest_id else None,
                'tax_dest_name': tax_map.tax_dest_id.name if tax_map.tax_dest_id else None,
            })

        # Serializar mapeos de cuentas
        for account_map in fiscal_position.account_ids:
            data['account_mappings'].append({
                'id': account_map.id,
                'account_src_id': account_map.account_src_id.id if account_map.account_src_id else None,
                'account_src_code': account_map.account_src_id.code if account_map.account_src_id else None,
                'account_dest_id': account_map.account_dest_id.id if account_map.account_dest_id else None,
                'account_dest_code': account_map.account_dest_id.code if account_map.account_dest_id else None,
            })

        return data

    @api.model
    def deserialize_fiscal_position(self, data, sync_config=None):
        """
        Deserializa datos de posición fiscal.

        Args:
            data: Diccionario con datos de la posición fiscal
            sync_config: Configuración de sincronización (opcional)

        Returns:
            account.fiscal.position: Posición fiscal creada o actualizada
        """
        FiscalPosition = self.env['account.fiscal.position'].sudo()

        # Buscar posición fiscal existente
        fiscal_position = FiscalPosition.find_or_create_from_sync(data)

        # Preparar valores
        vals = self._prepare_fiscal_position_vals(data)

        if fiscal_position:
            fiscal_position.write(vals)
            _logger.info(f'Posición fiscal actualizada: {fiscal_position.name} (ID: {fiscal_position.id})')
        else:
            fiscal_position = FiscalPosition.create(vals)
            _logger.info(f'Posición fiscal creada: {fiscal_position.name} (ID: {fiscal_position.id})')

        # Marcar cloud_sync_id
        if data.get('id') and not fiscal_position.cloud_sync_id:
            fiscal_position.write({'cloud_sync_id': data['id']})

        # Procesar mapeos de impuestos
        if data.get('tax_mappings'):
            self._process_fiscal_position_taxes(fiscal_position, data['tax_mappings'])

        return fiscal_position

    def _prepare_fiscal_position_vals(self, data):
        """Prepara valores para crear/actualizar una posición fiscal."""
        vals = {
            'name': data.get('name'),
        }

        # Campos opcionales
        if data.get('sequence'):
            vals['sequence'] = data['sequence']
        if data.get('auto_apply') is not None:
            vals['auto_apply'] = data['auto_apply']
        if data.get('vat_required') is not None:
            vals['vat_required'] = data['vat_required']
        if data.get('note'):
            vals['note'] = data['note']
        if data.get('is_institutional') is not None:
            vals['is_institutional'] = data['is_institutional']
        if data.get('institutional_discount'):
            vals['institutional_discount'] = data['institutional_discount']
        if data.get('id_database_old'):
            vals['id_database_old'] = str(data['id_database_old'])

        # Manejar país
        if data.get('country_id'):
            country = self.env['res.country'].sudo().browse(data['country_id'])
            if country.exists():
                vals['country_id'] = country.id

        # Limpiar valores None
        vals = {k: v for k, v in vals.items() if v is not None}

        return vals

    def _process_fiscal_position_taxes(self, fiscal_position, tax_mappings):
        """Procesa los mapeos de impuestos de una posición fiscal."""
        FPTax = self.env['account.fiscal.position.tax'].sudo()
        AccountTax = self.env['account.tax'].sudo()

        for tax_data in tax_mappings:
            existing = None
            if tax_data.get('id'):
                existing = FPTax.search([
                    ('position_id', '=', fiscal_position.id),
                    ('cloud_sync_id', '=', tax_data['id'])
                ], limit=1)

            # Buscar impuestos origen y destino
            tax_src = None
            tax_dest = None

            if tax_data.get('tax_src_id'):
                tax_src = AccountTax.browse(tax_data['tax_src_id'])
                if not tax_src.exists():
                    tax_src = None
            if not tax_src and tax_data.get('tax_src_name'):
                tax_src = AccountTax.search([('name', '=', tax_data['tax_src_name'])], limit=1)

            if tax_data.get('tax_dest_id'):
                tax_dest = AccountTax.browse(tax_data['tax_dest_id'])
                if not tax_dest.exists():
                    tax_dest = None
            if not tax_dest and tax_data.get('tax_dest_name'):
                tax_dest = AccountTax.search([('name', '=', tax_data['tax_dest_name'])], limit=1)

            if tax_src:  # tax_dest puede ser False (eliminar impuesto)
                vals = {
                    'position_id': fiscal_position.id,
                    'tax_src_id': tax_src.id,
                    'tax_dest_id': tax_dest.id if tax_dest else False,
                }

                if existing:
                    existing.write(vals)
                else:
                    vals['cloud_sync_id'] = tax_data.get('id')
                    FPTax.create(vals)

    # ==================== SERIALIZADORES DE NOTAS DE CRÉDITO ====================

    @api.model
    def serialize_refund(self, refund_order):
        """
        Serializa una orden de reembolso/nota de crédito para sincronización.

        Args:
            refund_order: Registro pos.order que es un reembolso

        Returns:
            dict: Datos serializados
        """
        # Usar el serializador de orden base
        data = self.serialize_order(refund_order)

        # Agregar campos específicos de reembolso
        data['is_refund'] = True
        data['refunded_order_ids'] = refund_order.refunded_order_ids.ids if hasattr(refund_order, 'refunded_order_ids') else []

        # Buscar la orden original si existe
        if hasattr(refund_order, 'refunded_order_ids') and refund_order.refunded_order_ids:
            original_order = refund_order.refunded_order_ids[0]
            data['original_order'] = {
                'id': original_order.id,
                'name': original_order.name,
                'pos_reference': original_order.pos_reference,
            }

        return data

    def _prepare_partner_vals(self, data):
        """
        Prepara los valores para crear/actualizar un partner.

        Args:
            data: Diccionario con datos del partner

        Returns:
            dict: Valores preparados para Odoo
        """
        vals = {
            'name': data.get('name'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'mobile': data.get('mobile'),
            'vat': data.get('vat'),
            'street': data.get('street'),
            'street2': data.get('street2'),
            'city': data.get('city'),
            'zip': data.get('zip'),
            'type': data.get('type', 'contact'),
            'comment': data.get('comment'),
            'barcode': data.get('barcode'),
            'ref': data.get('ref'),
        }

        # Manejar país
        if data.get('country_id'):
            country = self.env['res.country'].sudo().browse(data['country_id'])
            if country.exists():
                vals['country_id'] = country.id
        elif data.get('country_code'):
            country = self.env['res.country'].sudo().search([
                ('code', '=', data['country_code'])
            ], limit=1)
            if country:
                vals['country_id'] = country.id

        # Manejar estado/provincia
        if data.get('state_id'):
            state = self.env['res.country.state'].sudo().browse(data['state_id'])
            if state.exists():
                vals['state_id'] = state.id
        elif data.get('state_code') and vals.get('country_id'):
            state = self.env['res.country.state'].sudo().search([
                ('code', '=', data['state_code']),
                ('country_id', '=', vals['country_id'])
            ], limit=1)
            if state:
                vals['state_id'] = state.id

        # Manejar lista de precios
        if data.get('property_product_pricelist'):
            pricelist = self.env['product.pricelist'].sudo().browse(
                data['property_product_pricelist']
            )
            if pricelist.exists():
                vals['property_product_pricelist'] = pricelist.id

        # Manejar id_database_old (como string)
        # IMPORTANTE: Solo copiar id_database_old si ya existe, NO auto-generar desde 'id'
        # porque los IDs de diferentes bases de datos pueden coincidir causando falsos positivos
        if data.get('id_database_old'):
            vals['id_database_old'] = str(data['id_database_old'])

        # Manejar l10n_latam_identification_type_id (tipo de identificación: cédula, RUC, etc.)
        if data.get('l10n_latam_identification_type_id') or data.get('l10n_latam_identification_type_name'):
            IdentificationType = self.env['l10n_latam.identification.type'].sudo()

            id_type = None
            # Primero intentar por ID directo
            if data.get('l10n_latam_identification_type_id'):
                id_type = IdentificationType.browse(data['l10n_latam_identification_type_id'])
                if not id_type.exists():
                    id_type = None

            # Si no existe por ID, buscar por nombre
            if not id_type and data.get('l10n_latam_identification_type_name'):
                id_type = IdentificationType.search([
                    ('name', '=', data['l10n_latam_identification_type_name'])
                ], limit=1)

            if id_type:
                vals['l10n_latam_identification_type_id'] = id_type.id

        # Limpiar valores None
        vals = {k: v for k, v in vals.items() if v is not None}

        return vals

    # ==================== SERIALIZADORES DE SESIÓN POS ====================

    @api.model
    def serialize_session(self, session):
        """
        Serializa una sesión POS para sincronización.

        Args:
            session: Registro pos.session

        Returns:
            dict: Datos serializados
        """
        data = {
            'id': session.id,
            'name': session.name,
            'state': session.state,
            'start_at': session.start_at.isoformat() if session.start_at else None,
            'stop_at': session.stop_at.isoformat() if session.stop_at else None,
            'sequence_number': session.sequence_number,
            'login_number': session.login_number,
            'cash_control': session.cash_control,
            'cash_register_balance_start': session.cash_register_balance_start,
            'cash_register_balance_end': session.cash_register_balance_end,
            'cash_register_balance_end_real': session.cash_register_balance_end_real,
            # Relaciones
            'config_id': session.config_id.id if session.config_id else None,
            'config_name': session.config_id.name if session.config_id else None,
            'user_id': session.user_id.id if session.user_id else None,
            'user_name': session.user_id.name if session.user_id else None,
            # Campos de sincronización
            'cloud_sync_id': session.cloud_sync_id if hasattr(session, 'cloud_sync_id') else None,
            'id_database_old': session.id_database_old if hasattr(session, 'id_database_old') else None,
            # Totales
            'total_payments_amount': session.total_payments_amount if hasattr(session, 'total_payments_amount') else 0,
            'order_count': session.order_count if hasattr(session, 'order_count') else 0,
        }

        # Serializar statement_lines si existe cash_control
        if session.cash_control and hasattr(session, 'statement_line_ids'):
            data['statement_lines'] = []
            for line in session.statement_line_ids:
                data['statement_lines'].append({
                    'id': line.id,
                    'amount': line.amount,
                    'date': line.date.isoformat() if line.date else None,
                    'payment_ref': line.payment_ref if hasattr(line, 'payment_ref') else None,
                })

        return data

    @api.model
    def deserialize_session(self, data, sync_config=None):
        """
        Deserializa datos de sesión POS.

        CORREGIDO: Maneja correctamente sesiones existentes para evitar error
        "Ya hay otra sesión abierta para este punto de venta".

        Args:
            data: Diccionario con datos de la sesión
            sync_config: Configuración de sincronización (opcional)

        Returns:
            pos.session: Sesión creada o actualizada
        """
        Session = self.env['pos.session'].sudo()
        PosConfig = self.env['pos.config'].sudo()

        # Buscar sesión existente por cloud_sync_id o nombre
        session = None
        if data.get('cloud_sync_id') and 'cloud_sync_id' in Session._fields:
            session = Session.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)

        if not session and data.get('name'):
            session = Session.search([('name', '=', data['name'])], limit=1)

        # Preparar valores
        vals = self._prepare_session_vals(data)

        if session:
            # Actualizar sesión existente (solo campos seguros)
            safe_vals = {k: v for k, v in vals.items() if k not in ['config_id', 'state']}
            if safe_vals:
                session.write(safe_vals)
            _logger.info(f'Sesión actualizada: {session.name} (ID: {session.id})')
        else:
            # Para crear sesión necesitamos config_id válido
            config_id = vals.get('config_id')
            if not config_id:
                _logger.warning(f'No se puede crear sesión sin config_id: {data.get("name")}')
                return None

            # CORRECCIÓN: Verificar si ya existe una sesión abierta para este config_id
            # Si existe, usar esa sesión en lugar de crear una nueva
            existing_open_session = Session.search([
                ('config_id', '=', config_id),
                ('state', 'in', ['opening_control', 'opened']),
            ], limit=1)

            if existing_open_session:
                _logger.info(
                    f'Ya existe sesión abierta para config_id {config_id}: '
                    f'{existing_open_session.name} (ID: {existing_open_session.id}). '
                    f'Usando sesión existente en lugar de crear nueva.'
                )
                session = existing_open_session
                # Actualizar cloud_sync_id si es necesario
                if data.get('id') and 'cloud_sync_id' in Session._fields and not session.cloud_sync_id:
                    session.write({'cloud_sync_id': data['id']})
            else:
                # No hay sesión abierta, crear una nueva
                try:
                    session = Session.create(vals)
                    _logger.info(f'Sesión creada: {session.name} (ID: {session.id})')
                except Exception as e:
                    # Si falla la creación, intentar usar una sesión existente del mismo config
                    _logger.warning(f'Error creando sesión: {e}. Buscando sesión alternativa...')
                    session = Session.search([
                        ('config_id', '=', config_id),
                    ], limit=1, order='id desc')
                    if session:
                        _logger.info(f'Usando sesión existente: {session.name}')
                    else:
                        _logger.error(f'No se pudo crear ni encontrar sesión para config_id {config_id}')
                        return None

        # Marcar cloud_sync_id si no se hizo antes
        if session and data.get('id') and 'cloud_sync_id' in Session._fields and not session.cloud_sync_id:
            session.write({'cloud_sync_id': data['id']})

        return session

    def _prepare_session_vals(self, data):
        """Prepara valores para crear/actualizar una sesión."""
        vals = {}

        # Campos básicos
        if data.get('state'):
            vals['state'] = data['state']
        if data.get('start_at'):
            vals['start_at'] = self._parse_datetime(data['start_at'])
        if data.get('stop_at'):
            vals['stop_at'] = self._parse_datetime(data['stop_at'])
        if data.get('sequence_number'):
            vals['sequence_number'] = data['sequence_number']
        if data.get('login_number'):
            vals['login_number'] = data['login_number']

        # Cash control
        if data.get('cash_register_balance_start') is not None:
            vals['cash_register_balance_start'] = data['cash_register_balance_start']
        if data.get('cash_register_balance_end_real') is not None:
            vals['cash_register_balance_end_real'] = data['cash_register_balance_end_real']

        # Buscar config_id
        if data.get('config_id'):
            config = self.env['pos.config'].sudo().browse(data['config_id'])
            if config.exists():
                vals['config_id'] = config.id
        elif data.get('config_name'):
            config = self.env['pos.config'].sudo().search([
                ('name', '=', data['config_name'])
            ], limit=1)
            if config:
                vals['config_id'] = config.id

        # Buscar user_id
        if data.get('user_id'):
            user = self.env['res.users'].sudo().browse(data['user_id'])
            if user.exists():
                vals['user_id'] = user.id
        elif data.get('user_name'):
            user = self.env['res.users'].sudo().search([
                ('name', '=', data['user_name'])
            ], limit=1)
            if user:
                vals['user_id'] = user.id

        if data.get('id_database_old'):
            vals['id_database_old'] = str(data['id_database_old'])

        return vals

    # ==================== SERIALIZADORES DE JSON.STORAGE ====================

    @api.model
    def deserialize_json_storage(self, data, sync_config=None):
        """
        Deserializa datos de json.storage recibidos de una sucursal.

        Args:
            data: Diccionario con datos del registro json.storage
            sync_config: Configuración de sincronización (opcional)

        Returns:
            json.storage: Registro creado o actualizado
        """
        JsonStorage = self.env['json.storage'].sudo()
        cloud_id = data.get('id')

        _logger.info(f'Deserializando json.storage cloud_id={cloud_id}')

        # Buscar registro existente con múltiples verificaciones
        existing = None

        # VERIFICACIÓN 1: Por cloud_sync_id
        if cloud_id and 'cloud_sync_id' in JsonStorage._fields:
            existing = JsonStorage.search([
                ('cloud_sync_id', '=', cloud_id)
            ], limit=1)
            if existing:
                _logger.info(f'json.storage encontrado por cloud_sync_id={cloud_id}')

        # VERIFICACIÓN 2: Por ID directo (cuando offline y cloud comparten BD)
        if not existing and cloud_id:
            existing_by_id = JsonStorage.browse(cloud_id)
            if existing_by_id.exists():
                existing = existing_by_id
                _logger.info(f'json.storage encontrado por ID directo={cloud_id}')

        # VERIFICACIÓN 3: Por pos_order si está disponible
        if not existing and data.get('pos_order'):
            pos_order_id = data['pos_order']
            # Buscar la orden por cloud_sync_id o id_database_old
            PosOrder = self.env['pos.order'].sudo()
            order = None
            if 'cloud_sync_id' in PosOrder._fields:
                order = PosOrder.search([('cloud_sync_id', '=', pos_order_id)], limit=1)
            if not order:
                order = PosOrder.search([('id_database_old', '=', str(pos_order_id))], limit=1)
            # También buscar por ID directo
            if not order:
                direct_order = PosOrder.browse(pos_order_id)
                if direct_order.exists():
                    order = direct_order
            if order:
                existing = JsonStorage.search([('pos_order', '=', order.id)], limit=1)
                if existing:
                    _logger.info(f'json.storage encontrado por pos_order={order.name}')

        # NOTA: Se eliminó la verificación por client_invoice + id_database_old_invoice_client
        # porque esos valores son del CLIENTE, no de la TRANSACCIÓN, y causaba duplicados.
        # Las verificaciones válidas son: cloud_sync_id, ID directo, y pos_order.

        # Preparar valores
        vals = {
            'json_data': data.get('json_data'),
            'employee': data.get('employee'),
            'id_point_of_sale': data.get('id_point_of_sale'),
            'client_invoice': data.get('client_invoice'),
            'id_database_old_invoice_client': data.get('id_database_old_invoice_client'),
            'is_access_key': data.get('is_access_key', False),
            'sent': data.get('sent', False),
            'db_key': data.get('db_key'),
        }

        # Resolver pos_order_id (Many2one a pos.config)
        if data.get('pos_order_id'):
            config_id = data['pos_order_id']
            pos_config = self.env['pos.config'].sudo().browse(config_id)
            if pos_config.exists():
                vals['pos_order_id'] = pos_config.id
            else:
                # Intentar buscar por cloud_sync_id
                if 'cloud_sync_id' in self.env['pos.config']._fields:
                    pos_config = self.env['pos.config'].sudo().search([
                        ('cloud_sync_id', '=', config_id)
                    ], limit=1)
                    if pos_config:
                        vals['pos_order_id'] = pos_config.id

        # Resolver pos_order (Many2one a pos.order)
        # CRÍTICO: El ID del offline NO existe en el cloud, debemos buscar por otros criterios
        pos_order = None
        PosOrder = self.env['pos.order'].sudo()
        order_id = data.get('pos_order')

        _logger.info(f'Resolviendo pos_order para json.storage: offline_id={order_id}, ref={data.get("_pos_order_ref")}')

        if order_id:
            # 1. Buscar por id_database_old (el ID original del offline guardado en el cloud)
            pos_order = PosOrder.search([('id_database_old', '=', str(order_id))], limit=1)
            if pos_order:
                _logger.info(f'pos_order encontrado por id_database_old: {pos_order.name} (ID: {pos_order.id})')

            # 2. Buscar por cloud_sync_id (si el cloud asignó este ID)
            if not pos_order and 'cloud_sync_id' in PosOrder._fields:
                pos_order = PosOrder.search([('cloud_sync_id', '=', order_id)], limit=1)
                if pos_order:
                    _logger.info(f'pos_order encontrado por cloud_sync_id: {pos_order.name}')

            # 3. Buscar por ID directo (solo si es el mismo servidor)
            if not pos_order:
                direct_order = PosOrder.browse(order_id)
                if direct_order.exists():
                    pos_order = direct_order
                    _logger.info(f'pos_order encontrado por ID directo: {pos_order.name}')

        # 4. Buscar por referencia de nombre si está disponible
        if not pos_order and data.get('_pos_order_ref'):
            pos_order = PosOrder.search([('name', '=', data['_pos_order_ref'])], limit=1)
            if pos_order:
                _logger.info(f'pos_order encontrado por nombre: {pos_order.name}')

        # 5. Si aún no se encuentra, buscar la orden más reciente que coincida con client_invoice
        if not pos_order and data.get('client_invoice'):
            pos_order = PosOrder.search([
                ('partner_id.vat', '=', data['client_invoice']),
            ], order='create_date desc', limit=1)
            if pos_order:
                _logger.info(f'pos_order encontrado por partner VAT: {pos_order.name}')

        if pos_order:
            vals['pos_order'] = pos_order.id
        else:
            _logger.warning(
                f'No se pudo encontrar pos_order para json.storage. '
                f'offline_id={order_id}, ref={data.get("_pos_order_ref")}, '
                f'client={data.get("client_invoice")}. '
                f'El registro se creará SIN referencia a pos.order.'
            )

        if existing:
            # Actualizar registro existente
            existing.with_context(skip_sync_queue=True).write(vals)
            if 'sync_state' in JsonStorage._fields:
                existing.with_context(skip_sync_queue=True).write({'sync_state': 'synced'})
            _logger.info(f'json.storage actualizado: {existing.id}')
            return existing
        else:
            # Crear nuevo registro
            if cloud_id and 'cloud_sync_id' in JsonStorage._fields:
                vals['cloud_sync_id'] = cloud_id
            if 'sync_state' in JsonStorage._fields:
                vals['sync_state'] = 'synced'
            record = JsonStorage.with_context(skip_sync_queue=True).create(vals)
            _logger.info(f'json.storage creado: {record.id} (cloud_id={cloud_id})')
            return record

    @api.model
    def deserialize_json_note_credit(self, data, sync_config=None):
        """
        Deserializa datos de json.note.credit recibidos de una sucursal.

        Args:
            data: Diccionario con datos del registro json.note.credit
            sync_config: Configuración de sincronización (opcional)

        Returns:
            json.note.credit: Registro creado o actualizado
        """
        JsonNoteCredit = self.env['json.note.credit'].sudo()
        cloud_id = data.get('id')

        _logger.info(f'Deserializando json.note.credit cloud_id={cloud_id}')

        # Buscar registro existente
        existing = None
        if cloud_id and 'cloud_sync_id' in JsonNoteCredit._fields:
            existing = JsonNoteCredit.search([
                ('cloud_sync_id', '=', cloud_id)
            ], limit=1)

        # Preparar valores
        vals = {
            'json_data': data.get('json_data'),
            'id_point_of_sale': data.get('id_point_of_sale'),
            'date_invoices': data.get('date_invoices'),
            'is_access_key': data.get('is_access_key', False),
            'sent': data.get('sent', False),
            'db_key': data.get('db_key'),
        }

        # Resolver pos_order_id (Many2one a pos.config)
        if data.get('pos_order_id'):
            config_id = data['pos_order_id']
            pos_config = self.env['pos.config'].sudo().browse(config_id)
            if pos_config.exists():
                vals['pos_order_id'] = pos_config.id
            else:
                # Intentar buscar por cloud_sync_id
                if 'cloud_sync_id' in self.env['pos.config']._fields:
                    pos_config = self.env['pos.config'].sudo().search([
                        ('cloud_sync_id', '=', config_id)
                    ], limit=1)
                    if pos_config:
                        vals['pos_order_id'] = pos_config.id

        if existing:
            # Actualizar registro existente
            existing.with_context(skip_sync_queue=True).write(vals)
            if 'sync_state' in JsonNoteCredit._fields:
                existing.with_context(skip_sync_queue=True).write({'sync_state': 'synced'})
            _logger.info(f'json.note.credit actualizado: {existing.id}')
            return existing
        else:
            # Crear nuevo registro
            if cloud_id and 'cloud_sync_id' in JsonNoteCredit._fields:
                vals['cloud_sync_id'] = cloud_id
            if 'sync_state' in JsonNoteCredit._fields:
                vals['sync_state'] = 'synced'
            record = JsonNoteCredit.with_context(skip_sync_queue=True).create(vals)
            _logger.info(f'json.note.credit creado: {record.id} (cloud_id={cloud_id})')
            return record

    # ==================== SERIALIZADORES DE INSTITUTION ====================

    @api.model
    def serialize_institution(self, institution):
        """
        Serializa una institución para sincronización.

        Args:
            institution: Registro institution

        Returns:
            dict: Datos serializados de la institución
        """
        return {
            'id': institution.id,
            'id_institutions': institution.id_institutions,
            'name': institution.name,
            'ruc_institution': institution.ruc_institution,
            'agreement_date': institution.agreement_date.isoformat() if institution.agreement_date else None,
            'address': institution.address,
            'type_credit_institution': institution.type_credit_institution,
            'cellphone': institution.cellphone,
            'court_day': institution.court_day,
            'additional_discount_percentage': institution.additional_discount_percentage,
            'pvp': institution.pvp,
            'cloud_sync_id': institution.cloud_sync_id if hasattr(institution, 'cloud_sync_id') and institution.cloud_sync_id else None,
            'id_database_old': institution.id_database_old if hasattr(institution, 'id_database_old') else None,
        }

    @api.model
    def deserialize_institution(self, data, sync_config=None):
        """
        Deserializa datos de institución recibidos.

        Args:
            data: Diccionario con datos del registro institution
            sync_config: Configuración de sincronización (opcional)

        Returns:
            institution: Registro creado o actualizado
        """
        Institution = self.env['institution'].sudo()
        cloud_id = data.get('id')

        _logger.info(f'Deserializando institution cloud_id={cloud_id}, name={data.get("name")}')

        # Buscar registro existente por múltiples criterios
        existing = None

        # 1. Por cloud_sync_id
        if cloud_id and 'cloud_sync_id' in Institution._fields:
            existing = Institution.search([('cloud_sync_id', '=', cloud_id)], limit=1)

        # 2. Por ID directo (mismo servidor)
        if not existing and cloud_id:
            direct = Institution.browse(cloud_id)
            if direct.exists():
                existing = direct

        # 3. Por id_institutions (identificador único de negocio)
        if not existing and data.get('id_institutions'):
            existing = Institution.search([
                ('id_institutions', '=', data.get('id_institutions'))
            ], limit=1)

        # 4. Por nombre + tipo
        if not existing and data.get('name'):
            existing = Institution.search([
                ('name', '=', data.get('name')),
                ('type_credit_institution', '=', data.get('type_credit_institution'))
            ], limit=1)

        # Preparar valores
        vals = {
            'id_institutions': data.get('id_institutions'),
            'name': data.get('name'),
            'ruc_institution': data.get('ruc_institution'),
            'address': data.get('address'),
            'type_credit_institution': data.get('type_credit_institution'),
            'cellphone': data.get('cellphone'),
            'court_day': data.get('court_day'),
            'additional_discount_percentage': data.get('additional_discount_percentage', 0),
            'pvp': data.get('pvp', '1'),
        }

        # Parsear fecha
        if data.get('agreement_date'):
            from datetime import date as date_type
            try:
                vals['agreement_date'] = date_type.fromisoformat(data['agreement_date'])
            except (ValueError, TypeError):
                pass

        if existing:
            existing.with_context(skip_sync_queue=True).write(vals)
            if cloud_id and 'cloud_sync_id' in Institution._fields and not existing.cloud_sync_id:
                existing.with_context(skip_sync_queue=True).write({'cloud_sync_id': cloud_id})
            _logger.info(f'institution actualizada: {existing.name} (ID={existing.id})')
            return existing
        else:
            if cloud_id and 'cloud_sync_id' in Institution._fields:
                vals['cloud_sync_id'] = cloud_id
            record = Institution.with_context(skip_sync_queue=True).create(vals)
            _logger.info(f'institution creada: {record.name} (ID={record.id})')
            return record

    @api.model
    def serialize_institution_client(self, institution_client):
        """
        Serializa una relación institución-cliente para sincronización.

        Args:
            institution_client: Registro institution.client

        Returns:
            dict: Datos serializados
        """
        return {
            'id': institution_client.id,
            'institution_id': institution_client.institution_id.id,
            'institution_id_institutions': institution_client.institution_id.id_institutions,
            'institution_name': institution_client.institution_id.name,
            'partner_id': institution_client.partner_id.id,
            'partner_vat': institution_client.partner_id.vat,
            'partner_name': institution_client.partner_id.name,
            'available_amount': institution_client.available_amount,
            'sale': institution_client.sale,
            'cloud_sync_id': institution_client.cloud_sync_id if hasattr(institution_client, 'cloud_sync_id') and institution_client.cloud_sync_id else None,
        }

    @api.model
    def deserialize_institution_client(self, data, sync_config=None):
        """
        Deserializa datos de relación institución-cliente recibidos.

        IMPORTANTE: Este método sincroniza los cambios de crédito/saldo entre
        offline y cloud, asegurando que el available_amount refleje
        los consumos realizados en cualquier punto.

        Args:
            data: Diccionario con datos del registro institution.client
            sync_config: Configuración de sincronización (opcional)

        Returns:
            institution.client: Registro creado o actualizado
        """
        InstitutionClient = self.env['institution.client'].sudo()
        source_id = data.get('id')  # ID del servidor origen (offline o cloud)

        _logger.info(
            f'Deserializando institution.client source_id={source_id}, '
            f'institution_id_institutions={data.get("institution_id_institutions")}, '
            f'partner_vat={data.get("partner_vat")}, '
            f'available_amount={data.get("available_amount")}, sale={data.get("sale")}'
        )

        # Buscar registro existente por múltiples criterios
        # IMPORTANTE: Priorizar búsqueda por institution+partner que es la clave natural
        existing = None
        institution = None
        partner = None

        # 1. PRIMERO buscar por institución + partner (relación única y más confiable)
        # Encontrar la institución por id_institutions (código único)
        if data.get('institution_id_institutions'):
            institution = self.env['institution'].sudo().search([
                ('id_institutions', '=', data['institution_id_institutions'])
            ], limit=1)
            if institution:
                _logger.debug(f'Institución encontrada por id_institutions: {institution.name}')

        # Buscar partner por VAT (cédula/RUC - único)
        if data.get('partner_vat'):
            partner = self.env['res.partner'].sudo().search([
                ('vat', '=', data['partner_vat'])
            ], limit=1)
            if partner:
                _logger.debug(f'Partner encontrado por VAT: {partner.name}')

        # Buscar institution.client por la combinación única
        if institution and partner:
            existing = InstitutionClient.search([
                ('institution_id', '=', institution.id),
                ('partner_id', '=', partner.id)
            ], limit=1)
            if existing:
                _logger.info(
                    f'institution.client encontrado por institution+partner: '
                    f'id={existing.id}, partner={partner.name}, institution={institution.name}'
                )

        # 2. Si no encontramos por institution+partner, buscar por cloud_sync_id
        if not existing and source_id and 'cloud_sync_id' in InstitutionClient._fields:
            existing = InstitutionClient.search([('cloud_sync_id', '=', source_id)], limit=1)
            if existing:
                _logger.info(f'institution.client encontrado por cloud_sync_id: {existing.id}')

        # NOTA: NO buscamos por ID directo porque los IDs pueden ser diferentes
        # entre servidores offline y cloud

        # Preparar valores para actualizar
        vals = {}
        cloud_available = data.get('available_amount')
        cloud_sale = data.get('sale')

        # Verificar si hay cambios pendientes en la cola de sync para este registro
        # Esto indica que el local tiene cambios que aún no se han enviado al cloud
        has_pending_sync = False
        if existing:
            SyncQueue = self.env['pos.sync.queue'].sudo()
            pending = SyncQueue.search([
                ('model_name', '=', 'institution.client'),
                ('record_id', '=', existing.id),
                ('state', 'in', ['pending', 'processing'])
            ], limit=1)
            has_pending_sync = bool(pending)
            if has_pending_sync:
                _logger.info(
                    f'institution.client tiene cambios pendientes de sync: '
                    f'queue_id={pending.id}, state={pending.state}'
                )

        # Lógica de actualización inteligente para available_amount:
        # - Si hay cambios locales pendientes → NO sobrescribir (el local es más reciente)
        # - Si el local es menor que el cloud y no hay pendientes → el cloud puede haber aumentado (admin)
        # - Si el local es mayor que el cloud → actualizar (consumo en otro punto o admin redujo)
        if existing and cloud_available is not None:
            local_available = existing.available_amount

            if has_pending_sync:
                # HAY CAMBIOS PENDIENTES: proteger el valor local
                _logger.info(
                    f'PROTEGIENDO available_amount local (hay sync pendiente): '
                    f'local={local_available}, cloud={cloud_available}'
                )
                # NO agregamos available_amount a vals
            elif local_available < cloud_available:
                # Local es MENOR: podría ser consumo local no sincronizado
                # Verificar si el cupo (sale) cambió - si cambió, el admin modificó algo
                if cloud_sale is not None and existing.sale != cloud_sale:
                    # El cupo cambió, probablemente el admin ajustó todo
                    vals['available_amount'] = cloud_available
                    _logger.info(
                        f'Actualizando available_amount (cupo cambió): '
                        f'local={local_available} -> cloud={cloud_available}'
                    )
                else:
                    # El cupo es igual pero available_amount local es menor = consumo local
                    _logger.info(
                        f'PROTEGIENDO available_amount local (consumo no sincronizado): '
                        f'local={local_available}, cloud={cloud_available}'
                    )
                    # NO agregamos available_amount a vals
            else:
                # Local es MAYOR o IGUAL: actualizar con valor del cloud
                vals['available_amount'] = cloud_available
        elif cloud_available is not None:
            # No existe registro local, usar el valor del cloud
            vals['available_amount'] = cloud_available

        # El cupo (sale) siempre se actualiza desde el cloud (el admin lo controla)
        if cloud_sale is not None:
            vals['sale'] = cloud_sale

        if existing:
            # ACTUALIZAR registro existente
            old_amount = existing.available_amount
            if vals:
                existing.with_context(skip_sync_queue=True).write(vals)
            # Guardar el source_id como cloud_sync_id si no está configurado
            if source_id and 'cloud_sync_id' in InstitutionClient._fields and not existing.cloud_sync_id:
                existing.with_context(skip_sync_queue=True).write({'cloud_sync_id': source_id})
            _logger.info(
                f'institution.client ACTUALIZADO: partner={existing.partner_id.name}, '
                f'institution={existing.institution_id.name}, '
                f'available_amount: {old_amount} -> {existing.available_amount}'
            )
            return existing
        else:
            # CREAR nuevo registro - usar institution y partner ya encontrados
            if not institution or not partner:
                _logger.warning(
                    f'No se puede crear institution.client: '
                    f'institution={institution}, partner={partner}, '
                    f'institution_id_institutions={data.get("institution_id_institutions")}, '
                    f'partner_vat={data.get("partner_vat")}'
                )
                return None

            vals['institution_id'] = institution.id
            vals['partner_id'] = partner.id
            if 'available_amount' not in vals:
                vals['available_amount'] = data.get('sale', 0)
            if 'sale' not in vals:
                vals['sale'] = data.get('sale', 0)

            if source_id and 'cloud_sync_id' in InstitutionClient._fields:
                vals['cloud_sync_id'] = source_id

            record = InstitutionClient.with_context(skip_sync_queue=True).create(vals)
            _logger.info(
                f'institution.client CREADO: partner={record.partner_id.name}, '
                f'institution={record.institution_id.name}, '
                f'available_amount={record.available_amount}'
            )
            return record

    # ==================== SERIALIZADORES DE TRANSFERENCIAS DE STOCK ====================

    @api.model
    def serialize_stock_picking(self, picking):
        """
        Serializa una transferencia de stock para sincronización.

        Args:
            picking: Registro stock.picking

        Returns:
            dict: Datos serializados
        """
        data = {
            'id': picking.id,
            'name': picking.name,
            'state': picking.state,
            'origin': picking.origin,
            'note': picking.note,
            'scheduled_date': picking.scheduled_date.isoformat() if picking.scheduled_date else None,
            'date_done': picking.date_done.isoformat() if picking.date_done else None,
            # Tipo de transferencia
            'picking_type_id': picking.picking_type_id.id if picking.picking_type_id else None,
            'picking_type_code': picking.picking_type_id.code if picking.picking_type_id else None,
            'picking_type_name': picking.picking_type_id.name if picking.picking_type_id else None,
            # Ubicaciones
            'location_id': picking.location_id.id if picking.location_id else None,
            'location_name': picking.location_id.complete_name if picking.location_id else None,
            'location_dest_id': picking.location_dest_id.id if picking.location_dest_id else None,
            'location_dest_name': picking.location_dest_id.complete_name if picking.location_dest_id else None,
            # Partner
            'partner_id': picking.partner_id.id if picking.partner_id else None,
            'partner_name': picking.partner_id.name if picking.partner_id else None,
            # Campos personalizados de stock_transfer_in_pos
            'type_transfer': picking.type_transfer if hasattr(picking, 'type_transfer') else None,
            # Campos de sincronización
            'cloud_sync_id': picking.cloud_sync_id if hasattr(picking, 'cloud_sync_id') else None,
            'id_database_old': picking.id_database_old if hasattr(picking, 'id_database_old') else None,
            # Líneas de movimiento
            'moves': [],
        }

        # Serializar líneas de movimiento
        for move in picking.move_ids:
            move_data = {
                'id': move.id,
                'product_id': move.product_id.id if move.product_id else None,
                'product_name': move.product_id.name if move.product_id else None,
                'product_default_code': move.product_id.default_code if move.product_id else None,
                'product_barcode': move.product_id.barcode if move.product_id else None,
                'product_uom_qty': move.product_uom_qty,
                'quantity': move.quantity if hasattr(move, 'quantity') else move.product_uom_qty,
                'product_uom': move.product_uom.id if move.product_uom else None,
                'product_uom_name': move.product_uom.name if move.product_uom else None,
                'state': move.state,
                'name': move.name,
            }
            data['moves'].append(move_data)

        return data

    @api.model
    def deserialize_stock_picking(self, data, sync_config=None):
        """
        Deserializa datos de transferencia de stock.

        Args:
            data: Diccionario con datos de la transferencia
            sync_config: Configuración de sincronización (opcional)

        Returns:
            stock.picking: Transferencia creada o actualizada
        """
        Picking = self.env['stock.picking'].sudo()

        # Buscar transferencia existente
        picking = None
        if data.get('cloud_sync_id') and 'cloud_sync_id' in Picking._fields:
            picking = Picking.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)

        if not picking and data.get('name'):
            picking = Picking.search([('name', '=', data['name'])], limit=1)

        # Preparar valores
        vals = self._prepare_stock_picking_vals(data)

        if picking:
            # Solo actualizar si no está validado
            if picking.state not in ('done', 'cancel'):
                picking.write(vals)
                _logger.info(f'Transferencia actualizada: {picking.name} (ID: {picking.id})')
        else:
            if not vals.get('picking_type_id'):
                _logger.warning(f'No se puede crear transferencia sin picking_type_id: {data.get("name")}')
                return None
            picking = Picking.create(vals)
            _logger.info(f'Transferencia creada: {picking.name} (ID: {picking.id})')

        # Marcar cloud_sync_id
        if data.get('id') and 'cloud_sync_id' in Picking._fields and not picking.cloud_sync_id:
            picking.write({'cloud_sync_id': data['id']})

        # Procesar líneas de movimiento
        if data.get('moves'):
            self._process_stock_moves(picking, data['moves'])

        return picking

    def _prepare_stock_picking_vals(self, data):
        """Prepara valores para crear/actualizar una transferencia."""
        vals = {
            'origin': data.get('origin'),
            'note': data.get('note'),
        }

        # Buscar tipo de picking
        if data.get('picking_type_id'):
            picking_type = self.env['stock.picking.type'].sudo().browse(data['picking_type_id'])
            if picking_type.exists():
                vals['picking_type_id'] = picking_type.id
        elif data.get('picking_type_code'):
            picking_type = self.env['stock.picking.type'].sudo().search([
                ('code', '=', data['picking_type_code'])
            ], limit=1)
            if picking_type:
                vals['picking_type_id'] = picking_type.id

        # Buscar ubicaciones
        if data.get('location_id'):
            location = self.env['stock.location'].sudo().browse(data['location_id'])
            if location.exists():
                vals['location_id'] = location.id
        elif data.get('location_name'):
            location = self.env['stock.location'].sudo().search([
                ('complete_name', '=', data['location_name'])
            ], limit=1)
            if location:
                vals['location_id'] = location.id

        if data.get('location_dest_id'):
            location_dest = self.env['stock.location'].sudo().browse(data['location_dest_id'])
            if location_dest.exists():
                vals['location_dest_id'] = location_dest.id
        elif data.get('location_dest_name'):
            location_dest = self.env['stock.location'].sudo().search([
                ('complete_name', '=', data['location_dest_name'])
            ], limit=1)
            if location_dest:
                vals['location_dest_id'] = location_dest.id

        # Fechas
        if data.get('scheduled_date'):
            vals['scheduled_date'] = self._parse_datetime(data['scheduled_date'])

        # Campo personalizado type_transfer
        if data.get('type_transfer'):
            vals['type_transfer'] = data['type_transfer']

        if data.get('id_database_old'):
            vals['id_database_old'] = str(data['id_database_old'])

        # Limpiar valores None
        vals = {k: v for k, v in vals.items() if v is not None}

        return vals

    def _process_stock_moves(self, picking, moves_data):
        """Procesa las líneas de movimiento de una transferencia."""
        StockMove = self.env['stock.move'].sudo()

        for move_data in moves_data:
            # Buscar producto
            product = None
            if move_data.get('product_id'):
                product = self.env['product.product'].sudo().browse(move_data['product_id'])
                if not product.exists():
                    product = None
            if not product and move_data.get('product_barcode'):
                product = self.env['product.product'].sudo().search([
                    ('barcode', '=', move_data['product_barcode'])
                ], limit=1)
            if not product and move_data.get('product_default_code'):
                product = self.env['product.product'].sudo().search([
                    ('default_code', '=', move_data['product_default_code'])
                ], limit=1)

            if not product:
                _logger.warning(f'Producto no encontrado para movimiento: {move_data}')
                continue

            # Buscar movimiento existente
            existing_move = None
            if move_data.get('id') and 'cloud_sync_id' in StockMove._fields:
                existing_move = StockMove.search([
                    ('picking_id', '=', picking.id),
                    ('cloud_sync_id', '=', move_data['id'])
                ], limit=1)

            if not existing_move:
                existing_move = StockMove.search([
                    ('picking_id', '=', picking.id),
                    ('product_id', '=', product.id)
                ], limit=1)

            vals = {
                'product_id': product.id,
                'product_uom_qty': move_data.get('product_uom_qty', 1),
                'name': move_data.get('name') or product.name,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            }

            if existing_move:
                if existing_move.state not in ('done', 'cancel'):
                    existing_move.write(vals)
            else:
                vals['picking_id'] = picking.id
                if move_data.get('id') and 'cloud_sync_id' in StockMove._fields:
                    vals['cloud_sync_id'] = move_data['id']
                StockMove.create(vals)

    # ==================== MIGRACIÓN INICIAL ====================

    @api.model
    def run_initial_migration(self, sync_config):
        """
        Ejecuta migración inicial desde PRINCIPAL a OFFLINE.

        Descarga todos los datos maestros por lotes.
        Optimizado: No requiere campos computados almacenados.

        Args:
            sync_config: Registro pos.sync.config

        Returns:
            dict: Resultado de la migración
        """
        _logger.info(f'[MIGRACIÓN] Iniciando migración inicial para {sync_config.name}')

        result = {
            'success': True,
            'models_processed': {},
            'total_records': 0,
            'errors': [],
            'start_time': datetime.now().isoformat(),
        }

        try:
            # 1. Obtener manifiesto
            manifest = self._get_migration_manifest(sync_config)
            if not manifest.get('success'):
                result['success'] = False
                result['errors'].append(manifest.get('error', 'Error obteniendo manifiesto'))
                return result

            sync_order = manifest.get('sync_order', [])
            batch_size = manifest.get('recommended_batch_size', 500)

            # Mapeo de nombres en manifiesto a modelos Odoo
            model_mapping = {
                'product_categories': 'product.category',
                'uom': 'uom.uom',
                'taxes': 'account.tax',
                'fiscal_positions': 'account.fiscal.position',
                'payment_methods': 'pos.payment.method',
                'partners': 'res.partner',
                'pricelists': 'product.pricelist',
                'product_templates': 'product.template',
                'products': 'product.product',
                'pricelist_items': 'product.pricelist.item',
                'loyalty_programs': 'loyalty.program',
                'loyalty_rules': 'loyalty.rule',
                'loyalty_rewards': 'loyalty.reward',
            }

            # 2. Procesar cada modelo en orden
            for entity_name in sync_order:
                model_name = model_mapping.get(entity_name)
                if not model_name:
                    continue

                total_for_model = manifest.get('manifest', {}).get(entity_name, 0)
                if total_for_model == 0:
                    continue

                _logger.info(f'[MIGRACIÓN] Descargando {entity_name}: {total_for_model} registros')

                model_result = self._migrate_model(
                    sync_config, model_name, total_for_model, batch_size
                )

                result['models_processed'][entity_name] = model_result
                result['total_records'] += model_result.get('imported', 0)

                if model_result.get('errors'):
                    result['errors'].extend(model_result['errors'])

            result['end_time'] = datetime.now().isoformat()

            # Log resultado
            self.env['pos.sync.log'].sudo().log(
                sync_config_id=sync_config.id,
                action='full_sync',
                message=f'Migración completada: {result["total_records"]} registros',
                level='info',
                records_processed=result['total_records'],
            )

        except Exception as e:
            _logger.error(f'[MIGRACIÓN] Error: {str(e)}')
            import traceback
            _logger.error(traceback.format_exc())
            result['success'] = False
            result['errors'].append(str(e))

        return result

    def _get_migration_manifest(self, sync_config):
        """Obtiene el manifiesto de migración desde el servidor."""
        payload = {
            'warehouse_id': sync_config.warehouse_id.id,
        }

        return self._send_to_cloud(
            sync_config,
            '/pos_offline_sync/migration/manifest',
            payload
        )

    def _migrate_model(self, sync_config, model_name, total, batch_size):
        """
        Migra un modelo completo por lotes.

        Args:
            sync_config: Configuración de sincronización
            model_name: Nombre del modelo Odoo
            total: Total de registros a migrar
            batch_size: Tamaño de lote

        Returns:
            dict: Resultado de la migración del modelo
        """
        result = {
            'model': model_name,
            'total': total,
            'imported': 0,
            'updated': 0,
            'errors': [],
        }

        offset = 0
        while offset < total:
            try:
                # Descargar lote
                response = self._send_to_cloud(
                    sync_config,
                    '/pos_offline_sync/migration/pull_batch',
                    {
                        'model': model_name,
                        'limit': batch_size,
                        'offset': offset,
                        'warehouse_id': sync_config.warehouse_id.id,
                    }
                )

                if not response.get('success'):
                    result['errors'].append(
                        f'Error en lote {offset}: {response.get("error")}'
                    )
                    break

                records = response.get('records', [])
                if not records:
                    break

                # Importar lote
                batch_result = self._import_migration_batch(model_name, records)
                result['imported'] += batch_result.get('created', 0)
                result['updated'] += batch_result.get('updated', 0)

                if batch_result.get('errors'):
                    result['errors'].extend(batch_result['errors'])

                offset += len(records)
                _logger.info(
                    f'[MIGRACIÓN] {model_name}: {offset}/{total} procesados'
                )

                # No continuar si no hay más
                if not response.get('has_more'):
                    break

            except Exception as e:
                result['errors'].append(f'Error en lote {offset}: {str(e)}')
                break

        return result

    def _import_migration_batch(self, model_name, records):
        """
        Importa un lote de registros para migración.

        Args:
            model_name: Nombre del modelo
            records: Lista de registros a importar

        Returns:
            dict: Resultado de la importación
        """
        result = {'created': 0, 'updated': 0, 'errors': []}

        if model_name not in self.env:
            result['errors'].append(f'Modelo {model_name} no existe')
            return result

        Model = self.env[model_name].sudo()

        for record_data in records:
            try:
                with self.env.cr.savepoint():
                    existing = self._find_existing_for_migration(
                        Model, model_name, record_data
                    )

                    vals = self._prepare_migration_vals(model_name, record_data)

                    if existing:
                        existing.write(vals)
                        result['updated'] += 1
                    else:
                        Model.create(vals)
                        result['created'] += 1

            except Exception as e:
                error_msg = f'Error importando {model_name} id={record_data.get("id")}: {str(e)}'
                _logger.warning(error_msg)
                result['errors'].append(error_msg)

        return result

    def _find_existing_for_migration(self, Model, model_name, record_data):
        """
        Busca registro existente para migración.
        IMPORTANTE: Evitar duplicados usando múltiples criterios de búsqueda.
        """
        # 1. Por id_database_old (el ID del PRINCIPAL) - PRIORIDAD MÁXIMA
        if 'id_database_old' in Model._fields and record_data.get('id_database_old'):
            existing = Model.search([
                ('id_database_old', '=', str(record_data['id_database_old']))
            ], limit=1)
            if existing:
                return existing

        # 2. Por cloud_sync_id
        if 'cloud_sync_id' in Model._fields and record_data.get('id'):
            existing = Model.search([
                ('cloud_sync_id', '=', record_data['id'])
            ], limit=1)
            if existing:
                return existing

        # ==================== RES.PARTNER ====================
        if model_name == 'res.partner':
            # Por VAT (RUC/Cédula) - más confiable
            if record_data.get('vat'):
                existing = Model.search([('vat', '=', record_data['vat'])], limit=1)
                if existing:
                    return existing

            # Por email (si existe)
            if record_data.get('email'):
                existing = Model.search([('email', '=', record_data['email'])], limit=1)
                if existing:
                    return existing

            # Por nombre + teléfono (combinación única)
            if record_data.get('name') and record_data.get('phone'):
                existing = Model.search([
                    ('name', '=', record_data['name']),
                    ('phone', '=', record_data['phone'])
                ], limit=1)
                if existing:
                    return existing

            # Por nombre + móvil
            if record_data.get('name') and record_data.get('mobile'):
                existing = Model.search([
                    ('name', '=', record_data['name']),
                    ('mobile', '=', record_data['mobile'])
                ], limit=1)
                if existing:
                    return existing

            # Por nombre exacto para empresas
            if record_data.get('name') and record_data.get('is_company'):
                existing = Model.search([
                    ('name', '=', record_data['name']),
                    ('is_company', '=', True)
                ], limit=1)
                if existing:
                    return existing

            return None

        # ==================== PRODUCT.PRODUCT ====================
        if model_name == 'product.product':
            if record_data.get('barcode'):
                existing = Model.search([('barcode', '=', record_data['barcode'])], limit=1)
                if existing:
                    return existing
            if record_data.get('default_code'):
                existing = Model.search([('default_code', '=', record_data['default_code'])], limit=1)
                if existing:
                    return existing
            if record_data.get('name'):
                existing = Model.search([('name', '=', record_data['name'])], limit=1)
                if existing:
                    return existing

        # ==================== PRODUCT.TEMPLATE ====================
        if model_name == 'product.template':
            if record_data.get('barcode'):
                existing = Model.search([('barcode', '=', record_data['barcode'])], limit=1)
                if existing:
                    return existing
            if record_data.get('default_code'):
                existing = Model.search([('default_code', '=', record_data['default_code'])], limit=1)
                if existing:
                    return existing
            if record_data.get('name'):
                existing = Model.search([('name', '=', record_data['name'])], limit=1)
                if existing:
                    return existing

        # ==================== OTROS MODELOS ====================
        if model_name == 'product.category' and record_data.get('complete_name'):
            return Model.search([('complete_name', '=', record_data['complete_name'])], limit=1)

        if model_name == 'uom.uom' and record_data.get('name'):
            return Model.search([('name', '=', record_data['name'])], limit=1)

        if model_name == 'account.tax' and record_data.get('name'):
            return Model.search([
                ('name', '=', record_data['name']),
                ('type_tax_use', '=', record_data.get('type_tax_use', 'sale'))
            ], limit=1)

        if model_name == 'pos.payment.method' and record_data.get('name'):
            return Model.search([('name', '=', record_data['name'])], limit=1)

        if model_name == 'product.pricelist' and record_data.get('name'):
            return Model.search([('name', '=', record_data['name'])], limit=1)

        if model_name == 'loyalty.program' and record_data.get('name'):
            return Model.search([('name', '=', record_data['name'])], limit=1)

        return None

    def _prepare_migration_vals(self, model_name, record_data):
        """
        Prepara valores para crear/actualizar durante migración.

        Args:
            model_name: Nombre del modelo
            record_data: Datos del registro

        Returns:
            dict: Valores preparados
        """
        vals = dict(record_data)

        # Remover campos que no deben copiarse
        fields_to_remove = [
            'id', 'create_date', 'create_uid', 'write_date', 'write_uid',
            '__last_update', 'display_name',
        ]
        for field in fields_to_remove:
            vals.pop(field, None)

        # Guardar ID original como id_database_old si existe el campo
        Model = self.env[model_name]
        if 'id_database_old' in Model._fields and record_data.get('id'):
            vals['id_database_old'] = record_data['id']

        # Manejar campos relacionales
        vals = self._resolve_migration_relations(model_name, vals)

        # Limpiar campos auxiliares que no deben escribirse en la BD
        helper_fields = [
            'categ_name', 'uom_name', 'uom_po_name', 'parent_name',
            'pricelist_name', 'program_name', 'journal_name', 'category_name',
            'complete_name',  # Solo se usa para buscar, no para escribir
        ]
        for field in helper_fields:
            vals.pop(field, None)

        # Validar que solo quedan campos válidos del modelo
        Model = self.env[model_name]
        valid_fields = set(Model._fields.keys())
        invalid_fields = [k for k in vals.keys() if k not in valid_fields]
        for field in invalid_fields:
            _logger.warning(f"[MIGRACIÓN] Removiendo campo inválido '{field}' de {model_name}")
            vals.pop(field, None)

        return vals

    def _resolve_migration_relations(self, model_name, vals):
        """
        Resuelve campos relacionales para migración.

        Busca registros locales por id_database_old o por nombre.
        IMPORTANTE: Solo resolver campos que existen en el modelo específico.
        """
        # Campos específicos para productos (product.product y product.template)
        if model_name in ('product.product', 'product.template'):
            self._resolve_field_by_name_or_id(vals, 'categ_id', 'product.category', 'categ_name', 'complete_name')
            # UOM son campos requeridos - usar método especial que nunca devuelve NULL
            self._resolve_uom_field(vals, 'uom_id', 'uom_name')
            self._resolve_uom_field(vals, 'uom_po_id', 'uom_po_name')
            # Resolver taxes_id (Many2many)
            if 'taxes_id' in vals:
                vals['taxes_id'] = self._resolve_taxes(vals.get('taxes_id', []))

        # Campos específicos para product.product
        if model_name == 'product.product' and 'product_tmpl_id' in vals:
            self._resolve_field_by_id_database_old(vals, 'product_tmpl_id', 'product.template')

        # Campos específicos para product.category
        if model_name == 'product.category':
            # Resolver parent_id por complete_name o id_database_old
            parent_name = vals.pop('parent_name', None)
            parent_id_old = vals.get('parent_id')

            if parent_id_old or parent_name:
                Category = self.env['product.category'].sudo()
                parent = None

                # 1. Buscar por id_database_old del padre
                if parent_id_old and 'id_database_old' in Category._fields:
                    parent = Category.search([
                        ('id_database_old', '=', str(parent_id_old))
                    ], limit=1)

                # 2. Si no, buscar por complete_name
                if not parent and parent_name:
                    parent = Category.search([
                        ('complete_name', '=', parent_name)
                    ], limit=1)

                # 3. Si aún no existe, crear la jerarquía de padres
                if not parent and parent_name:
                    parent = self._create_category_hierarchy(parent_name)

                vals['parent_id'] = parent.id if parent else False
            else:
                vals['parent_id'] = False

        # Campos específicos para pricelist items
        if model_name == 'product.pricelist.item':
            self._resolve_field_by_name_or_id(vals, 'pricelist_id', 'product.pricelist', 'pricelist_name', 'name')
            self._resolve_field_by_id_database_old(vals, 'product_id', 'product.product')
            self._resolve_field_by_id_database_old(vals, 'product_tmpl_id', 'product.template')

        # Campos específicos para loyalty
        if model_name in ('loyalty.rule', 'loyalty.reward'):
            self._resolve_field_by_name_or_id(vals, 'program_id', 'loyalty.program', 'program_name', 'name')

        # Campos específicos para res.partner
        if model_name == 'res.partner':
            # Resolver country_id por nombre
            if 'country_name' in vals:
                country_name = vals.pop('country_name', None)
                if country_name and vals.get('country_id'):
                    Country = self.env['res.country'].sudo()
                    country = Country.search([('name', '=', country_name)], limit=1)
                    if not country:
                        country = Country.search([('name', 'ilike', country_name)], limit=1)
                    vals['country_id'] = country.id if country else False
                elif not vals.get('country_id'):
                    vals['country_id'] = False

            # Resolver state_id por nombre y código
            state_name = vals.pop('state_name', None)
            state_code = vals.pop('state_code', None)
            if state_name or state_code:
                State = self.env['res.country.state'].sudo()
                state = None
                country_id = vals.get('country_id')

                if state_code and country_id:
                    state = State.search([
                        ('code', '=', state_code),
                        ('country_id', '=', country_id)
                    ], limit=1)

                if not state and state_name and country_id:
                    state = State.search([
                        ('name', '=', state_name),
                        ('country_id', '=', country_id)
                    ], limit=1)

                if state:
                    vals['state_id'] = state.id

            # Resolver l10n_latam_identification_type_id por nombre
            if 'l10n_latam_identification_type_name' in vals:
                type_name = vals.pop('l10n_latam_identification_type_name', None)
                if type_name and 'l10n_latam_identification_type_id' in self.env['res.partner']._fields:
                    IdType = self.env['l10n_latam.identification.type'].sudo()
                    id_type = IdType.search([('name', '=', type_name)], limit=1)
                    if id_type:
                        vals['l10n_latam_identification_type_id'] = id_type.id

            # Resolver property_product_pricelist por nombre
            if 'property_product_pricelist_name' in vals:
                pricelist_name = vals.pop('property_product_pricelist_name', None)
                if pricelist_name:
                    Pricelist = self.env['product.pricelist'].sudo()
                    pricelist = Pricelist.search([('name', '=', pricelist_name)], limit=1)
                    if pricelist:
                        vals['property_product_pricelist'] = pricelist.id

        # Resolver journal para payment methods
        if model_name == 'pos.payment.method':
            self._resolve_field_by_name_or_id(vals, 'journal_id', 'account.journal', 'journal_name', 'name')

        return vals

    def _resolve_field_by_name_or_id(self, vals, field_name, model_name, name_field, search_field):
        """Resuelve un campo relacional buscando por nombre o id_database_old."""
        if field_name not in vals or not vals[field_name]:
            return

        Model = self.env[model_name].sudo()
        old_id = vals[field_name]
        name_value = vals.get(name_field)

        # Primero buscar por id_database_old
        if 'id_database_old' in Model._fields:
            local_record = Model.search([('id_database_old', '=', old_id)], limit=1)
            if local_record:
                vals[field_name] = local_record.id
                vals.pop(name_field, None)
                return

        # Luego buscar por nombre
        if name_value:
            local_record = Model.search([(search_field, '=', name_value)], limit=1)
            if local_record:
                vals[field_name] = local_record.id
                vals.pop(name_field, None)
                return

        # Si no se encuentra, dejar False
        vals[field_name] = False
        vals.pop(name_field, None)

    def _resolve_field_by_id_database_old(self, vals, field_name, model_name):
        """Resuelve un campo relacional solo por id_database_old."""
        if field_name not in vals or not vals[field_name]:
            return

        Model = self.env[model_name].sudo()
        old_id = vals[field_name]

        if 'id_database_old' in Model._fields:
            local_record = Model.search([('id_database_old', '=', old_id)], limit=1)
            if local_record:
                vals[field_name] = local_record.id
                return

        vals[field_name] = False

    def _resolve_taxes(self, taxes_data):
        """
        Resuelve impuestos por nombre.

        Args:
            taxes_data: Lista de dicts con 'id' y 'name'

        Returns:
            list: Comando Many2many [(6, 0, [ids])]
        """
        if not taxes_data:
            return [(6, 0, [])]

        Tax = self.env['account.tax'].sudo()
        resolved_ids = []

        for tax_info in taxes_data:
            if isinstance(tax_info, dict):
                tax_name = tax_info.get('name')
                if tax_name:
                    local_tax = Tax.search([
                        ('name', '=', tax_name),
                        ('type_tax_use', '=', 'sale')
                    ], limit=1)
                    if local_tax:
                        resolved_ids.append(local_tax.id)

        return [(6, 0, resolved_ids)]

    def _resolve_uom_field(self, vals, field_name, name_field):
        """
        Resuelve campo UOM buscando por nombre.
        Si no se encuentra, usa el UOM por defecto (Unidades).
        IMPORTANTE: UOM es campo requerido en product.template, nunca debe ser NULL.
        """
        Uom = self.env['uom.uom'].sudo()
        old_id = vals.get(field_name)
        name_value = vals.get(name_field)

        # Si no hay valor, usar UOM por defecto
        if not old_id and not name_value:
            default_uom = self._get_default_uom()
            if default_uom:
                vals[field_name] = default_uom.id
            vals.pop(name_field, None)
            return

        # Primero buscar por id_database_old
        if old_id and 'id_database_old' in Uom._fields:
            local_record = Uom.search([('id_database_old', '=', old_id)], limit=1)
            if local_record:
                vals[field_name] = local_record.id
                vals.pop(name_field, None)
                return

        # Luego buscar por nombre exacto
        if name_value:
            local_record = Uom.search([('name', '=', name_value)], limit=1)
            if local_record:
                vals[field_name] = local_record.id
                vals.pop(name_field, None)
                return

            # Buscar por nombre similar (ilike)
            local_record = Uom.search([('name', 'ilike', name_value)], limit=1)
            if local_record:
                vals[field_name] = local_record.id
                vals.pop(name_field, None)
                return

        # Si no se encuentra nada, usar UOM por defecto
        default_uom = self._get_default_uom()
        if default_uom:
            vals[field_name] = default_uom.id
            _logger.warning("UOM '%s' no encontrado, usando default '%s'", name_value or old_id, default_uom.name)
        else:
            _logger.error("No se pudo encontrar UOM por defecto, campo %s quedará sin valor", field_name)
        vals.pop(name_field, None)

    def _create_category_hierarchy(self, complete_name):
        """
        Crea una jerarquía de categorías desde un complete_name.

        Args:
            complete_name: Nombre completo como "POS / Food / Drinks"

        Returns:
            product.category: La categoría final (o la última creada)
        """
        if not complete_name:
            return self.env['product.category'].browse()

        Category = self.env['product.category'].sudo()

        # Verificar si ya existe
        existing = Category.search([('complete_name', '=', complete_name)], limit=1)
        if existing:
            return existing

        # Dividir en partes y crear jerarquía
        parts = [p.strip() for p in complete_name.split('/')]
        parent = self.env['product.category'].browse()

        for i, part in enumerate(parts):
            # Construir el complete_name hasta este punto
            partial_name = ' / '.join(parts[:i+1])

            # Buscar si existe
            category = Category.search([('complete_name', '=', partial_name)], limit=1)

            if not category:
                # Buscar por nombre + padre
                category = Category.search([
                    ('name', '=', part),
                    ('parent_id', '=', parent.id if parent else False)
                ], limit=1)

            if not category:
                # Crear la categoría
                category = Category.create({
                    'name': part,
                    'parent_id': parent.id if parent else False
                })
                _logger.info(f'[MIGRACIÓN] Categoría creada: {category.complete_name}')

            parent = category

        return parent

    def _get_default_uom(self):
        """Obtiene el UOM por defecto (Unidades/Units)."""
        Uom = self.env['uom.uom'].sudo()
        # Buscar por varios nombres comunes
        default_uom = Uom.search([
            ('name', 'in', ['Units', 'Unidades', 'Unit(s)', 'Unidad(es)'])
        ], limit=1)
        if not default_uom:
            # Buscar cualquier UOM de la categoría Unit
            default_uom = Uom.search([
                ('category_id.name', 'in', ['Unit', 'Unidad'])
            ], limit=1)
        if not default_uom:
            # Último recurso: cualquier UOM
            default_uom = Uom.search([], limit=1)
        return default_uom
