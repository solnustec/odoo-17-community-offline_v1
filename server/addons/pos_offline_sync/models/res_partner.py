# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api
from odoo.tools import config

_logger = logging.getLogger(__name__)

# Cache para configuración de sincronización (evita queries repetidas)
_sync_config_cache = {}
_SYNC_TRIGGER_FIELDS = frozenset({
    'name', 'email', 'phone', 'mobile', 'vat', 'street', 'street2',
    'city', 'state_id', 'country_id', 'zip', 'property_product_pricelist',
    'barcode', 'comment', 'active', 'ref', 'website', 'function',
})


class ResPartner(models.Model):
    """
    Extensión del modelo res.partner para sincronización offline.
    """
    _inherit = 'res.partner'

    # Campos de Sincronización - OPTIMIZADO: con índices para consultas rápidas
    cloud_sync_id = fields.Integer(
        string='ID en Cloud',
        readonly=True,
        copy=False,
        index=True,  # ÍNDICE para búsquedas por cloud_sync_id
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
        help='Indica si el cliente fue creado en modo offline'
    )

    # Campo para tracking de origen de sincronización (bidireccional)
    sync_source = fields.Selection([
        ('local', 'Local'),
        ('cloud', 'Nube'),
    ], string='Origen de Sincronización', default='local', copy=False,
        help='Indica de dónde proviene el último cambio')

    @api.model
    def create(self, vals):
        """
        Override para agregar cliente a cola de sincronización si aplica.
        OPTIMIZADO: Verificaciones tempranas para evitar trabajo innecesario.
        """
        # Verificar si debemos omitir la sincronización (viene del cloud o instalación)
        skip_sync = (
            vals.pop('skip_sync_queue', False) or
            self.env.context.get('skip_sync_queue', False) or
            self.env.context.get('install_mode', False) or
            self.env.context.get('module', False)  # Durante instalación de módulo
        )

        partner = super().create(vals)

        if skip_sync:
            return partner

        # Verificar si hay configuración de sincronización activa (con cache)
        sync_config = self._get_active_sync_config()

        if sync_config:
            partner._add_to_sync_queue(sync_config.warehouse_id.id)
            _logger.debug(f'Partner {partner.id} agregado a cola de sincronización')

        return partner

    @api.model
    def _get_active_sync_config(self):
        """
        Obtiene configuración de sincronización activa con cache.
        OPTIMIZADO: Evita queries repetidas.
        """
        global _sync_config_cache
        cache_key = f"{self.env.cr.dbname}_partner_sync"

        # Verificar cache (válido por 60 segundos)
        import time
        now = time.time()
        if cache_key in _sync_config_cache:
            cached_time, cached_id = _sync_config_cache[cache_key]
            if now - cached_time < 60:  # Cache válido por 60 segundos
                if cached_id:
                    return self.env['pos.sync.config'].browse(cached_id)
                return None

        # Buscar configuración activa
        sync_config = self.env['pos.sync.config'].sudo().search([
            ('sync_partners', '=', True),
            ('active', '=', True),
            ('operation_mode', '!=', 'offline'),
        ], limit=1)

        # Guardar en cache
        _sync_config_cache[cache_key] = (now, sync_config.id if sync_config else None)

        return sync_config

    def write(self, vals):
        """
        Override para actualizar cola de sincronización si el partner cambia.
        OPTIMIZADO: Verificaciones tempranas y cache de configuración.
        """
        # Verificación temprana: si no hay campos relevantes, salir rápido
        if not (_SYNC_TRIGGER_FIELDS & set(vals.keys())):
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

        # Obtener configuración activa (con cache)
        sync_config = self._get_active_sync_config()

        if not sync_config:
            return result

        # Solo procesar partners que necesitan sincronización
        for partner in self:
            if partner.sync_state in ('local', 'synced'):
                partner._add_to_sync_queue(
                    sync_config.warehouse_id.id,
                    operation='write'
                )
                _logger.debug(f'Partner {partner.id} agregado a cola de sincronización')

        return result

    def _add_to_sync_queue(self, warehouse_id, operation='create'):
        """
        Agrega el partner a la cola de sincronización.

        Args:
            warehouse_id: ID del almacén
            operation: Tipo de operación ('create', 'write')
        """
        self.ensure_one()
        SyncQueue = self.env['pos.sync.queue'].sudo()
        SyncManager = self.env['pos.sync.manager'].sudo()

        # Serializar datos del partner
        data = SyncManager.serialize_partner(self)

        # Determinar prioridad
        priority = '1'  # Normal

        # Agregar a cola
        queue_record = SyncQueue.add_to_queue(
            model_name='res.partner',
            record_id=self.id,
            operation=operation,
            data=data,
            warehouse_id=warehouse_id,
            priority=priority,
        )

        # Actualizar estado de sincronización
        self.write({
            'sync_state': 'pending',
            'sync_queue_id': queue_record.id,
            'offline_created': True,
        })

        _logger.info(f'Partner {self.name} agregado a cola de sincronización')

    def mark_as_synced(self, cloud_id=None):
        """
        Marca el partner como sincronizado (desde local hacia cloud).

        Args:
            cloud_id: ID del registro en el cloud (opcional)
        """
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
            'sync_source': 'local',
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id

        self.with_context(skip_sync_queue=True).write(vals)

    def mark_from_cloud(self, cloud_id=None):
        """
        Marca el partner como proveniente del cloud (sincronización bidireccional).

        Args:
            cloud_id: ID del registro en el cloud
        """
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
        """
        Obtiene partners pendientes de sincronización.

        Args:
            warehouse_id: ID del almacén (opcional)
            limit: Número máximo de registros

        Returns:
            res.partner: Partners pendientes
        """
        domain = [('sync_state', '=', 'pending')]
        return self.search(domain, limit=limit, order='write_date asc')

    def action_force_sync(self):
        """
        Fuerza la sincronización de los partners seleccionados.
        """
        sync_configs = self.env['pos.sync.config'].sudo().search([
            ('sync_partners', '=', True),
            ('active', '=', True),
        ], limit=1)

        if sync_configs:
            for partner in self:
                partner._add_to_sync_queue(
                    sync_configs.warehouse_id.id,
                    operation='write'
                )

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
        """
        Busca un partner existente o lo crea desde datos de sincronización.

        Args:
            data: Diccionario con datos del partner

        Returns:
            res.partner: Partner encontrado o None si no existe
        """
        partner = None

        # 1. Buscar por VAT (NIF/CIF/RUC) - identificador único más confiable
        if data.get('vat'):
            partner = self.search([('vat', '=', data['vat'])], limit=1)
            if partner:
                _logger.info(f'Partner encontrado por VAT: {partner.name}')
                return partner

        # 2. Buscar por cloud_sync_id (si ya fue sincronizado previamente)
        if data.get('cloud_sync_id'):
            partner = self.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)
            if partner:
                _logger.info(f'Partner encontrado por cloud_sync_id: {partner.name}')
                return partner

        # 3. Buscar por id_database_old SOLO si también coincide el nombre o email
        # Esto evita falsos positivos cuando IDs de diferentes BDs coinciden
        if data.get('id_database_old'):
            domain = [('id_database_old', '=', str(data['id_database_old']))]
            # Agregar criterio adicional para evitar falsos positivos
            if data.get('name'):
                domain.append(('name', '=', data['name']))
            elif data.get('email'):
                domain.append(('email', '=', data['email']))

            partner = self.search(domain, limit=1)
            if partner:
                _logger.info(f'Partner encontrado por id_database_old + criterio adicional: {partner.name}')
                return partner

        # 4. Buscar por email (si es único y coincide el nombre)
        if data.get('email') and data.get('name'):
            partner = self.search([
                ('email', '=', data['email']),
                ('name', '=', data['name'])
            ], limit=1)
            if partner:
                _logger.info(f'Partner encontrado por email + nombre: {partner.name}')
                return partner

        # 5. Buscar por barcode
        if data.get('barcode'):
            partner = self.search([('barcode', '=', data['barcode'])], limit=1)
            if partner:
                _logger.info(f'Partner encontrado por barcode: {partner.name}')
                return partner

        # No se encontró partner existente
        _logger.info(f'No se encontró partner existente para: {data.get("name")}')
        return None

    @api.model
    def create_or_update_from_sync(self, data, cloud_id=None):
        """
        Crea o actualiza un partner desde datos de sincronización bidireccional.

        Este método se usa cuando se reciben datos del servidor cloud
        para crear o actualizar un partner local.

        Args:
            data: Diccionario con datos del partner
            cloud_id: ID del registro en el cloud

        Returns:
            res.partner: Partner creado o actualizado
        """
        Partner = self.sudo()

        # Buscar partner existente usando find_or_create_from_sync
        existing = Partner.find_or_create_from_sync(data)

        # Preparar valores
        vals = self._prepare_partner_vals_from_sync(data)

        if existing:
            # Verificar si debemos actualizar (evitar sobrescribir cambios locales pendientes)
            if existing.sync_source == 'local' and existing.sync_state == 'pending':
                _logger.info(f'Partner {existing.name} tiene cambios locales pendientes, no se actualiza desde cloud')
                return existing

            existing.with_context(skip_sync_queue=True).write(vals)
            existing.mark_from_cloud(cloud_id)
            _logger.info(f'Partner actualizado desde cloud: {existing.name} (cloud_id: {cloud_id})')
            return existing
        else:
            # Crear nuevo partner
            vals['type'] = 'contact'
            partner = Partner.with_context(skip_sync_queue=True).create(vals)
            partner.mark_from_cloud(cloud_id)
            _logger.info(f'Partner creado desde cloud: {partner.name} (cloud_id: {cloud_id})')
            return partner

    def _prepare_partner_vals_from_sync(self, data):
        """
        Prepara valores para crear/actualizar un partner desde datos de sync.

        Args:
            data: Diccionario con datos del partner

        Returns:
            dict: Valores preparados
        """
        # Campos permitidos para sincronización
        allowed_fields = [
            'name', 'email', 'phone', 'mobile', 'vat', 'street', 'street2',
            'city', 'zip', 'comment', 'website', 'function', 'barcode',
            'id_database_old',
        ]

        vals = {}
        for field in allowed_fields:
            if field in data and data[field] is not None:
                vals[field] = data[field]

        # Manejar campos Many2one
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
        """
        Obtiene partners modificados desde una fecha.

        Args:
            last_sync_date: Fecha de última sincronización
            limit: Número máximo de registros

        Returns:
            res.partner: Partners modificados
        """
        domain = [('type', '=', 'contact')]

        if last_sync_date:
            domain.append(('write_date', '>', last_sync_date))

        return self.search(domain, limit=limit, order='write_date asc')

    def action_reset_sync_state(self):
        """
        Resetea el estado de sincronización de los partners seleccionados.
        """
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
