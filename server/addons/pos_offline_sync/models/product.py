# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

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
    """
    Extensión del modelo product.product para sincronización offline.
    """
    _inherit = 'product.product'

    # Campos de Sincronización
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,
        help='ID del registro en el servidor cloud'
    )
    # id_database_old = fields.Char(
    #     string='ID Base de Datos Origen',
    #     copy=False,
    #     index=True,
    #     help='ID del registro en la base de datos de origen (para migraciones)'
    # )
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False)

    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True,
        copy=False
    )

    def mark_as_synced(self, cloud_id=None):
        """
        Marca el producto como sincronizado.

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
    def find_or_create_from_sync(self, data):
        """
        Busca un producto existente o lo crea desde datos de sincronización.

        Args:
            data: Diccionario con datos del producto

        Returns:
            product.product: Producto encontrado o None si no existe
        """
        product = None

        # 1. Buscar por cloud_sync_id (si ya fue sincronizado previamente)
        if data.get('cloud_sync_id'):
            product = self.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)
            if product:
                _logger.info(f'Producto encontrado por cloud_sync_id: {product.name}')
                return product

        # 2. Buscar por barcode (identificador único más confiable)
        if data.get('barcode'):
            product = self.search([('barcode', '=', data['barcode'])], limit=1)
            if product:
                _logger.info(f'Producto encontrado por barcode: {product.name}')
                return product

        # 3. Buscar por default_code (referencia interna)
        if data.get('default_code'):
            product = self.search([
                ('default_code', '=', data['default_code'])
            ], limit=1)
            if product:
                _logger.info(f'Producto encontrado por default_code: {product.name}')
                return product

        # 4. Buscar por id_database_old SOLO si también coincide el nombre o barcode
        if data.get('id_database_old'):
            domain = [('id_database_old', '=', str(data['id_database_old']))]
            if data.get('name'):
                domain.append(('name', '=', data['name']))
            elif data.get('barcode'):
                domain.append(('barcode', '=', data['barcode']))

            product = self.search(domain, limit=1)
            if product:
                _logger.info(f'Producto encontrado por id_database_old + criterio adicional: {product.name}')
                return product

        # No se encontró producto existente
        _logger.info(f'No se encontró producto existente para: {data.get("name")}')
        return None


class ProductTemplate(models.Model):
    """
    Extensión del modelo product.template para sincronización offline.
    """
    _inherit = 'product.template'

    # Campos de Sincronización
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,
        help='ID del registro en el servidor cloud'
    )
    id_database_old = fields.Char(
        string='ID Base de Datos Origen',
        copy=False,
        index=True,
        help='ID del registro en la base de datos de origen (para migraciones)'
    )
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False)

    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True,
        copy=False
    )

    # Campo para tracking de origen de sincronización
    sync_source = fields.Selection([
        ('local', 'Local'),
        ('cloud', 'Nube'),
    ], string='Origen de Sincronización', default='local', copy=False,
        help='Indica de dónde proviene el último cambio')

    @api.model
    def create(self, vals):
        """
        Override para agregar producto a cola de sincronización si aplica.
        """
        # Verificar si debemos omitir la sincronización
        skip_sync = (
            vals.pop('skip_sync_queue', False) or
            self.env.context.get('skip_sync_queue', False) or
            self.env.context.get('install_mode', False) or
            self.env.context.get('module', False)
        )

        template = super().create(vals)

        if skip_sync:
            return template

        # Verificar si hay configuración de sincronización activa
        sync_config = self._get_active_sync_config()

        if sync_config:
            template._add_to_sync_queue(sync_config.warehouse_id.id)
            _logger.info(f'ProductTemplate {template.id} ({template.name}) agregado a cola de sincronización')

        return template

    def write(self, vals):
        """
        Override para detectar cambios y agregar a cola de sincronización.
        """
        # Verificación temprana: si no hay campos relevantes, salir rápido
        if not (_PRODUCT_SYNC_TRIGGER_FIELDS & set(vals.keys())):
            return super().write(vals)

        # Verificar si debemos omitir la sincronización
        skip_sync = (
            vals.pop('skip_sync_queue', False) or
            self.env.context.get('skip_sync_queue', False) or
            self.env.context.get('install_mode', False) or
            self.env.context.get('module', False)
        )

        result = super().write(vals)

        if skip_sync:
            return result

        # Obtener configuración activa
        sync_config = self._get_active_sync_config()

        if not sync_config:
            return result

        # Procesar templates que necesitan sincronización
        for template in self:
            if template.sync_state in ('local', 'synced'):
                template._add_to_sync_queue(
                    sync_config.warehouse_id.id,
                    operation='write'
                )
                _logger.info(f'ProductTemplate {template.id} ({template.name}) agregado a cola de sincronización (write)')

        return result

    @api.model
    def _get_active_sync_config(self):
        """
        Obtiene configuración de sincronización activa con cache.
        """
        global _product_sync_config_cache
        cache_key = f"{self.env.cr.dbname}_product_sync"

        # Verificar cache (válido por 60 segundos)
        import time
        now = time.time()
        if cache_key in _product_sync_config_cache:
            cached_time, cached_id = _product_sync_config_cache[cache_key]
            if now - cached_time < 60:
                if cached_id:
                    return self.env['pos.sync.config'].browse(cached_id)
                return None

        # Buscar configuración activa que sincronice productos
        sync_config = self.env['pos.sync.config'].sudo().search([
            ('sync_products', '=', True),
            ('active', '=', True),
            ('operation_mode', '!=', 'offline'),
        ], limit=1)

        # Guardar en cache
        _product_sync_config_cache[cache_key] = (now, sync_config.id if sync_config else None)

        return sync_config

    def _add_to_sync_queue(self, warehouse_id, operation='create'):
        """
        Agrega el product.template a la cola de sincronización.
        """
        self.ensure_one()
        SyncQueue = self.env['pos.sync.queue'].sudo()
        SyncManager = self.env['pos.sync.manager'].sudo()

        # Serializar datos del producto
        data = SyncManager.serialize_product_template(self)

        priority = '1'  # Normal

        # Agregar a cola
        queue_record = SyncQueue.add_to_queue(
            model_name='product.template',
            record_id=self.id,
            operation=operation,
            data=data,
            priority=priority,
            warehouse_id=warehouse_id,
            record_ref=f'{self.name} [{self.default_code or "Sin ref"}]'
        )

        # Actualizar estado de sincronización
        if queue_record:
            self.with_context(skip_sync_queue=True).write({
                'sync_state': 'pending',
            })

        return queue_record

    def mark_as_synced(self, cloud_id=None):
        """
        Marca el producto como sincronizado.
        """
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id

        self.with_context(skip_sync_queue=True).write(vals)


class ProductPricelist(models.Model):
    """
    Extensión del modelo product.pricelist para sincronización offline.
    """
    _inherit = 'product.pricelist'

    # Campos de Sincronización
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,
        help='ID del registro en el servidor cloud'
    )
    id_database_old = fields.Char(
        string='ID Base de Datos Origen',
        copy=False,
        index=True,
        help='ID del registro en la base de datos de origen (para migraciones)'
    )
    sync_state = fields.Selection([
        ('local', 'Solo Local'),
        ('pending', 'Pendiente de Sync'),
        ('synced', 'Sincronizado'),
        ('conflict', 'Conflicto'),
    ], string='Estado de Sincronización', default='local', copy=False)

    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True,
        copy=False
    )

    def mark_as_synced(self, cloud_id=None):
        """
        Marca la lista de precios como sincronizada.

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
    def find_or_create_from_sync(self, data):
        """
        Busca una lista de precios existente.

        Args:
            data: Diccionario con datos de la lista de precios

        Returns:
            product.pricelist: Lista de precios encontrada o None
        """
        pricelist = None

        # 1. Buscar por cloud_sync_id
        if data.get('cloud_sync_id'):
            pricelist = self.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)
            if pricelist:
                return pricelist

        # 2. Buscar por id_database_old + name
        if data.get('id_database_old'):
            domain = [('id_database_old', '=', str(data['id_database_old']))]
            if data.get('name'):
                domain.append(('name', '=', data['name']))
            pricelist = self.search(domain, limit=1)
            if pricelist:
                return pricelist

        # 3. Buscar por nombre exacto
        if data.get('name'):
            pricelist = self.search([('name', '=', data['name'])], limit=1)
            if pricelist:
                return pricelist

        return None


class ProductPricelistItem(models.Model):
    """
    Extensión del modelo product.pricelist.item para sincronización offline.
    """
    _inherit = 'product.pricelist.item'

    # Campos de Sincronización
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,
        help='ID del registro en el servidor cloud'
    )
    id_database_old = fields.Char(
        string='ID Base de Datos Origen',
        copy=False,
        index=True,
        help='ID del registro en la base de datos de origen (para migraciones)'
    )


class ProductCategory(models.Model):
    """
    Extensión del modelo product.category para sincronización offline.
    """
    _inherit = 'product.category'

    # Campos de Sincronización
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,
        help='ID del registro en el servidor cloud'
    )
    id_database_old = fields.Char(
        string='ID Base de Datos Origen',
        copy=False,
        index=True,
        help='ID del registro en la base de datos de origen (para migraciones)'
    )

    @api.model
    def find_or_create_by_name(self, complete_name):
        """
        Busca una categoría por nombre completo o la crea si no existe.

        Args:
            complete_name: Nombre completo de la categoría (ej: "All / Saleable / Food")

        Returns:
            product.category: Categoría encontrada o creada
        """
        if not complete_name:
            return self.browse()

        # Buscar por nombre completo
        category = self.search([('complete_name', '=', complete_name)], limit=1)
        if category:
            return category

        # Si no existe, crear la jerarquía
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
