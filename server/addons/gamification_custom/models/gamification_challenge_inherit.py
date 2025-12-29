# -*- coding: utf-8 -*-

import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GamificationChallenge(models.Model):
    _inherit = "gamification.challenge"

    department_category_ids = fields.Many2many(
        "gamification.department.category",
        string="Categorías de departamentos",
        help="Limita los usuarios del desafío a los departamentos dentro de las categorías seleccionadas.",
    )

    department_ids = fields.Many2many(
        "hr.department",
        compute="_compute_departments",
        store=False,
        string="Departamentos filtrados",
        help="Departamentos asociados a las categorías seleccionadas.",
    )

    history_count = fields.Integer(
        string="Registros en Historial",
        compute="_compute_history_count",
    )

    @api.depends("department_category_ids")
    def _compute_departments(self):
        assignment = self.env["gamification.department.assignment"]
        all_departments = self.env["hr.department"].search([])

        for challenge in self:
            if challenge.department_category_ids:
                departments = assignment.search([
                    ("category_id", "in", challenge.department_category_ids.ids),
                ]).mapped("department_id")
                challenge.department_ids = departments
            else:
                challenge.department_ids = all_departments

    def _compute_history_count(self):
        ChallengeHistory = self.env["gamification.challenge.history"]
        for challenge in self:
            challenge.history_count = ChallengeHistory.search_count([
                ("original_challenge_id", "=", challenge.id)
            ])

    def action_report_progress(self):
        """Descarga directamente el reporte PDF de progreso del desafio."""
        self.ensure_one()

        # Obtener las metas del desafio
        goals = self.env["gamification.goal"].search([
            ("challenge_id", "=", self.id)
        ], order="user_id, definition_id")

        if not goals:
            raise UserError(_("No se encontraron metas para este desafio."))

        # Buscar el reporte usando env.ref (patron internal_control)
        report = self.env.ref(
            'gamification_custom.action_report_progress',
            raise_if_not_found=False
        )

        if not report:
            raise UserError(_("No se encontro el reporte PDF. Actualice el modulo."))

        # Preparar datos para el contexto del reporte
        report_data = {
            "challenge_name": self.name,
            "user_name": "",
            "date_from": self.start_date,
            "date_to": self.end_date,
            "goal_count": len(goals),
        }

        # Generar PDF usando _render_qweb_pdf (patron internal_control)
        pdf_content, content_type = report._render_qweb_pdf(
            report.id,
            goals.ids,
            data={'report_data': report_data}
        )

        # Crear nombre del archivo
        safe_name = (self.name or 'progreso').replace(' ', '_').replace('/', '_')
        filename = f"Reporte_Progreso_{safe_name}.pdf"

        # Crear attachment
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })

        # Retornar accion de descarga directa
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_archive_goals_to_history(self):
        """Archiva las metas actuales al historial de desafíos."""
        self.ensure_one()

        # Crear el historial del desafío
        ChallengeHistory = self.env["gamification.challenge.history"]
        GoalHistory = self.env["gamification.goal.history"]

        # Verificar si ya existe un historial para este desafío con la misma fecha de fin
        existing_history = ChallengeHistory.search([
            ("original_challenge_id", "=", self.id),
            ("end_date", "=", self.end_date),
        ], limit=1)

        if existing_history:
            # Ya existe, actualizar las metas
            challenge_history = existing_history
        else:
            # Crear nuevo historial de desafío
            challenge_history = ChallengeHistory.create({
                "name": self.name,
                "original_challenge_id": self.id,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "manager_id": self.manager_id.id if self.manager_id else False,
            })

        # Obtener las metas del desafío
        goals = self.env["gamification.goal"].search([
            ("challenge_id", "=", self.id)
        ])

        count = 0
        for goal in goals:
            # Verificar si ya existe en historial
            existing_goal = GoalHistory.search([
                ("original_goal_id", "=", goal.id),
                ("challenge_history_id", "=", challenge_history.id),
            ], limit=1)

            if not existing_goal:
                GoalHistory.create_from_goal(goal, challenge_history)
                count += 1

        # Retornar acción para abrir el historial directamente
        return {
            "type": "ir.actions.act_window",
            "name": _("Historial - %s") % self.name,
            "res_model": "gamification.challenge.history",
            "view_mode": "form",
            "res_id": challenge_history.id,
            "target": "current",
        }

    def action_view_history(self):
        """Ver el historial archivado de este desafío."""
        self.ensure_one()

        histories = self.env["gamification.challenge.history"].search([
            ("original_challenge_id", "=", self.id)
        ])

        if len(histories) == 1:
            # Si solo hay un historial, abrir directamente
            return {
                "type": "ir.actions.act_window",
                "name": _("Historial - %s") % self.name,
                "res_model": "gamification.challenge.history",
                "view_mode": "form",
                "res_id": histories.id,
                "target": "current",
            }
        else:
            # Si hay varios o ninguno, mostrar lista
            return {
                "type": "ir.actions.act_window",
                "name": _("Historial de Desafíos - %s") % self.name,
                "res_model": "gamification.challenge.history",
                "view_mode": "tree,form",
                "domain": [("original_challenge_id", "=", self.id)],
                "context": {"default_original_challenge_id": self.id},
            }
