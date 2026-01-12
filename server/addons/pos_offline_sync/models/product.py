# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


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
