# -*- coding: utf-8 -*-
from odoo import models, fields, api

_sync_config_cache = {}
_SYNC_TRIGGER_FIELDS = frozenset({
    'name', 'email', 'phone', 'mobile', 'vat', 'street', 'street2',
    'city', 'state_id', 'country_id', 'zip', 'property_product_pricelist',
    'barcode', 'comment', 'active', 'ref', 'website', 'function',
})


class ResPartner(models.Model):
    _inherit = 'res.partner'

    cloud_sync_id = fields.Integer(string='ID en Cloud', readonly=True, copy=False)
    id_database_old = fields.Char(string='ID Base de Datos Origen', copy=False)
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False)
    sync_queue_id = fields.Many2one('pos.sync.queue', string='Registro en Cola', readonly=True, copy=False)
    last_sync_date = fields.Datetime(string='Última Sincronización', readonly=True, copy=False)
    offline_created = fields.Boolean(string='Creado Offline', default=False, copy=False)
    sync_source = fields.Selection([
        ('local', 'Local'),
        ('cloud', 'Nube'),
    ], string='Origen de Sincronización', default='local', copy=False)

    @api.model
    def create(self, vals):
        skip_sync = (
            vals.pop('skip_sync_queue', False) or
            self.env.context.get('skip_sync_queue', False) or
            self.env.context.get('install_mode', False) or
            self.env.context.get('module', False)
        )
        partner = super().create(vals)
        if skip_sync:
            return partner
        sync_config = self._get_active_sync_config()
        if sync_config:
            partner._add_to_sync_queue(sync_config.warehouse_id.id)
        return partner

    @api.model
    def _get_active_sync_config(self):
        global _sync_config_cache
        cache_key = f"{self.env.cr.dbname}_partner_sync"
        import time
        now = time.time()
        if cache_key in _sync_config_cache:
            cached_time, cached_id = _sync_config_cache[cache_key]
            if now - cached_time < 60:
                if cached_id:
                    return self.env['pos.sync.config'].browse(cached_id)
                return None
        sync_config = self.env['pos.sync.config'].sudo().search([
            ('sync_partners', '=', True),
            ('active', '=', True),
            ('operation_mode', '!=', 'offline'),
        ], limit=1)
        _sync_config_cache[cache_key] = (now, sync_config.id if sync_config else None)
        return sync_config

    def write(self, vals):
        if not (_SYNC_TRIGGER_FIELDS & set(vals.keys())):
            return super().write(vals)
        skip_sync = (
            vals.pop('skip_sync_queue', False) or
            self.env.context.get('skip_sync_queue', False) or
            self.env.context.get('install_mode', False) or
            self.env.context.get('module', False)
        )
        result = super().write(vals)
        if skip_sync:
            return result
        sync_config = self._get_active_sync_config()
        if not sync_config:
            return result
        for partner in self:
            if partner.sync_state in ('local', 'synced'):
                partner._add_to_sync_queue(sync_config.warehouse_id.id, operation='write')
        return result

    def _add_to_sync_queue(self, warehouse_id, operation='create'):
        self.ensure_one()
        SyncQueue = self.env['pos.sync.queue'].sudo()
        SyncManager = self.env['pos.sync.manager'].sudo()
        data = SyncManager.serialize_partner(self)
        queue_record = SyncQueue.add_to_queue(
            model_name='res.partner',
            record_id=self.id,
            operation=operation,
            data=data,
            warehouse_id=warehouse_id,
            priority='1',
        )
        self.write({
            'sync_state': 'pending',
            'sync_queue_id': queue_record.id,
            'offline_created': True,
        })

    def mark_as_synced(self, cloud_id=None):
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
            'sync_source': 'local',
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id
        self.with_context(skip_sync_queue=True).write(vals)

    def mark_from_cloud(self, cloud_id=None):
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
            'sync_source': 'cloud',
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id
        self.with_context(skip_sync_queue=True).write(vals)

    @api.model
    def get_pending_sync_partners(self, warehouse_id=None, limit=100):
        domain = [('sync_state', '=', 'pending')]
        return self.search(domain, limit=limit, order='write_date asc')

    def action_force_sync(self):
        sync_configs = self.env['pos.sync.config'].sudo().search([
            ('sync_partners', '=', True),
            ('active', '=', True),
        ], limit=1)
        if sync_configs:
            for partner in self:
                partner._add_to_sync_queue(sync_configs.warehouse_id.id, operation='write')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sincronización Programada',
                'message': f'{len(self)} clientes agregados a la cola de sincronización.',
                'type': 'info',
                'sticky': False,
            }
        }

    @api.model
    def find_or_create_from_sync(self, data):
        partner = None
        if data.get('vat'):
            partner = self.search([('vat', '=', data['vat'])], limit=1)
            if partner:
                return partner
        if data.get('cloud_sync_id'):
            partner = self.search([('cloud_sync_id', '=', data['cloud_sync_id'])], limit=1)
            if partner:
                return partner
        if data.get('id_database_old'):
            domain = [('id_database_old', '=', str(data['id_database_old']))]
            if data.get('name'):
                domain.append(('name', '=', data['name']))
            elif data.get('email'):
                domain.append(('email', '=', data['email']))
            partner = self.search(domain, limit=1)
            if partner:
                return partner
        if data.get('email') and data.get('name'):
            partner = self.search([
                ('email', '=', data['email']),
                ('name', '=', data['name'])
            ], limit=1)
            if partner:
                return partner
        if data.get('barcode'):
            partner = self.search([('barcode', '=', data['barcode'])], limit=1)
            if partner:
                return partner
        return None

    @api.model
    def create_or_update_from_sync(self, data, cloud_id=None):
        Partner = self.sudo()
        existing = Partner.find_or_create_from_sync(data)
        vals = self._prepare_partner_vals_from_sync(data)
        if existing:
            if existing.sync_source == 'local' and existing.sync_state == 'pending':
                return existing
            existing.with_context(skip_sync_queue=True).write(vals)
            existing.mark_from_cloud(cloud_id)
            return existing
        else:
            vals['type'] = 'contact'
            partner = Partner.with_context(skip_sync_queue=True).create(vals)
            partner.mark_from_cloud(cloud_id)
            return partner

    def _prepare_partner_vals_from_sync(self, data):
        allowed_fields = [
            'name', 'email', 'phone', 'mobile', 'vat', 'street', 'street2',
            'city', 'zip', 'comment', 'website', 'function', 'barcode',
            'id_database_old',
        ]
        vals = {}
        for field in allowed_fields:
            if field in data and data[field] is not None:
                vals[field] = data[field]
        if data.get('country_id'):
            if isinstance(data['country_id'], int):
                vals['country_id'] = data['country_id']
            elif isinstance(data['country_id'], dict) and data['country_id'].get('id'):
                vals['country_id'] = data['country_id']['id']
        if data.get('state_id'):
            if isinstance(data['state_id'], int):
                vals['state_id'] = data['state_id']
            elif isinstance(data['state_id'], dict) and data['state_id'].get('id'):
                vals['state_id'] = data['state_id']['id']
        if data.get('company_id'):
            if isinstance(data['company_id'], int):
                vals['company_id'] = data['company_id']
            elif isinstance(data['company_id'], dict) and data['company_id'].get('id'):
                vals['company_id'] = data['company_id']['id']
        return vals

    @api.model
    def get_modified_since(self, last_sync_date=None, limit=1000):
        domain = [('type', '=', 'contact')]
        if last_sync_date:
            domain.append(('write_date', '>', last_sync_date))
        return self.search(domain, limit=limit, order='write_date asc')

    def action_reset_sync_state(self):
        self.with_context(skip_sync_queue=True).write({
            'sync_state': 'local',
            'sync_queue_id': False,
            'cloud_sync_id': False,
            'last_sync_date': False,
            'sync_source': 'local',
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Estado Reseteado',
                'message': f'Se reseteó el estado de sincronización de {len(self)} partners.',
                'type': 'info',
                'sticky': False,
            }
        }
