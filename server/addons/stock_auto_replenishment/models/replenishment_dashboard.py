# -*- coding: utf-8 -*-
"""Dashboard de estadísticas de reabastecimiento automático."""
from datetime import datetime, timedelta
from odoo import models, fields, api


class ReplenishmentDashboard(models.Model):
    """Modelo para mostrar estadísticas del dashboard."""
    _name = 'auto.replenishment.dashboard'
    _description = 'Dashboard de Reabastecimiento Automático'
    _auto = False  # No crear tabla en BD

    name = fields.Char(string='Nombre')

    # Estadísticas de Transferencias
    total_pickings = fields.Integer(string='Total Transferencias')
    pickings_today = fields.Integer(string='Transferencias Hoy')
    pickings_week = fields.Integer(string='Transferencias Semana')
    pickings_month = fields.Integer(string='Transferencias Mes')

    # Por Estado
    pickings_draft = fields.Integer(string='Borrador')
    pickings_waiting = fields.Integer(string='En Espera')
    pickings_ready = fields.Integer(string='Listo')
    pickings_done = fields.Integer(string='Realizado')
    pickings_cancelled = fields.Integer(string='Cancelado')

    # Estadísticas de Cola
    queue_pending = fields.Integer(string='Cola Pendiente')
    queue_done = fields.Integer(string='Cola Procesada')
    queue_failed = fields.Integer(string='Cola Fallida')

    # Orderpoints
    orderpoints_auto = fields.Integer(string='Orderpoints Automáticos')
    orderpoints_need_replenish = fields.Integer(string='Necesitan Reabastecimiento')

    @api.model
    def get_dashboard_data(self):
        """Obtiene los datos para el dashboard."""
        Picking = self.env['stock.picking']
        Queue = self.env['product.replenishment.procurement.queue']
        Orderpoint = self.env['stock.warehouse.orderpoint']

        today = fields.Date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        # Dominio base para transferencias automáticas
        auto_domain = [('is_auto_replenishment', '=', True)]

        # Transferencias por período
        total_pickings = Picking.search_count(auto_domain)
        pickings_today = Picking.search_count(auto_domain + [('create_date', '>=', today)])
        pickings_week = Picking.search_count(auto_domain + [('create_date', '>=', week_start)])
        pickings_month = Picking.search_count(auto_domain + [('create_date', '>=', month_start)])

        # Transferencias por estado
        pickings_draft = Picking.search_count(auto_domain + [('state', '=', 'draft')])
        pickings_waiting = Picking.search_count(auto_domain + [('state', 'in', ['waiting', 'confirmed'])])
        pickings_ready = Picking.search_count(auto_domain + [('state', '=', 'assigned')])
        pickings_done = Picking.search_count(auto_domain + [('state', '=', 'done')])
        pickings_cancelled = Picking.search_count(auto_domain + [('state', '=', 'cancel')])

        # Cola de procurements
        queue_pending = Queue.search_count([('state', '=', 'pending')])
        queue_done = Queue.search_count([('state', '=', 'done')])
        queue_failed = Queue.search_count([('state', '=', 'failed')])

        # Orderpoints
        orderpoints_auto = Orderpoint.search_count([('trigger', '=', 'auto')])
        orderpoints_need_replenish = Orderpoint.search_count([
            ('trigger', '=', 'auto'),
            ('qty_to_order', '>', 0),
        ])

        # Estado de los Crons
        crons_data = self._get_crons_status()

        return {
            'total_pickings': total_pickings,
            'pickings_today': pickings_today,
            'pickings_week': pickings_week,
            'pickings_month': pickings_month,
            'pickings_draft': pickings_draft,
            'pickings_waiting': pickings_waiting,
            'pickings_ready': pickings_ready,
            'pickings_done': pickings_done,
            'pickings_cancelled': pickings_cancelled,
            'queue_pending': queue_pending,
            'queue_done': queue_done,
            'queue_failed': queue_failed,
            'orderpoints_auto': orderpoints_auto,
            'orderpoints_need_replenish': orderpoints_need_replenish,
            'crons': crons_data,
        }

    @api.model
    def _get_crons_status(self):
        """Obtiene el estado de los crons del módulo."""
        Cron = self.env['ir.cron'].sudo()
        crons = []

        # Cron de procesamiento de cola
        cron_process = Cron.search([
            ('model_id.model', '=', 'auto.replenishment.processor'),
            ('code', 'ilike', 'cron_process_queue'),
        ], limit=1)
        if cron_process:
            crons.append({
                'id': cron_process.id,
                'name': 'Procesar Cola',
                'active': cron_process.active,
                'interval': f"{cron_process.interval_number} {cron_process.interval_type}",
                'nextcall': cron_process.nextcall.strftime('%Y-%m-%d %H:%M') if cron_process.nextcall else '-',
                'lastcall': cron_process.lastcall.strftime('%Y-%m-%d %H:%M') if cron_process.lastcall else 'Nunca',
            })

        # Cron de limpieza
        cron_cleanup = Cron.search([
            ('model_id.model', '=', 'auto.replenishment.processor'),
            ('code', 'ilike', 'cron_cleanup_queue'),
        ], limit=1)
        if cron_cleanup:
            crons.append({
                'id': cron_cleanup.id,
                'name': 'Limpieza Cola',
                'active': cron_cleanup.active,
                'interval': f"{cron_cleanup.interval_number} {cron_cleanup.interval_type}",
                'nextcall': cron_cleanup.nextcall.strftime('%Y-%m-%d %H:%M') if cron_cleanup.nextcall else '-',
                'lastcall': cron_cleanup.lastcall.strftime('%Y-%m-%d %H:%M') if cron_cleanup.lastcall else 'Nunca',
            })

        return crons

    @api.model
    def action_open_pickings(self, state=None):
        """Abre las transferencias automáticas filtradas por estado."""
        domain = [('is_auto_replenishment', '=', True)]
        if state:
            if state == 'waiting':
                domain.append(('state', 'in', ['waiting', 'confirmed']))
            else:
                domain.append(('state', '=', state))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Transferencias Automáticas',
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': domain,
        }

    @api.model
    def action_open_queue(self, state=None):
        """Abre la cola filtrada por estado."""
        domain = []
        if state:
            domain.append(('state', '=', state))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Cola de Procurements',
            'res_model': 'product.replenishment.procurement.queue',
            'view_mode': 'tree,form',
            'domain': domain,
        }

    @api.model
    def action_open_orderpoints(self, needs_replenish=False):
        """Abre los orderpoints automáticos."""
        domain = [('trigger', '=', 'auto')]
        if needs_replenish:
            domain.append(('qty_to_order', '>', 0))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Reglas Automáticas',
            'res_model': 'stock.warehouse.orderpoint',
            'view_mode': 'tree,form',
            'domain': domain,
        }
