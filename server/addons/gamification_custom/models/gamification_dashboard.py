# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, time, date
from markupsafe import escape


class GamificationDashboard(models.Model):
    _name = 'gamification.dashboard'
    _description = 'Gamification Dashboard'
    _rec_name = 'display_name'

    user_id = fields.Many2one('res.users', string='Usuario', required=True, default=lambda self: self.env.user)
    goal_count = fields.Integer('Metas Activas', compute='_compute_stats', store=False)
    badge_count = fields.Integer('Insignias', compute='_compute_stats', store=False)
    avg_progress = fields.Float('Progreso Promedio', compute='_compute_stats', store=False)
    history_count = fields.Integer('Historial', compute='_compute_stats', store=False)

    display_name = fields.Char('Nombre', compute='_compute_display_name', store=False)

    x_banner_html = fields.Html(string='Mensaje de meta lograda en Mis Metas', compute='_compute_completion_banner', sanitize=False, store=False)

    # Campos para el desafío actual
    x_current_challenge_html = fields.Html(
        string='Desafío Actual',
        compute='_compute_current_challenge',
        sanitize=False,
        store=False
    )

    @api.depends('user_id')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"Mis Metas - {record.user_id.name}"

    def _compute_stats(self):
        """Compute gamification statistics for the user"""
        for dashboard in self:
            try:
                # Goals count
                goals = self.env['gamification.goal'].search([
                    ('user_id', '=', dashboard.user_id.id),
                    ('state', 'in', ['draft', 'inprogress'])
                ])
                dashboard.goal_count = len(goals)

                # Badges count
                badges = self.env['gamification.badge.user'].search([
                    ('user_id', '=', dashboard.user_id.id)
                ])
                dashboard.badge_count = len(badges)

                # History count
                history = self.env['gamification.goal.history'].search([
                    ('user_id', '=', dashboard.user_id.id)
                ])
                dashboard.history_count = len(history)

                # Average progress
                if goals:
                    total_progress = sum(goal.completeness for goal in goals)
                    dashboard.avg_progress = round(total_progress / len(goals), 1)
                else:
                    dashboard.avg_progress = 0.0

            except Exception:
                dashboard.goal_count = 0
                dashboard.badge_count = 0
                dashboard.avg_progress = 0.0
                dashboard.history_count = 0

    @api.depends('user_id')
    def _compute_current_challenge(self):
        """Compute HTML showing current active challenges with progress"""
        Goal = self.env['gamification.goal']

        for rec in self:
            user = rec.user_id

            # Get active goals grouped by challenge
            active_goals = Goal.search([
                ('user_id', '=', user.id),
                ('state', 'in', ['draft', 'inprogress']),
                ('challenge_id', '!=', False)
            ], order='challenge_id, definition_id')

            if not active_goals:
                rec.x_current_challenge_html = (
                    "<div class='alert alert-secondary'>"
                    "<i class='fa fa-info-circle'></i> "
                    "No tiene desafíos activos en este momento."
                    "</div>"
                )
                continue

            # Group goals by challenge
            challenges = {}
            for goal in active_goals:
                ch_id = goal.challenge_id.id
                if ch_id not in challenges:
                    challenges[ch_id] = {
                        'challenge': goal.challenge_id,
                        'goals': []
                    }
                challenges[ch_id]['goals'].append(goal)

            html_parts = []

            for ch_data in challenges.values():
                challenge = ch_data['challenge']
                goals = ch_data['goals']

                # Challenge header
                ch_name = escape(challenge.name or 'Sin nombre')
                end_date = challenge.end_date.strftime('%d/%m/%Y') if challenge.end_date else 'Sin fecha'

                # Calculate days remaining
                days_remaining = ''
                if challenge.end_date:
                    delta = challenge.end_date - date.today()
                    if delta.days > 0:
                        days_remaining = f"<span class='badge bg-info'>{delta.days} días restantes</span>"
                    elif delta.days == 0:
                        days_remaining = "<span class='badge bg-warning'>¡Último día!</span>"
                    else:
                        days_remaining = "<span class='badge bg-danger'>Vencido</span>"

                html_parts.append(f"""
                    <div class='card mb-3 border-primary'>
                        <div class='card-header bg-primary text-white d-flex justify-content-between align-items-center'>
                            <strong><i class='fa fa-flag'></i> {ch_name}</strong>
                            <span>Fecha fin: {end_date} {days_remaining}</span>
                        </div>
                        <div class='card-body'>
                            <table class='table table-sm table-hover mb-0'>
                                <thead>
                                    <tr>
                                        <th>Meta</th>
                                        <th class='text-end'>Actual</th>
                                        <th class='text-end'>Objetivo</th>
                                        <th class='text-end'>Faltante</th>
                                        <th style='width: 150px;'>Progreso</th>
                                    </tr>
                                </thead>
                                <tbody>
                """)

                for goal in goals:
                    goal_name = escape(goal.definition_id.name if goal.definition_id else 'Meta')
                    current = goal.current or 0
                    target = goal.target_goal or 0
                    remaining = max(0, target - current)
                    progress = min(goal.completeness or 0, 100)

                    # Color based on progress
                    if progress >= 100:
                        progress_color = 'bg-success'
                        row_class = 'table-success'
                    elif progress >= 75:
                        progress_color = 'bg-info'
                        row_class = ''
                    elif progress >= 50:
                        progress_color = 'bg-warning'
                        row_class = ''
                    else:
                        progress_color = 'bg-danger'
                        row_class = ''

                    html_parts.append(f"""
                        <tr class='{row_class}'>
                            <td><strong>{goal_name}</strong></td>
                            <td class='text-end'>${current:,.2f}</td>
                            <td class='text-end'>${target:,.2f}</td>
                            <td class='text-end text-danger'><strong>${remaining:,.2f}</strong></td>
                            <td>
                                <div class='progress' style='height: 20px;'>
                                    <div class='progress-bar {progress_color}' role='progressbar'
                                         style='width: {progress}%;'
                                         aria-valuenow='{progress}' aria-valuemin='0' aria-valuemax='100'>
                                        {progress:.0f}%
                                    </div>
                                </div>
                            </td>
                        </tr>
                    """)

                html_parts.append("""
                                </tbody>
                            </table>
                        </div>
                    </div>
                """)

            rec.x_current_challenge_html = ''.join(html_parts)

    def action_my_goals(self):
        """Action to open user's goals"""
        self.ensure_one()
        return {
            'name': _('Mis Metas'),
            'res_model': 'gamification.goal',
            'target': 'current',
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban',
            'context': {
                'search_default_my': True,
                'search_default_inprogress': True,
            },
            'domain': [('user_id', '=', self.user_id.id)],
        }

    def action_my_badges(self):
        """Action to open user's badges"""
        self.ensure_one()
        return {
            'name': _('Mis Insignias'),
            'res_model': 'gamification.badge.user',
            'target': 'current',
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban',
            'context': {
                'search_default_my': True,
                'create': 0,
                'edit': 0,
            },
            'domain': [('user_id', '=', self.user_id.id)],
        }

    def action_goals_progress(self):
        """Action to open user's goals with progress bars (list view)"""
        self.ensure_one()
        return {
            'name': _('Progreso de Mis Metas'),
            'res_model': 'gamification.goal',
            'target': 'current',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'context': {
                'search_default_my': True,
                'search_default_inprogress': True,
            },
            'domain': [('user_id', '=', self.user_id.id)],
        }

    def action_list_badges(self):
        """Action to open user's list badges"""
        self.ensure_one()
        return {
            'name': _('Lista de Insignias'),
            'res_model': 'gamification.badge.user',
            'target': 'current',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'context': {
                'search_default_my': True,
                'create': 0,
                'edit': 0,
            },
            'domain': [('user_id', '=', self.user_id.id)],
        }

    def action_my_history(self):
        """Action to open user's challenge history"""
        self.ensure_one()
        return {
            'name': _('Mi Historial de Desafíos'),
            'res_model': 'gamification.goal.history',
            'target': 'current',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'context': {
                'create': 0,
                'edit': 0,
            },
            'domain': [('user_id', '=', self.user_id.id)],
        }

    def action_report_progress(self):
        """Open wizard to download progress report."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Descargar reporte de progreso'),
            'res_model': 'gamification.progress.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_model': self._name,
            },
        }
    
    @api.depends('user_id')
    def _compute_completion_banner(self):
        Goal = self.env['gamification.goal']
        BadgeUser = self.env['gamification.badge.user']

        for rec in self:
            user = rec.user_id

            completed_goal = Goal.search([
                ('user_id', '=', user.id),
                ('state', '=', 'reached'),
                ('x_reached_date', '!=', False),
            ], order='x_reached_date desc, end_date desc, write_date desc, id desc', limit=1)

            if not completed_goal:
                completed_goal = Goal.search([
                    ('user_id', '=', user.id),
                    ('state', '=', 'reached'),
                    ('end_date', '!=', False),
            ], order='end_date desc, write_date desc, id desc', limit=1)

            if not completed_goal:
                completed_goal = Goal.search([
                    ('user_id', '=', user.id),
                    ('state', '=', 'reached'),
                ], order='write_date desc, id desc', limit=1)

            if completed_goal:
                dt = completed_goal.x_reached_date or completed_goal.end_date or completed_goal.write_date
                date_completed_txt = dt.strftime('%d/%m/%Y') if dt else ''

                goal_name = (
                        (completed_goal.definition_id and completed_goal.definition_id.name)
                        or completed_goal.display_name
                        or ''
                )

                challenge_name = (
                        (completed_goal.challenge_id and completed_goal.challenge_id.name)
                        or completed_goal.challenge_id.display_name
                        or ''
                )

                if completed_goal.challenge_id:
                    badge_users = BadgeUser.search([
                        ('user_id', '=', user.id),
                        ('challenge_id', '=', completed_goal.challenge_id.id),
                    ], order='create_date desc', limit=10)
                else:
                    badge_users = self.env['gamification.badge.user']
                badge_names = ', '.join(bu.badge_id.name for bu in badge_users if bu.badge_id)

                bonification = completed_goal.x_bonification
                bonification_txt = str(bonification) if bonification not in (None, False, '') else '—'

                bonification_amount = completed_goal.x_bonification_amount
                bonification_amount_txt = str(bonification_amount) if bonification_amount not in (None, False, '') else '—'

                user_name_e = escape(user.name or '')
                goal_name_e = escape(goal_name or '—')
                challenge_name_e = escape(challenge_name or '—')
                badge_names_e = escape(badge_names)
                bonification_e = escape(bonification_txt)
                bonification_amount_e = escape(bonification_amount_txt)

                rec.x_banner_html = (
                    f"<div class='alert alert-success'>"
                    f"<strong>¡Felicitaciones!</strong> estimado {user_name_e}.</br>"
                    f"Ha cumplido la meta <em>{goal_name_e or '—'}</em> en la fecha: {date_completed_txt}, "
                    f"dentro del desafío <em>{challenge_name_e or '—'}</em>. Por lo que ha ganado lo siguiente: <ul>"             
                    f" <li> Insignias: {badge_names_e or '—'} </li>"
                    f" <li> Bonificación: {bonification_e or '—'} </li>"
                    f" <li> Bonificación monetaria: {bonification_amount_e or '—'} </li>"
                    "</ul>"
                    f"</div>"
                )
            else:
                user_name_e = escape(user.name or '')
                rec.x_banner_html = (
                    f"<div class='alert alert-info'>"
                    f"Estimado {user_name_e}, aún no ha cumplido ninguna meta. "
                    f"¡Le deseamos el mejor de los éxitos!"
                    f"</div>"
                )

    @api.model
    def get_or_create_dashboard(self, user_id=None):
        """Get or create metas dashboard for current user"""
        if not user_id:
            user_id = self.env.user.id
            
        dashboard = self.search([('user_id', '=', user_id)], limit=1)
        if not dashboard:
            dashboard = self.create({'user_id': user_id})
        return dashboard