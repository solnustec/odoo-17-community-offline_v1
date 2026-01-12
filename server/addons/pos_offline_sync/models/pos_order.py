# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# Campos que disparan re-sincronización (definidos como constante para eficiencia)
_ORDER_SYNC_TRIGGER_FIELDS = frozenset({
    'amount_total', 'amount_paid', 'state', 'partner_id',
    'lines', 'payment_ids', 'name'
})


class PosOrder(models.Model):
    """
    Extensión del modelo pos.order para sincronización offline.
    """
    _inherit = 'pos.order'

    # Campos de Sincronización - OPTIMIZADO: con índices para consultas rápidas
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,  # ÍNDICE para búsquedas por cloud_sync_id
        help='ID del registro en el servidor cloud'
    )
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False, index=True)  # ÍNDICE

    sync_queue_id = fields.Many2one(
        'pos.sync.queue',
        string='Registro en Cola',
        readonly=True,
        copy=False
    )
    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True,
        copy=False
    )
    offline_created = fields.Boolean(
        string='Creado Offline',
        default=False,
        copy=False,
        help='Indica si la orden fue creada en modo offline'
    )
    id_database_old = fields.Char(
        string='ID Base Datos Original',
        readonly=True,
        copy=False,
        index=True,
        help='ID del registro en la base de datos original (offline)'
    )

    @api.model
    def create(self, vals):
        """
        Override para manejar is_delivery_order.
        La sincronización se hace en action_pos_order_paid cuando la orden está completa.
        """
        order = super().create(vals)

        # FORZAR: is_delivery_order siempre False DESPUÉS de crear
        # Usamos SQL directo para evitar que pos_sale_order lo sobrescriba
        if order.is_delivery_order:
            self.env.cr.execute(
                "UPDATE pos_order SET is_delivery_order = FALSE WHERE id = %s",
                (order.id,)
            )
            order.invalidate_recordset(['is_delivery_order'])

        return order

    def write(self, vals):
        """
        Override para actualizar cola de sincronización si la orden cambia.
        OPTIMIZADO: Verificaciones tempranas y procesamiento eficiente.
        """
        # FORZAR: is_delivery_order siempre False (no usar órdenes de entrega)
        if vals.get('is_delivery_order'):
            vals['is_delivery_order'] = False

        # Verificación temprana: si no hay campos relevantes, salir rápido
        if not (_ORDER_SYNC_TRIGGER_FIELDS & set(vals.keys())):
            result = super().write(vals)
            # Verificar y corregir is_delivery_order después del write
            self._force_delivery_order_false()
            return result

        # Verificar si debemos omitir la sincronización
        skip_sync = (
            self.env.context.get('skip_sync_queue', False) or
            self.env.context.get('install_mode', False) or
            self.env.context.get('module', False)
        )

        # Guardar el name anterior solo si 'name' está en vals
        old_names = {}
        if 'name' in vals:
            old_names = {order.id: order.name for order in self}

        result = super().write(vals)

        if skip_sync:
            return result

        # Si el name cambió de "/" a un valor real, actualizar la cola de sincronización
        if 'name' in vals and old_names:
            for order in self:
                old_name = old_names.get(order.id)
                new_name = order.name
                # Si el name cambió de "/" o de un valor temporal a un nombre real
                if old_name != new_name and new_name and new_name != '/':
                    # Actualizar el registro en la cola de sincronización si existe
                    if order.sync_queue_id and order.sync_queue_id.state in ['pending', 'error']:
                        order._update_sync_queue_data(new_name)

        # Re-sincronizar solo si hay campos que disparan sincronización (excepto name)
        sync_fields = _ORDER_SYNC_TRIGGER_FIELDS - {'name'}
        if sync_fields & set(vals.keys()):
            for order in self:
                if order.sync_state == 'synced':
                    # Ya estaba sincronizado, necesita actualización
                    warehouse = order._get_order_warehouse()
                    if warehouse:
                        sync_config = self.env['pos.sync.config'].get_config_for_warehouse(
                            warehouse.id
                        )
                        if sync_config and sync_config.sync_orders:
                            order._add_to_sync_queue(warehouse.id, operation='write')

        # Verificar y corregir is_delivery_order después del write
        self._force_delivery_order_false()

        return result

    def _update_sync_queue_data(self, new_name):
        """
        Actualiza los datos de la cola de sincronización con el nombre correcto.

        Args:
            new_name: Nuevo nombre de la orden
        """
        self.ensure_one()
        if not self.sync_queue_id:
            return

        try:
            # Actualizar record_ref
            self.sync_queue_id.write({'record_ref': new_name})

            # Actualizar el JSON data con el nombre correcto
            data = self.sync_queue_id.get_data()
            if data:
                data['name'] = new_name
                self.sync_queue_id.set_data(data)

            _logger.info(f'Cola de sync actualizada con nombre correcto: {new_name}')
        except Exception as e:
            _logger.error(f'Error actualizando cola de sync: {e}')

    def _force_delivery_order_false(self):
        """
        Fuerza is_delivery_order = False usando SQL directo.
        Esto es necesario porque pos_sale_order puede sobrescribir el valor
        durante la cadena de herencia.
        """
        if not self:
            return

        # Obtener IDs de órdenes que tienen is_delivery_order = True
        order_ids = self.ids
        self.env.cr.execute(
            "SELECT id FROM pos_order WHERE id IN %s AND is_delivery_order = TRUE",
            (tuple(order_ids),)
        )
        ids_to_fix = [row[0] for row in self.env.cr.fetchall()]

        if ids_to_fix:
            self.env.cr.execute(
                "UPDATE pos_order SET is_delivery_order = FALSE WHERE id IN %s",
                (tuple(ids_to_fix),)
            )
            # Invalidar cache para esos registros
            self.browse(ids_to_fix).invalidate_recordset(['is_delivery_order'])

    def _get_order_warehouse(self):
        """
        Obtiene el almacén asociado a la orden.

        Returns:
            stock.warehouse: Almacén de la orden
        """
        self.ensure_one()
        if self.session_id and self.session_id.config_id:
            picking_type = self.session_id.config_id.picking_type_id
            if picking_type:
                return picking_type.warehouse_id
        return None

    def _add_to_sync_queue(self, warehouse_id, operation='create'):
        """
        Agrega la orden a la cola de sincronización.

        Args:
            warehouse_id: ID del almacén
            operation: Tipo de operación ('create', 'write')
        """
        self.ensure_one()
        SyncQueue = self.env['pos.sync.queue'].sudo()
        SyncManager = self.env['pos.sync.manager'].sudo()

        # Forzar que todos los cambios pendientes se escriban a la BD
        self.env.flush_all()
        # Refrescar el registro para obtener el name actualizado
        self.invalidate_recordset(['name'])
        # Leer el name directamente de la BD por si acaso
        self.env.cr.execute("SELECT name FROM pos_order WHERE id = %s", (self.id,))
        result = self.env.cr.fetchone()
        db_name = result[0] if result else None

        # Obtener el nombre correcto para record_ref
        # Priorizar el name de la BD, luego el del modelo
        record_ref = db_name if db_name and db_name != '/' else self.name
        if not record_ref or record_ref == '/':
            # Si aún no tiene name, usar config/id
            if self.config_id:
                record_ref = f"{self.config_id.name}/{self.id}"
            else:
                record_ref = f"pos.order#{self.id}"

        # Serializar datos de la orden
        data = SyncManager.serialize_order(self)

        # Asegurar que el name en los datos sea el correcto (el name real, no pos_reference)
        # Usar el name de la BD que obtuvimos antes
        actual_name = db_name if db_name and db_name != '/' else self.name
        if actual_name and actual_name != '/':
            data['name'] = actual_name

        # Determinar prioridad según estado
        priority = '1'  # Normal
        if self.state == 'paid':
            priority = '2'  # Alta para órdenes pagadas
        if self.state == 'invoiced':
            priority = '3'  # Urgente para facturadas

        # Agregar a cola con record_ref correcto
        queue_record = SyncQueue.add_to_queue(
            model_name='pos.order',
            record_id=self.id,
            operation=operation,
            data=data,
            warehouse_id=warehouse_id,
            pos_config_id=self.config_id.id if self.config_id else None,
            session_id=self.session_id.id if self.session_id else None,
            priority=priority,
        )

        # Actualizar record_ref explícitamente si es diferente
        if queue_record.record_ref != record_ref:
            queue_record.write({'record_ref': record_ref})

        # Actualizar estado de sincronización
        self.write({
            'sync_state': 'pending',
            'sync_queue_id': queue_record.id,
            'offline_created': True,
        })

        _logger.info(f'Orden {record_ref} agregada a cola de sincronización')

    def mark_as_synced(self, cloud_id=None):
        """
        Marca la orden como sincronizada.

        Args:
            cloud_id: ID del registro en el cloud (opcional)
        """
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id

        self.write(vals)

    @api.model
    def create_from_ui(self, orders, draft=False):
        """
        Override del método create_from_ui para manejar órdenes offline.

        Este método es llamado cuando se crean órdenes desde la UI del POS.
        Verificamos si debemos omitir la generación de contabilidad.

        IMPORTANTE: Después de que todos los módulos heredados (como pos_custom_check)
        hayan terminado de procesar, re-serializamos la orden para incluir los datos
        de cheque/tarjeta que se guardan DESPUÉS del super().
        """
        # Verificar configuración de sincronización
        created_orders = []

        for order_data in orders:
            # Obtener configuración del almacén
            session_id = order_data.get('data', {}).get('session_id')
            if session_id:
                session = self.env['pos.session'].browse(session_id)
                warehouse = session.config_id.picking_type_id.warehouse_id

                sync_config = self.env['pos.sync.config'].get_config_for_warehouse(
                    warehouse.id
                )

                if sync_config:
                    # Marcar si debemos omitir contabilidad
                    if sync_config.skip_accounting:
                        order_data['data']['skip_accounting'] = True
                    if sync_config.skip_invoice_generation:
                        order_data['data']['skip_invoice'] = True

        # Llamar al método padre
        # NOTA: Aquí se crea la orden, se paga, se factura y se serializa INICIALMENTE
        # Pero los datos de cheque/tarjeta se guardan DESPUÉS por pos_custom_check
        result = super().create_from_ui(orders, draft=draft)

        # RE-SERIALIZAR las órdenes para incluir los datos de cheque/tarjeta
        # que fueron guardados por otros módulos (pos_custom_check) DESPUÉS del super()
        self._resync_orders_with_payment_data(result)

        return result

    def _resync_orders_with_payment_data(self, order_results):
        """
        Re-serializa las órdenes para actualizar los datos de pago en la cola de sincronización.

        Este método se llama DESPUÉS de que todos los módulos heredados hayan terminado
        de guardar los datos de cheque/tarjeta en los pagos.

        Args:
            order_results: Lista de resultados de create_from_ui (diccionarios con 'id')
        """
        if not order_results:
            return

        SyncQueue = self.env['pos.sync.queue'].sudo()
        SyncManager = self.env['pos.sync.manager'].sudo()

        for order_result in order_results:
            order_id = order_result.get('id')
            if not order_id:
                continue

            order = self.browse(order_id)
            if not order.exists():
                continue

            # Verificar si la orden tiene una cola de sincronización pendiente
            queue_record = SyncQueue.search([
                ('model_name', '=', 'pos.order'),
                ('record_id', '=', order.id),
                ('state', 'in', ['pending', 'error']),
            ], limit=1, order='id desc')

            if queue_record:
                # Forzar flush para asegurar que los datos estén en la BD
                self.env.flush_all()

                # Re-serializar la orden con los datos actualizados
                new_data = SyncManager.serialize_order(order)

                # Verificar si hay datos de pago que actualizar
                has_payment_data = False
                for payment in new_data.get('payments', []):
                    if (payment.get('check_number') or payment.get('check_owner') or
                        payment.get('number_voucher') or payment.get('holder_card')):
                        has_payment_data = True
                        break

                if has_payment_data or new_data.get('check_info_json') or new_data.get('card_info_json'):
                    # Actualizar la cola con los nuevos datos
                    import json
                    queue_record.write({
                        'data_json': json.dumps(new_data),
                    })
                    _logger.info(
                        f'Orden {order.name} re-serializada con datos de pago actualizados. '
                        f'check_info_json={bool(new_data.get("check_info_json"))}, '
                        f'payments con datos={has_payment_data}'
                    )

    def _generate_pos_order_invoice(self):
        """
        Override para manejar facturación en modo offline.

        En modo OFFLINE:
        - Crea factura en BORRADOR con clave de acceso
        - NO postea (no envía al SRI)
        - Estado de orden queda en 'paid' (no 'invoiced')

        En modo ONLINE o sin sync_config:
        - Comportamiento normal (postea y envía al SRI)
        """
        warehouse = self._get_order_warehouse()
        if warehouse:
            sync_config = self.env['pos.sync.config'].get_config_for_warehouse(
                warehouse.id
            )

            if sync_config and sync_config.skip_invoice_generation:
                _logger.info(
                    f'Omitiendo generación de factura para orden {self.name} '
                    f'(configuración skip_invoice_generation activa)'
                )
                return None

            # En modo offline: crear factura en BORRADOR con clave de acceso
            # La factura se posteará cuando se sincronice al servidor online
            if sync_config and sync_config.operation_mode == 'offline':
                return self._create_draft_invoice_with_access_key()

        return super()._generate_pos_order_invoice()

    def _create_draft_invoice_with_access_key(self):
        """
        Crea una factura en BORRADOR y genera la clave de acceso sin enviar al SRI.

        Este método es usado en modo OFFLINE para:
        1. Crear la factura con todos los datos
        2. Generar la clave de acceso de 49 dígitos
        3. NO postear la factura (queda en draft)
        4. NO enviar al SRI

        La factura se posteará y enviará al SRI cuando se sincronice al servidor principal.

        Returns:
            account.move: Factura en borrador con clave de acceso
        """
        self.ensure_one()

        if not self.partner_id:
            _logger.warning(f'No se puede crear factura sin cliente para orden {self.name}')
            return None

        if self.account_move:
            _logger.info(f'Orden {self.name} ya tiene factura: {self.account_move.name}')
            return self.account_move

        try:
            # Preparar valores de factura (método estándar de Odoo)
            invoice_vals = self._prepare_invoice_vals()

            # Crear factura SIN postear
            invoice = self.env['account.move'].sudo().with_context(
                skip_sync_queue=True,
            ).create(invoice_vals)

            # Vincular factura a la orden ANTES de generar clave
            # (el name de la factura se necesita para la clave)
            # IMPORTANTE: Estado queda en 'paid' (no 'invoiced')
            # La factura está en borrador, se posteará al sincronizar al online
            self.with_context(skip_sync_queue=True).write({
                'account_move': invoice.id,
                'state': 'paid',  # Estado 'paid' aunque tenga factura borrador
            })

            # Generar clave de acceso manualmente (sin postear)
            # Esto es lo que normalmente hace _post() en l10n_ec_edi
            if hasattr(invoice, '_l10n_ec_set_authorization_number'):
                if invoice.country_code == 'EC':
                    # Verificar que el diario tiene EDI ecuatoriano
                    if any(x.code == 'ecuadorian_edi' for x in invoice.journal_id.edi_format_ids):
                        invoice._l10n_ec_set_authorization_number()
                        _logger.info(
                            f'Clave de acceso generada para factura {invoice.name} en modo offline: '
                            f'{invoice.l10n_ec_authorization_number[:20] if invoice.l10n_ec_authorization_number else "N/A"}...'
                        )

            _logger.info(
                f'Factura {invoice.name} creada en BORRADOR para orden {self.name} '
                f'(modo offline - pendiente de sync para enviar al SRI)'
            )

            return invoice

        except Exception as e:
            _logger.error(f'Error al crear factura en borrador: {e}', exc_info=True)
            return None

    def action_pos_order_paid(self):
        """
        Override para manejar el comportamiento de pago en modo offline.
        IMPORTANTE: Aquí se agrega a cola de sincronización porque la orden ya tiene pagos.
        """
        result = super().action_pos_order_paid()

        # Verificar si debemos omitir la sincronización
        skip_sync = (
            self.env.context.get('skip_sync_queue', False) or
            self.env.context.get('install_mode', False) or
            self.env.context.get('module', False)
        )

        for order in self:
            warehouse = order._get_order_warehouse()
            if warehouse:
                sync_config = self.env['pos.sync.config'].get_config_for_warehouse(
                    warehouse.id
                )

                if sync_config:
                    # Omitir lógica contable si está configurado
                    if sync_config.skip_accounting:
                        _logger.info(
                            f'Omitiendo registros contables para orden {order.name} '
                            f'(modo offline)'
                        )

                    # Agregar a cola de sincronización en TODOS los modos
                    # (offline, hybrid, sync_on_demand) si sync_orders está activo
                    if not skip_sync and sync_config.sync_orders:
                        _logger.info(
                            f'Agregando orden {order.name} a cola de sync '
                            f'(pagos: {len(order.payment_ids)}, estado: {order.state}, '
                            f'modo: {sync_config.operation_mode})'
                        )
                        order._add_to_sync_queue(warehouse.id)

        return result

    @api.model
    def get_pending_sync_orders(self, warehouse_id, limit=100):
        """
        Obtiene órdenes pendientes de sincronización.

        Args:
            warehouse_id: ID del almacén
            limit: Número máximo de registros

        Returns:
            pos.order: Órdenes pendientes
        """
        return self.search([
            ('sync_state', '=', 'pending'),
            ('session_id.config_id.picking_type_id.warehouse_id', '=', warehouse_id),
        ], limit=limit, order='date_order asc')

    def action_force_sync(self):
        """
        Fuerza la sincronización de las órdenes seleccionadas.
        """
        for order in self:
            warehouse = order._get_order_warehouse()
            if warehouse:
                order._add_to_sync_queue(warehouse.id, operation='write')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sincronización Programada',
                'message': f'{len(self)} órdenes agregadas a la cola de sincronización.',
                'type': 'info',
                'sticky': False,
            }
        }
