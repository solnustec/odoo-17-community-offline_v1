# -*- coding: utf-8 -*-
from odoo import models, fields, api


class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

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
        program = None
        cloud_id_raw = data.get('cloud_sync_id') or data.get('id')
        cloud_id = None
        if cloud_id_raw:
            try:
                cloud_id = int(cloud_id_raw)
            except (ValueError, TypeError):
                pass
        if cloud_id:
            program = self.search([('cloud_sync_id', '=', cloud_id)], limit=1)
            if program:
                return program
        if data.get('id_database_old'):
            program = self.search([('id_database_old', '=', str(data['id_database_old']))], limit=1)
            if program:
                return program
        if cloud_id:
            program = self.search([('id_database_old', '=', str(cloud_id))], limit=1)
            if program:
                return program
        if cloud_id:
            try:
                program = self.browse(cloud_id)
                if program.exists():
                    if not program.cloud_sync_id or program.cloud_sync_id == cloud_id:
                        return program
            except Exception:
                pass
        if data.get('name') and data.get('program_type'):
            program = self.search([
                ('name', '=', data['name']),
                ('program_type', '=', data['program_type']),
            ], limit=1)
            if program:
                if not program.cloud_sync_id or program.cloud_sync_id == cloud_id:
                    return program
                program_without_sync = self.search([
                    ('name', '=', data['name']),
                    ('program_type', '=', data['program_type']),
                    ('cloud_sync_id', '=', False),
                ], limit=1)
                if program_without_sync:
                    return program_without_sync
                return program
        return None


class LoyaltyRule(models.Model):
    _inherit = 'loyalty.rule'

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


class LoyaltyReward(models.Model):
    _inherit = 'loyalty.reward'

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


class LoyaltyCard(models.Model):
    _inherit = 'loyalty.card'

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
        card = None
        if data.get('cloud_sync_id'):
            card = self.search([('cloud_sync_id', '=', data['cloud_sync_id'])], limit=1)
            if card:
                return card
        if data.get('code'):
            card = self.search([('code', '=', data['code'])], limit=1)
            if card:
                return card
        if data.get('partner_id') and data.get('program_id'):
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
