# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class LoyaltyProgram(models.Model):
    """
    Extensión del modelo loyalty.program para sincronización offline.
    """
    _inherit = 'loyalty.program'

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
        Marca el programa como sincronizado.

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
        Busca un programa de lealtad existente para sincronización.

        Estrategia de búsqueda (en orden de prioridad):
        1. Por cloud_sync_id (para programas ya sincronizados)
        2. Por id_database_old (para migraciones)
        3. Por ID del cloud como id_database_old local (para vincular programas existentes)
        4. Por nombre exacto + tipo de programa (fallback para primera sincronización)

        Args:
            data: Diccionario con datos del programa

        Returns:
            loyalty.program: Programa encontrado o None
        """
        program = None

        # Obtener el ID del cloud
        cloud_id_raw = data.get('cloud_sync_id') or data.get('id')
        cloud_id = None

        _logger.info(
            "find_or_create_from_sync: buscando programa con cloud_id_raw=%s (tipo: %s), nombre=%s",
            cloud_id_raw, type(cloud_id_raw).__name__, data.get('name')
        )

        if cloud_id_raw:
            try:
                cloud_id = int(cloud_id_raw)
            except (ValueError, TypeError):
                _logger.warning("No se pudo convertir cloud_id_raw=%s a entero", cloud_id_raw)

        # 1. Buscar por cloud_sync_id (programas ya sincronizados)
        if cloud_id:
            program = self.search([
                ('cloud_sync_id', '=', cloud_id)
            ], limit=1)

            _logger.info(
                "Búsqueda por cloud_sync_id=%s: %s",
                cloud_id, f"encontrado ID={program.id}, nombre={program.name}" if program else "no encontrado"
            )

            if program:
                return program

        # 2. Buscar por id_database_old (para migraciones)
        if data.get('id_database_old'):
            program = self.search([
                ('id_database_old', '=', str(data['id_database_old']))
            ], limit=1)
            if program:
                _logger.info(
                    "Programa encontrado por id_database_old=%s: %s (ID local: %s)",
                    data['id_database_old'], program.name, program.id
                )
                return program

        # 3. Buscar programas existentes cuyo id_database_old coincida con el cloud_id
        # Esto vincula programas que fueron migrados con el mismo ID
        if cloud_id:
            program = self.search([
                ('id_database_old', '=', str(cloud_id))
            ], limit=1)
            if program:
                _logger.info(
                    "Programa encontrado por id_database_old=%s (coincide con cloud_id): %s (ID local: %s)",
                    cloud_id, program.name, program.id
                )
                return program

        # 4. Buscar por ID local que coincida con el ID del cloud
        # Esto funciona para bases de datos clonadas o que mantienen los mismos IDs
        if cloud_id:
            try:
                program = self.browse(cloud_id)
                if program.exists():
                    # Verificar que no tenga ya un cloud_sync_id diferente
                    if program.cloud_sync_id and program.cloud_sync_id != cloud_id:
                        _logger.info(
                            "Programa ID=%s existe pero tiene cloud_sync_id=%s diferente. Continuando búsqueda.",
                            cloud_id, program.cloud_sync_id
                        )
                    else:
                        _logger.info(
                            "Programa encontrado por ID local=%s (coincide con cloud_id): %s (cloud_sync_id: %s)",
                            cloud_id, program.name, program.cloud_sync_id
                        )
                        return program
            except Exception as e:
                _logger.debug("Error buscando por ID local %s: %s", cloud_id, e)

        # 5. Buscar por nombre exacto y tipo de programa
        # IMPORTANTE: Esto vincula programas existentes que nunca fueron sincronizados
        # Solo funciona si el nombre NO ha sido modificado en el cloud
        if data.get('name') and data.get('program_type'):
            program = self.search([
                ('name', '=', data['name']),
                ('program_type', '=', data['program_type']),
            ], limit=1)
            if program:
                # Si el programa NO tiene cloud_sync_id, es la primera sincronización
                # y debemos vincularlo con el cloud
                if not program.cloud_sync_id:
                    _logger.info(
                        "Programa encontrado por nombre=%s y tipo=%s: ID local %s. "
                        "Primera sincronización, se vinculará con cloud_id=%s",
                        data['name'], data['program_type'], program.id, cloud_id
                    )
                    return program

                # Si el cloud_sync_id coincide, es el programa correcto
                if program.cloud_sync_id == cloud_id:
                    _logger.info(
                        "Programa encontrado por nombre=%s y tipo=%s: ID local %s (cloud_sync_id=%s coincide)",
                        data['name'], data['program_type'], program.id, program.cloud_sync_id
                    )
                    return program

                # Si tiene un cloud_sync_id diferente, es un programa diferente
                # pero con el mismo nombre. Buscamos si hay otro sin cloud_sync_id
                program_without_sync = self.search([
                    ('name', '=', data['name']),
                    ('program_type', '=', data['program_type']),
                    ('cloud_sync_id', '=', False),
                ], limit=1)
                if program_without_sync:
                    _logger.info(
                        "Encontrado programa sin cloud_sync_id con nombre='%s': ID local %s. Se usará este.",
                        data['name'], program_without_sync.id
                    )
                    return program_without_sync

                # Si llegamos aquí, el programa existente ya está vinculado a otro cloud
                # En este caso, actualizamos el existente en lugar de crear duplicado
                _logger.warning(
                    "Programa '%s' tiene cloud_sync_id=%s diferente a %s. "
                    "Se actualizará para evitar duplicados.",
                    data['name'], program.cloud_sync_id, cloud_id
                )
                return program

        _logger.info(
            "No se encontró programa de lealtad existente para cloud_id=%s, nombre=%s",
            cloud_id, data.get('name')
        )
        return None


class LoyaltyRule(models.Model):
    """
    Extensión del modelo loyalty.rule para sincronización offline.
    """
    _inherit = 'loyalty.rule'

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
        """Marca la regla como sincronizada."""
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id
        self.write(vals)


class LoyaltyReward(models.Model):
    """
    Extensión del modelo loyalty.reward para sincronización offline.
    """
    _inherit = 'loyalty.reward'

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
        """Marca la recompensa como sincronizada."""
        vals = {
            'sync_state': 'synced',
            'last_sync_date': fields.Datetime.now(),
        }
        if cloud_id:
            vals['cloud_sync_id'] = cloud_id
        self.write(vals)


class LoyaltyCard(models.Model):
    """
    Extensión del modelo loyalty.card para sincronización offline.
    Representa las tarjetas/puntos de lealtad de los clientes.
    """
    _inherit = 'loyalty.card'

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
        """Marca la tarjeta como sincronizada."""
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
        Busca una tarjeta de lealtad existente.

        Args:
            data: Diccionario con datos de la tarjeta

        Returns:
            loyalty.card: Tarjeta encontrada o None
        """
        card = None

        # 1. Buscar por cloud_sync_id
        if data.get('cloud_sync_id'):
            card = self.search([
                ('cloud_sync_id', '=', data['cloud_sync_id'])
            ], limit=1)
            if card:
                return card

        # 2. Buscar por código
        if data.get('code'):
            card = self.search([('code', '=', data['code'])], limit=1)
            if card:
                return card

        # 3. Buscar por partner_id y program_id
        if data.get('partner_id') and data.get('program_id'):
            # Intentar mapear partner y program por sus cloud_sync_id
            partner = None
            program = None

            if data.get('partner_cloud_id'):
                partner = self.env['res.partner'].search([
                    ('cloud_sync_id', '=', data['partner_cloud_id'])
                ], limit=1)
            if not partner and data.get('partner_id'):
                partner = self.env['res.partner'].browse(data['partner_id'])
                if not partner.exists():
                    partner = None

            if data.get('program_cloud_id'):
                program = self.env['loyalty.program'].search([
                    ('cloud_sync_id', '=', data['program_cloud_id'])
                ], limit=1)
            if not program and data.get('program_id'):
                program = self.env['loyalty.program'].browse(data['program_id'])
                if not program.exists():
                    program = None

            if partner and program:
                card = self.search([
                    ('partner_id', '=', partner.id),
                    ('program_id', '=', program.id)
                ], limit=1)
                if card:
                    return card

        return None
