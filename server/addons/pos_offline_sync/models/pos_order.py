# -*- coding: utf-8 -*-
from odoo import models, fields, api

_ORDER_SYNC_TRIGGER_FIELDS = frozenset({
    'amount_total', 'amount_paid', 'state', 'partner_id',
    'lines', 'payment_ids', 'name'
})


class PosOrder(models.Model):
    _inherit = 'pos.order'

    cloud_sync_id = fields.Integer(string='ID en Cloud', readonly=True, copy=False)
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False)
    sync_queue_id = fields.Many2one('pos.sync.queue', string='Registro en Cola', readonly=True, copy=False)
    last_sync_date = fields.Datetime(string='Última Sincronización', readonly=True, copy=False)
    offline_created = fields.Boolean(string='Creado Offline', default=False, copy=False)
    id_database_old = fields.Char(string='ID Base Datos Original', readonly=True, copy=False)

    @api.model
    def create(self, vals):
        order = super().create(vals)
        if order.is_delivery_order:
            self.env.cr.execute(
                "UPDATE pos_order SET is_delivery_order = FALSE WHERE id = %s",
                (order.id,)
            )
            order.invalidate_recordset(['is_delivery_order'])
        return order

    def write(self, vals):
        if vals.get('is_delivery_order'):
            vals['is_delivery_order'] = False
        if not (_ORDER_SYNC_TRIGGER_FIELDS & set(vals.keys())):
            result = super().write(vals)
            self._force_delivery_order_false()
            return result
        skip_sync = (
            self.env.context.get('skip_sync_queue', False) or
            self.env.context.get('install_mode', False) or
            self.env.context.get('module', False)
        )
        old_names = {}
        if 'name' in vals:
            old_names = {order.id: order.name for order in self}
        result = super().write(vals)
        if skip_sync:
            return result
        if 'name' in vals and old_names:
            for order in self:
                old_name = old_names.get(order.id)
                new_name = order.name
                if old_name != new_name and new_name and new_name != '/':
                    if order.sync_queue_id and order.sync_queue_id.state in ['pending', 'error']:
                        order._update_sync_queue_data(new_name)
        sync_fields = _ORDER_SYNC_TRIGGER_FIELDS - {'name'}
        if sync_fields & set(vals.keys()):
            for order in self:
                if order.sync_state == 'synced':
                    warehouse = order._get_order_warehouse()
                    if warehouse:
                        sync_config = self.env['pos.sync.config'].get_config_for_warehouse(warehouse.id)
                        if sync_config and sync_config.sync_orders:
                            order._add_to_sync_queue(warehouse.id, operation='write')
        self._force_delivery_order_false()
        return result

    def _update_sync_queue_data(self, new_name):
        self.ensure_one()
        if not self.sync_queue_id:
            return
        try:
            self.sync_queue_id.write({'record_ref': new_name})
            data = self.sync_queue_id.get_data()
            if data:
                data['name'] = new_name
                self.sync_queue_id.set_data(data)
        except Exception:
            pass

    def _force_delivery_order_false(self):
        if not self:
            return
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
            self.browse(ids_to_fix).invalidate_recordset(['is_delivery_order'])

    def _get_order_warehouse(self):
        self.ensure_one()
        if self.session_id and self.session_id.config_id:
            picking_type = self.session_id.config_id.picking_type_id
            if picking_type:
                return picking_type.warehouse_id
        return None

    def _add_to_sync_queue(self, warehouse_id, operation='create'):
        self.ensure_one()
        SyncQueue = self.env['pos.sync.queue'].sudo()
        SyncManager = self.env['pos.sync.manager'].sudo()
        self.env.flush_all()
        self.invalidate_recordset(['name'])
        self.env.cr.execute("SELECT name FROM pos_order WHERE id = %s", (self.id,))
        result = self.env.cr.fetchone()
        db_name = result[0] if result else None
        record_ref = db_name if db_name and db_name != '/' else self.name
        if not record_ref or record_ref == '/':
            if self.config_id:
                record_ref = f"{self.config_id.name}/{self.id}"
            else:
                record_ref = f"pos.order#{self.id}"
        data = SyncManager.serialize_order(self)
        actual_name = db_name if db_name and db_name != '/' else self.name
        if actual_name and actual_name != '/':
            data['name'] = actual_name
        priority = '1'
        if self.state == 'paid':
            priority = '2'
        if self.state == 'invoiced':
            priority = '3'
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
        if queue_record.record_ref != record_ref:
            queue_record.write({'record_ref': record_ref})
        self.write({
            'sync_state': 'pending',
            'sync_queue_id': queue_record.id,
            'offline_created': True,
        })

    def mark_as_synced(self, cloud_id=None):
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id
        self.write(vals)

    @api.model
    def create_from_ui(self, orders, draft=False):
        for order_data in orders:
            session_id = order_data.get('data', {}).get('session_id')
            if session_id:
                session = self.env['pos.session'].browse(session_id)
                warehouse = session.config_id.picking_type_id.warehouse_id
                sync_config = self.env['pos.sync.config'].get_config_for_warehouse(warehouse.id)
                if sync_config:
                    if sync_config.skip_accounting:
                        order_data['data']['skip_accounting'] = True
                    if sync_config.skip_invoice_generation:
                        order_data['data']['skip_invoice'] = True
        result = super().create_from_ui(orders, draft=draft)
        self._resync_orders_with_payment_data(result)
        return result

    def _resync_orders_with_payment_data(self, order_results):
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
            queue_record = SyncQueue.search([
                ('model_name', '=', 'pos.order'),
                ('record_id', '=', order.id),
                ('state', 'in', ['pending', 'error']),
            ], limit=1, order='id desc')
            if queue_record:
                self.env.flush_all()
                new_data = SyncManager.serialize_order(order)
                has_payment_data = False
                for payment in new_data.get('payments', []):
                    if (payment.get('check_number') or payment.get('check_owner') or
                        payment.get('number_voucher') or payment.get('holder_card')):
                        has_payment_data = True
                        break
                if has_payment_data or new_data.get('check_info_json') or new_data.get('card_info_json'):
                    import json
                    queue_record.write({'data_json': json.dumps(new_data)})

    def _generate_pos_order_invoice(self):
        warehouse = self._get_order_warehouse()
        if warehouse:
            sync_config = self.env['pos.sync.config'].get_config_for_warehouse(warehouse.id)
            if sync_config and sync_config.skip_invoice_generation:
                return None
            if sync_config and sync_config.operation_mode == 'offline':
                return self._create_draft_invoice_with_access_key()
        return super()._generate_pos_order_invoice()

    def _create_draft_invoice_with_access_key(self):
        self.ensure_one()
        if not self.partner_id:
            return None
        if self.account_move:
            return self.account_move
        try:
            invoice_vals = self._prepare_invoice_vals()
            invoice = self.env['account.move'].sudo().with_context(skip_sync_queue=True).create(invoice_vals)
            self.with_context(skip_sync_queue=True).write({
                'account_move': invoice.id,
                'state': 'paid',
            })
            if hasattr(invoice, '_l10n_ec_set_authorization_number'):
                if invoice.country_code == 'EC':
                    if any(x.code == 'ecuadorian_edi' for x in invoice.journal_id.edi_format_ids):
                        invoice._l10n_ec_set_authorization_number()
            return invoice
        except Exception:
            return None

    def action_pos_order_paid(self):
        result = super().action_pos_order_paid()
        skip_sync = (
            self.env.context.get('skip_sync_queue', False) or
            self.env.context.get('install_mode', False) or
            self.env.context.get('module', False)
        )
        for order in self:
            warehouse = order._get_order_warehouse()
            if warehouse:
                sync_config = self.env['pos.sync.config'].get_config_for_warehouse(warehouse.id)
                if sync_config and not skip_sync and sync_config.sync_orders:
                    order._add_to_sync_queue(warehouse.id)
        return result

    @api.model
    def get_pending_sync_orders(self, warehouse_id, limit=100):
        return self.search([
            ('sync_state', '=', 'pending'),
            ('session_id.config_id.picking_type_id.warehouse_id', '=', warehouse_id),
        ], limit=limit, order='date_order asc')

    def action_force_sync(self):
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
