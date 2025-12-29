# -*- coding: utf-8 -*-
"""
Utilidades para cargar configuración de POS desde variables de entorno (.env).

Este módulo permite configurar puntos de venta (POS) desde un archivo .env
en lugar de hacerlo manualmente a través de la interfaz de Odoo.

Variables de entorno soportadas:
- POS_OFFLINE_CLOUD_URL: URL del servidor cloud
- POS_OFFLINE_API_KEY: API key para autenticación
- POS_OFFLINE_WAREHOUSE_ID: ID del almacén
- POS_OFFLINE_WAREHOUSE_NAME: Nombre del almacén (alternativa al ID)
- POS_OFFLINE_SYNC_INTERVAL: Intervalo de sincronización en minutos
- POS_OFFLINE_OPERATION_MODE: Modo de operación (offline, hybrid, sync_on_demand)
- POS_OFFLINE_SYNC_ORDERS: Sincronizar órdenes (true/false)
- POS_OFFLINE_SYNC_PARTNERS: Sincronizar clientes (true/false)
- POS_OFFLINE_SYNC_PRODUCTS: Sincronizar productos (true/false)
- POS_OFFLINE_SYNC_STOCK: Sincronizar stock (true/false)
- POS_OFFLINE_SYNC_LOYALTY: Sincronizar programas de lealtad (true/false)
- POS_OFFLINE_SYNC_PRICELISTS: Sincronizar listas de precios (true/false)
- POS_OFFLINE_SYNC_FISCAL_POSITIONS: Sincronizar posiciones fiscales (true/false)
- POS_OFFLINE_POS_CONFIG_IDS: IDs de configuraciones POS separados por coma
- POS_OFFLINE_POS_CONFIG_NAMES: Nombres de configuraciones POS separados por coma
"""
import os
import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class PosConfigEnvLoader(models.AbstractModel):
    """
    Modelo abstracto para cargar configuración de POS desde variables de entorno.
    """
    _name = 'pos.config.env.loader'
    _description = 'Cargador de configuración POS desde .env'

    @api.model
    def _str_to_bool(self, value):
        """Convierte un string a booleano."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'si', 'sí')
        return bool(value)

    @api.model
    def _get_env_value(self, key, default=None):
        """Obtiene un valor de variable de entorno."""
        return os.environ.get(key, default)

    @api.model
    def _get_env_bool(self, key, default=True):
        """Obtiene un valor booleano de variable de entorno."""
        value = self._get_env_value(key)
        if value is None:
            return default
        return self._str_to_bool(value)

    @api.model
    def _get_env_int(self, key, default=None):
        """Obtiene un valor entero de variable de entorno."""
        value = self._get_env_value(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @api.model
    def _get_env_list(self, key, default=None):
        """Obtiene una lista de valores de variable de entorno (separados por coma)."""
        value = self._get_env_value(key)
        if value is None:
            return default or []
        return [v.strip() for v in value.split(',') if v.strip()]

    @api.model
    def load_config_from_env(self):
        """
        Carga o actualiza la configuración de sincronización desde variables de entorno.

        Returns:
            pos.sync.config: Configuración creada o actualizada, o None si no hay config
        """
        cloud_url = self._get_env_value('POS_OFFLINE_CLOUD_URL')
        warehouse_id = self._get_env_int('POS_OFFLINE_WAREHOUSE_ID')
        warehouse_name = self._get_env_value('POS_OFFLINE_WAREHOUSE_NAME')

        # Si no hay URL de cloud ni warehouse, no hay nada que configurar
        if not cloud_url and not warehouse_id and not warehouse_name:
            _logger.info('No se encontraron variables de entorno para POS offline sync')
            return None

        # Buscar almacén
        warehouse = None
        if warehouse_id:
            warehouse = self.env['stock.warehouse'].sudo().browse(warehouse_id)
            if not warehouse.exists():
                _logger.warning(f'Almacén con ID {warehouse_id} no encontrado')
                warehouse = None

        if not warehouse and warehouse_name:
            warehouse = self.env['stock.warehouse'].sudo().search([
                ('name', '=', warehouse_name)
            ], limit=1)
            if not warehouse:
                _logger.warning(f'Almacén con nombre "{warehouse_name}" no encontrado')

        if not warehouse:
            # Usar el primer almacén disponible
            warehouse = self.env['stock.warehouse'].sudo().search([], limit=1)
            if not warehouse:
                _logger.error('No hay almacenes disponibles para configuración POS offline')
                return None
            _logger.info(f'Usando almacén por defecto: {warehouse.name}')

        # Buscar configuración existente
        SyncConfig = self.env['pos.sync.config'].sudo()
        config = SyncConfig.search([
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)

        # Preparar valores
        vals = {
            'warehouse_id': warehouse.id,
            'cloud_url': cloud_url or '',
            'api_key': self._get_env_value('POS_OFFLINE_API_KEY', ''),
            'sync_interval': self._get_env_int('POS_OFFLINE_SYNC_INTERVAL', 5),
            'operation_mode': self._get_env_value('POS_OFFLINE_OPERATION_MODE', 'hybrid'),
            # Opciones de sincronización
            'sync_orders': self._get_env_bool('POS_OFFLINE_SYNC_ORDERS', True),
            'sync_partners': self._get_env_bool('POS_OFFLINE_SYNC_PARTNERS', True),
            'sync_products': self._get_env_bool('POS_OFFLINE_SYNC_PRODUCTS', True),
            'sync_stock': self._get_env_bool('POS_OFFLINE_SYNC_STOCK', True),
            'sync_loyalty': self._get_env_bool('POS_OFFLINE_SYNC_LOYALTY', True),
            'sync_employees': self._get_env_bool('POS_OFFLINE_SYNC_EMPLOYEES', True),
            'sync_payment_methods': self._get_env_bool('POS_OFFLINE_SYNC_PAYMENT_METHODS', True),
            'sync_pricelists': self._get_env_bool('POS_OFFLINE_SYNC_PRICELISTS', True),
            'sync_fiscal_positions': self._get_env_bool('POS_OFFLINE_SYNC_FISCAL_POSITIONS', True),
            'sync_refunds': self._get_env_bool('POS_OFFLINE_SYNC_REFUNDS', True),
            # Opciones contables
            'skip_accounting': self._get_env_bool('POS_OFFLINE_SKIP_ACCOUNTING', True),
            'skip_invoice_generation': self._get_env_bool('POS_OFFLINE_SKIP_INVOICE', True),
            # Configuración avanzada
            'batch_size': self._get_env_int('POS_OFFLINE_BATCH_SIZE', 100),
            'retry_attempts': self._get_env_int('POS_OFFLINE_RETRY_ATTEMPTS', 3),
            'sync_timeout': self._get_env_int('POS_OFFLINE_SYNC_TIMEOUT', 30),
        }

        # Agregar nombre si no existe
        if not config:
            config_name = self._get_env_value('POS_OFFLINE_CONFIG_NAME')
            if not config_name:
                config_name = f'Sync Config - {warehouse.name}'
            vals['name'] = config_name

        # Buscar configuraciones POS
        pos_config_ids = []
        pos_config_id_list = self._get_env_list('POS_OFFLINE_POS_CONFIG_IDS')
        pos_config_name_list = self._get_env_list('POS_OFFLINE_POS_CONFIG_NAMES')

        PosConfig = self.env['pos.config'].sudo()

        # Por IDs
        for pos_id in pos_config_id_list:
            try:
                pos_config = PosConfig.browse(int(pos_id))
                if pos_config.exists():
                    pos_config_ids.append(pos_config.id)
            except (ValueError, TypeError):
                _logger.warning(f'ID de POS inválido: {pos_id}')

        # Por nombres
        for pos_name in pos_config_name_list:
            pos_config = PosConfig.search([('name', '=', pos_name)], limit=1)
            if pos_config:
                if pos_config.id not in pos_config_ids:
                    pos_config_ids.append(pos_config.id)
            else:
                _logger.warning(f'Configuración POS "{pos_name}" no encontrada')

        if pos_config_ids:
            vals['pos_config_ids'] = [(6, 0, pos_config_ids)]

        # Crear o actualizar configuración
        if config:
            config.write(vals)
            _logger.info(f'Configuración de sincronización actualizada desde .env: {config.name}')
        else:
            config = SyncConfig.create(vals)
            _logger.info(f'Configuración de sincronización creada desde .env: {config.name}')

        return config

    @api.model
    def get_env_config_summary(self):
        """
        Retorna un resumen de la configuración actual desde variables de entorno.

        Returns:
            dict: Resumen de configuración
        """
        return {
            'cloud_url': self._get_env_value('POS_OFFLINE_CLOUD_URL', 'No configurado'),
            'api_key': '***' if self._get_env_value('POS_OFFLINE_API_KEY') else 'No configurado',
            'warehouse_id': self._get_env_int('POS_OFFLINE_WAREHOUSE_ID'),
            'warehouse_name': self._get_env_value('POS_OFFLINE_WAREHOUSE_NAME'),
            'sync_interval': self._get_env_int('POS_OFFLINE_SYNC_INTERVAL', 5),
            'operation_mode': self._get_env_value('POS_OFFLINE_OPERATION_MODE', 'hybrid'),
            'sync_options': {
                'orders': self._get_env_bool('POS_OFFLINE_SYNC_ORDERS', True),
                'partners': self._get_env_bool('POS_OFFLINE_SYNC_PARTNERS', True),
                'products': self._get_env_bool('POS_OFFLINE_SYNC_PRODUCTS', True),
                'stock': self._get_env_bool('POS_OFFLINE_SYNC_STOCK', True),
                'loyalty': self._get_env_bool('POS_OFFLINE_SYNC_LOYALTY', True),
                'pricelists': self._get_env_bool('POS_OFFLINE_SYNC_PRICELISTS', True),
                'fiscal_positions': self._get_env_bool('POS_OFFLINE_SYNC_FISCAL_POSITIONS', True),
                'refunds': self._get_env_bool('POS_OFFLINE_SYNC_REFUNDS', True),
            },
            'pos_configs': {
                'ids': self._get_env_list('POS_OFFLINE_POS_CONFIG_IDS'),
                'names': self._get_env_list('POS_OFFLINE_POS_CONFIG_NAMES'),
            },
        }


class PosSyncConfigEnv(models.Model):
    """
    Extensión de pos.sync.config para soportar carga desde .env.
    """
    _inherit = 'pos.sync.config'

    @api.model
    def load_from_env(self):
        """
        Carga configuración desde variables de entorno.

        Returns:
            pos.sync.config: Configuración creada o actualizada
        """
        loader = self.env['pos.config.env.loader'].sudo()
        return loader.load_config_from_env()

    @api.model
    def init_from_env_on_startup(self):
        """
        Inicializa configuración desde .env al iniciar.
        Este método puede ser llamado desde un hook de inicio.
        """
        try:
            config = self.load_from_env()
            if config:
                _logger.info(f'Configuración POS Offline inicializada: {config.name}')
        except Exception as e:
            _logger.error(f'Error inicializando configuración POS desde .env: {e}')
