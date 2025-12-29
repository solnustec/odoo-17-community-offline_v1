# -*- coding: utf-8 -*-

import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GamificationChallengeHistory(models.Model):
    _name = "gamification.challenge.history"
    _description = "Historial de Desafíos"
    _order = "date_archived desc, id desc"
    _rec_name = "name"

    # Información del desafío original
    name = fields.Char(string="Nombre del Desafío", required=True)
    original_challenge_id = fields.Many2one(
        "gamification.challenge",
        string="Desafío Original",
        ondelete="set null",
        help="Referencia al desafío original (puede ser nulo si fue eliminado).",
    )

    # Fechas del desafío
    start_date = fields.Date(string="Fecha de Inicio")
    end_date = fields.Date(string="Fecha de Finalización")
    date_archived = fields.Datetime(
        string="Fecha de Archivado",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    # Responsable
    manager_id = fields.Many2one(
        "res.users",
        string="Responsable",
        ondelete="set null",
    )

    # Estadísticas
    total_users = fields.Integer(
        string="Total Participantes",
        compute="_compute_statistics",
        store=True,
    )
    goals_reached = fields.Integer(
        string="Metas Alcanzadas",
        compute="_compute_statistics",
        store=True,
    )
    goals_failed = fields.Integer(
        string="Metas Fallidas",
        compute="_compute_statistics",
        store=True,
    )
    goals_inprogress = fields.Integer(
        string="Metas En Progreso",
        compute="_compute_statistics",
        store=True,
    )
    total_bonification = fields.Float(
        string="Total Bonificaciones",
        compute="_compute_statistics",
        store=True,
    )
    success_rate = fields.Float(
        string="Tasa de Éxito (%)",
        compute="_compute_statistics",
        store=True,
    )

    # Relación con metas archivadas
    goal_history_ids = fields.One2many(
        "gamification.goal.history",
        "challenge_history_id",
        string="Metas Archivadas",
    )

    goal_count = fields.Integer(
        string="Total de Metas",
        compute="_compute_statistics",
        store=True,
    )

    # Estado del archivado
    state = fields.Selection(
        selection=[
            ("archived", "Archivado"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado",
        default="archived",
    )

    # Notas
    notes = fields.Text(string="Notas")

    user_id = fields.Many2one('res.users', string="Usuario")
    x_user_department_id = fields.Many2one(
        'hr.department',
        string='Departamento',
        compute='_compute_user_department',
        store=True,
        readonly=True,
    )

    @api.depends("goal_history_ids", "goal_history_ids.state", "goal_history_ids.bonification_amount")
    def _compute_statistics(self):
        for record in self:
            goals = record.goal_history_ids
            record.goal_count = len(goals)
            record.total_users = len(goals.mapped("user_id"))
            record.goals_reached = len(goals.filtered(lambda g: g.state == "reached"))
            record.goals_failed = len(goals.filtered(lambda g: g.state == "failed"))
            record.goals_inprogress = len(goals.filtered(lambda g: g.state == "inprogress"))
            record.total_bonification = sum(
                g.bonification_amount or 0 for g in goals if g.state == "reached"
            )
            if record.goal_count > 0:
                record.success_rate = (record.goals_reached / record.goal_count) * 100
            else:
                record.success_rate = 0.0

    def action_view_goals(self):
        """Ver las metas archivadas de este desafío."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Metas - %s") % self.name,
            "res_model": "gamification.goal.history",
            "view_mode": "tree,form,pivot,graph",
            "domain": [("challenge_history_id", "=", self.id)],
            "context": {"default_challenge_history_id": self.id},
        }

    def action_print_report(self):
        """Descarga directamente el reporte PDF del historial del desafio."""
        import logging
        _logger = logging.getLogger(__name__)

        _logger.info("=" * 60)
        _logger.info("DEBUG: Iniciando action_print_report")
        _logger.info("=" * 60)

        self.ensure_one()
        _logger.info(f"DEBUG: self.id = {self.id}, self.name = {self.name}")

        # Preparar los datos para el reporte
        goals = self.goal_history_ids
        _logger.info(f"DEBUG: Total goals en historial: {len(goals)}")

        reached_goals = goals.filtered(lambda g: g.state == "reached")
        failed_goals = goals.filtered(lambda g: g.state == "failed")
        inprogress_goals = goals.filtered(lambda g: g.state in ["inprogress", "draft"])

        _logger.info(f"DEBUG: reached={len(reached_goals)}, failed={len(failed_goals)}, inprogress={len(inprogress_goals)}")

        report_data = {
            "challenge": self,
            "goals": goals,
            "reached_goals": reached_goals,
            "failed_goals": failed_goals,
            "inprogress_goals": inprogress_goals,
            "include_reached": True,
            "include_failed": True,
            "include_inprogress": True,
            "total_goals": len(goals),
            "total_reached": len(reached_goals),
            "total_failed": len(failed_goals),
            "total_inprogress": len(inprogress_goals),
            "total_bonification": sum(g.bonification_amount or 0 for g in reached_goals),
            "success_rate": (len(reached_goals) / len(goals) * 100) if goals else 0,
        }
        _logger.info(f"DEBUG: report_data preparado con {len(report_data)} keys")

        # Buscar o crear el reporte
        report = self._get_or_create_pdf_report()
        _logger.info(f"DEBUG: report obtenido = {report}")

        if not report:
            raise UserError(_(
                "No se pudo crear el reporte PDF. Contacte al administrador."
            ))

        # Generar PDF usando _render_qweb_pdf (patron internal_control)
        _logger.info("DEBUG: Llamando a _render_qweb_pdf...")
        _logger.info(f"DEBUG: report.id = {report.id}, doc_ids = {[self.id]}")

        try:
            pdf_content, content_type = report._render_qweb_pdf(
                report.id,
                [self.id],
                data={'report_data': report_data}
            )
            _logger.info(f"DEBUG: PDF generado exitosamente, tamano = {len(pdf_content)} bytes")
            _logger.info(f"DEBUG: content_type = {content_type}")
        except Exception as e:
            _logger.error(f"DEBUG: Error al generar PDF: {str(e)}")
            _logger.exception("DEBUG: Traceback completo:")
            raise

        # Crear nombre del archivo
        safe_name = (self.name or 'historial').replace(' ', '_').replace('/', '_')
        filename = f"Historial_Desafio_{safe_name}.pdf"
        _logger.info(f"DEBUG: filename = {filename}")

        # Crear attachment
        _logger.info("DEBUG: Creando ir.attachment...")
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        _logger.info(f"DEBUG: Attachment creado con id = {attachment.id}")

        # Retornar accion de descarga directa
        url = f'/web/content/{attachment.id}?download=true'
        _logger.info(f"DEBUG: URL de descarga = {url}")
        _logger.info("DEBUG: Retornando accion de descarga")
        _logger.info("=" * 60)

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }

    def _get_or_create_pdf_report(self):
        """Obtiene o crea el reporte PDF para historial de desafios."""
        import logging
        _logger = logging.getLogger(__name__)

        # Primero intentar con env.ref
        report = self.env.ref(
            'gamification_custom.action_report_challenge_history_pdf',
            raise_if_not_found=False
        )

        if report:
            _logger.info("DEBUG: Reporte encontrado via env.ref")
            return report

        # Si no existe, buscar por report_name
        _logger.info("DEBUG: Buscando reporte por report_name...")
        report = self.env['ir.actions.report'].search([
            ('report_name', '=', 'gamification_custom.report_challenge_history'),
        ], limit=1)

        if report:
            _logger.info("DEBUG: Reporte encontrado via search")
            return report

        # Si no existe, crearlo programaticamente
        _logger.info("DEBUG: Creando reporte programaticamente...")
        try:
            report = self.env['ir.actions.report'].sudo().create({
                'name': 'Reporte de Historial de Desafio',
                'model': 'gamification.challenge.history',
                'report_type': 'qweb-pdf',
                'report_name': 'gamification_custom.report_challenge_history',
                'report_file': 'gamification_custom.report_challenge_history',
                'print_report_name': "'Historial_Desafio'",
                'binding_model_id': self.env['ir.model']._get('gamification.challenge.history').id,
                'binding_type': 'report',
            })
            _logger.info(f"DEBUG: Reporte creado con id = {report.id}")

            # Crear el ir.model.data para que env.ref funcione en el futuro
            self.env['ir.model.data'].sudo().create({
                'name': 'action_report_challenge_history_pdf',
                'module': 'gamification_custom',
                'model': 'ir.actions.report',
                'res_id': report.id,
                'noupdate': False,
            })
            _logger.info("DEBUG: ir.model.data creado")

            return report
        except Exception as e:
            _logger.error(f"DEBUG: Error al crear reporte: {str(e)}")
            _logger.exception("DEBUG: Traceback:")
            return None

    @api.model
    def create_from_challenge(self, challenge):
        """Crea un registro de historial a partir de un desafío existente."""
        if not challenge:
            return self.env["gamification.challenge.history"]

        # Verificar si ya existe un historial para este desafío con la misma fecha de fin
        existing = self.search([
            ("original_challenge_id", "=", challenge.id),
            ("end_date", "=", challenge.end_date),
        ], limit=1)

        if existing:
            return existing

        vals = {
            "name": challenge.name,
            "original_challenge_id": challenge.id,
            "start_date": challenge.start_date,
            "end_date": challenge.end_date,
            "manager_id": challenge.manager_id.id if challenge.manager_id else False,
        }
        return self.create(vals)

    @api.depends('user_id', 'user_id.employee_id', 'user_id.employee_id.department_id')
    def _compute_user_department(self):
        Employee = self.env['hr.employee'].sudo()
        for r in self:
            dept = False
            user = r.user_id
            if user:
                if 'employee_id' in user._fields and user.employee_id:
                    dept = user.employee_id.department_id
                else:
                    emp = Employee.search([('user_id', '=', user.id), ('active', '=', True)], limit=1)
                    dept = emp.department_id if emp else False
            r.x_user_department_id = dept
