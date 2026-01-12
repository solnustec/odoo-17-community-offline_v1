# -*- coding: utf-8 -*-
from odoo import models, fields, api

# Cache para configuración de sincronización de productos
_product_sync_config_cache = {}

# Campos que activan sincronización cuando cambian en product.template
_PRODUCT_SYNC_TRIGGER_FIELDS = frozenset({
    'name', 'default_code', 'barcode', 'list_price', 'standard_price',
    'type', 'detailed_type', 'available_in_pos', 'sale_ok', 'purchase_ok',
    'active', 'categ_id', 'uom_id', 'uom_po_id', 'description',
    'description_sale', 'weight', 'volume', 'pos_categ_ids', 'taxes_id',
    'image_128', 'image_1920', 'to_weight',
})


class ProductProduct(models.Model):
    _inherit = 'product.product'

    cloud_sync_id = fields.Integer(string='ID en Cloud', readonly=True, copy=False)
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False)
    last_sync_date = fields.Datetime(string='Última Sincronización', readonly=True, copy=False)

    def mark_as_synced(self, cloud_id=None):
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id
        self.write(vals)

    @api.model
    def find_or_create_from_sync(self, data):
        product = None
        if data.get('cloud_sync_id'):
            product = self.search([('cloud_sync_id', '=', data['cloud_sync_id'])], limit=1)
            if product:
                return product
        if data.get('barcode'):
            product = self.search([('barcode', '=', data['barcode'])], limit=1)
            if product:
                return product
        if data.get('default_code'):
            product = self.search([('default_code', '=', data['default_code'])], limit=1)
            if product:
                return product
        if data.get('id_database_old'):
            domain = [('id_database_old', '=', str(data['id_database_old']))]
            if data.get('name'):
                domain.append(('name', '=', data['name']))
            elif data.get('barcode'):
                domain.append(('barcode', '=', data['barcode']))
            product = self.search(domain, limit=1)
            if product:
                return product
        return None


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    cloud_sync_id = fields.Integer(string='ID en Cloud', readonly=True, copy=False)
    id_database_old = fields.Char(string='ID Base de Datos Origen', copy=False)
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False)
    last_sync_date = fields.Datetime(string='Última Sincronización', readonly=True, copy=False)
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
        template = super().create(vals)
        if skip_sync:
            return template
        sync_config = self._get_active_sync_config()
        if sync_config:
            template._add_to_sync_queue(sync_config.warehouse_id.id)
        return template

    def write(self, vals):
        if not (_PRODUCT_SYNC_TRIGGER_FIELDS & set(vals.keys())):
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
        for template in self:
            if template.sync_state in ('local', 'synced'):
                template._add_to_sync_queue(sync_config.warehouse_id.id, operation='write')
        return result

    @api.model
    def _get_active_sync_config(self):
        global _product_sync_config_cache
        cache_key = f"{self.env.cr.dbname}_product_sync"
        import time
        now = time.time()
        if cache_key in _product_sync_config_cache:
            cached_time, cached_id = _product_sync_config_cache[cache_key]
            if now - cached_time < 60:
                if cached_id:
                    return self.env['pos.sync.config'].browse(cached_id)
                return None
        sync_config = self.env['pos.sync.config'].sudo().search([
            ('sync_products', '=', True),
            ('active', '=', True),
            ('operation_mode', '!=', 'offline'),
        ], limit=1)
        _product_sync_config_cache[cache_key] = (now, sync_config.id if sync_config else None)
        return sync_config

    def _add_to_sync_queue(self, warehouse_id, operation='create'):
        self.ensure_one()
        SyncQueue = self.env['pos.sync.queue'].sudo()
        SyncManager = self.env['pos.sync.manager'].sudo()
        data = SyncManager.serialize_product_template(self)
        queue_record = SyncQueue.add_to_queue(
            model_name='product.template',
            record_id=self.id,
            operation=operation,
            data=data,
            priority='1',
            warehouse_id=warehouse_id,
            record_ref=f'{self.name} [{self.default_code or "Sin ref"}]'
        )
        if queue_record:
            self.with_context(skip_sync_queue=True).write({'sync_state': 'pending'})
        return queue_record

    def mark_as_synced(self, cloud_id=None):
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id
        self.with_context(skip_sync_queue=True).write(vals)


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    cloud_sync_id = fields.Integer(string='ID en Cloud', readonly=True, copy=False)
    id_database_old = fields.Char(string='ID Base de Datos Origen', copy=False)
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False)
    last_sync_date = fields.Datetime(string='Última Sincronización', readonly=True, copy=False)

    def mark_as_synced(self, cloud_id=None):
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id
        self.write(vals)

    @api.model
    def find_or_create_from_sync(self, data):
        pricelist = None
        if data.get('cloud_sync_id'):
            pricelist = self.search([('cloud_sync_id', '=', data['cloud_sync_id'])], limit=1)
            if pricelist:
                return pricelist
        if data.get('id_database_old'):
            domain = [('id_database_old', '=', str(data['id_database_old']))]
            if data.get('name'):
                domain.append(('name', '=', data['name']))
            pricelist = self.search(domain, limit=1)
            if pricelist:
                return pricelist
        if data.get('name'):
            pricelist = self.search([('name', '=', data['name'])], limit=1)
            if pricelist:
                return pricelist
        return None


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    cloud_sync_id = fields.Integer(string='ID en Cloud', readonly=True, copy=False)
    id_database_old = fields.Char(string='ID Base de Datos Origen', copy=False)


class ProductCategory(models.Model):
    _inherit = 'product.category'

    cloud_sync_id = fields.Integer(string='ID en Cloud', readonly=True, copy=False)
    id_database_old = fields.Char(string='ID Base de Datos Origen', copy=False)

    @api.model
    def find_or_create_by_name(self, complete_name):
        if not complete_name:
            return self.browse()
        category = self.search([('complete_name', '=', complete_name)], limit=1)
        if category:
            return category
        parts = [p.strip() for p in complete_name.split('/')]
        parent = self.browse()
        for part in parts:
            category = self.search([
                ('name', '=', part),
                ('parent_id', '=', parent.id if parent else False)
            ], limit=1)
            if not category:
                category = self.create({
                    'name': part,
                    'parent_id': parent.id if parent else False
                })
            parent = category
        return category
