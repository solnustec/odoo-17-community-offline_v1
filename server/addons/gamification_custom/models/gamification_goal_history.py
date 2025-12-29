# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class GamificationGoalHistory(models.Model):
    _name = "gamification.goal.history"
    _description = "Historial de Metas de Gamificación"
    _order = "date_archived desc, id desc"
    _rec_name = "display_name"

    # Relación con el desafío archivado
    challenge_history_id = fields.Many2one(
        "gamification.challenge.history",
        string="Desafío Archivado",
        index=True,
        ondelete="cascade",
    )

    # Información del usuario
    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        required=True,
        index=True,
        ondelete="restrict",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado",
        index=True,
        ondelete="set null",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Departamento",
        index=True,
        ondelete="set null",
    )
    department_parent_id = fields.Many2one(
        "hr.department",
        string="Zona",
        ondelete="set null",
    )

    # Información del desafío y meta (para compatibilidad)
    challenge_id = fields.Many2one(
        "gamification.challenge",
        string="Desafío Original",
        index=True,
        ondelete="set null",
    )
    challenge_name = fields.Char(
        string="Nombre del Desafío",
        help="Nombre del desafío al momento del archivado.",
    )
    definition_id = fields.Many2one(
        "gamification.goal.definition",
        string="Definición de Meta",
        ondelete="set null",
    )
    definition_name = fields.Char(
        string="Nombre de la Meta",
        help="Nombre de la meta al momento del archivado.",
    )

    # Datos de progreso
    target_goal = fields.Float(string="Meta Objetivo")
    current_value = fields.Float(string="Valor Alcanzado")
    completeness = fields.Float(string="% Completado")
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("inprogress", "En Progreso"),
            ("reached", "Alcanzada"),
            ("failed", "Fallida"),
        ],
        string="Estado Final",
        required=True,
        index=True,
    )

    # Fechas
    start_date = fields.Date(string="Fecha Inicio")
    end_date = fields.Date(string="Fecha Fin")
    reached_date = fields.Date(string="Fecha de Cumplimiento")
    date_archived = fields.Datetime(
        string="Fecha de Archivado",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    # Bonificaciones
    bonification = fields.Text(string="Bonificación")
    bonification_amount = fields.Float(string="Bonificación Monetaria")
    bonification_status = fields.Boolean(string="Bonificación Entregada")

    # Referencia al goal original (puede ser nulo si ya se eliminó)
    original_goal_id = fields.Integer(
        string="ID Goal Original",
        help="ID del registro original de gamification.goal",
    )

    # Campo computado para nombre
    display_name = fields.Char(
        string="Nombre",
        compute="_compute_display_name",
        store=True,
    )

    @api.depends("user_id", "definition_name", "challenge_name")
    def _compute_display_name(self):
        for record in self:
            parts = []
            if record.user_id:
                parts.append(record.user_id.name)
            if record.definition_name:
                parts.append(record.definition_name)
            if record.challenge_name:
                parts.append(f"({record.challenge_name})")
            record.display_name = " - ".join(parts) if parts else f"Historial #{record.id}"

    @api.model
    def create_from_goal(self, goal, challenge_history=None):
        """Crea un registro de historial a partir de un goal existente."""
        if not goal:
            return self.env["gamification.goal.history"]

        # Buscar empleado
        employee = self.env["hr.employee"].sudo().search(
            [("user_id", "=", goal.user_id.id)], limit=1
        )

        vals = {
            "challenge_history_id": challenge_history.id if challenge_history else False,
            "user_id": goal.user_id.id,
            "employee_id": employee.id if employee else False,
            "department_id": goal.x_user_department_id.id if goal.x_user_department_id else False,
            "department_parent_id": goal.x_user_department_parent_id.id if goal.x_user_department_parent_id else False,
            "challenge_id": goal.challenge_id.id if goal.challenge_id else False,
            "challenge_name": goal.challenge_id.name if goal.challenge_id else "",
            "definition_id": goal.definition_id.id if goal.definition_id else False,
            "definition_name": goal.definition_id.name if goal.definition_id else goal.display_name,
            "target_goal": goal.target_goal,
            "current_value": goal.current,
            "completeness": goal.completeness,
            "state": goal.state,
            "start_date": goal.start_date,
            "end_date": goal.end_date,
            "reached_date": goal.x_reached_date,
            "bonification": goal.x_bonification,
            "bonification_amount": goal.x_bonification_amount,
            "bonification_status": goal.x_bonification_status,
            "original_goal_id": goal.id,
        }
        return self.create(vals)

    @api.model
    def archive_challenge_goals(self, challenge):
        """Archiva todas las metas de un desafío."""
        if not challenge:
            return 0

        # Crear o encontrar el historial del desafío
        ChallengeHistory = self.env["gamification.challenge.history"]
        challenge_history = ChallengeHistory.create_from_challenge(challenge)

        goals = self.env["gamification.goal"].search([
            ("challenge_id", "=", challenge.id)
        ])

        count = 0
        for goal in goals:
            # Verificar si ya existe en historial
            existing = self.search([
                ("original_goal_id", "=", goal.id),
                ("challenge_id", "=", challenge.id),
            ], limit=1)

            if not existing:
                self.create_from_goal(goal, challenge_history)
                count += 1

        return count
