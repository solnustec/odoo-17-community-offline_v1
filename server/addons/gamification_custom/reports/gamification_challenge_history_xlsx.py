# -*- coding: utf-8 -*-

from odoo import _, models


class GamificationChallengeHistoryXlsx(models.AbstractModel):
    """XLSX report for gamification challenge history."""

    _name = "report.gamification_custom.challenge_history_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte XLSX de historial de desafíos"

    def _get_state_label(self, state):
        """Retorna la etiqueta del estado."""
        states = {
            "draft": _("Borrador"),
            "inprogress": _("En Progreso"),
            "reached": _("Alcanzada"),
            "failed": _("Fallida"),
        }
        return states.get(state, state)

    def _write_challenge_header(self, workbook, sheet, challenge, data, row):
        """Escribe el encabezado con información del desafío."""
        title_format = workbook.add_format({
            "bold": True,
            "font_size": 16,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#1a237e",
            "font_color": "white",
        })
        subtitle_format = workbook.add_format({
            "bold": True,
            "font_size": 11,
            "bg_color": "#e8eaf6",
        })
        info_format = workbook.add_format({
            "font_size": 10,
        })
        number_format = workbook.add_format({
            "font_size": 10,
            "num_format": "#,##0.00",
        })
        percent_format = workbook.add_format({
            "font_size": 10,
            "num_format": "0.00%",
        })

        # Título
        sheet.merge_range(row, 0, row, 7, _("REPORTE DE HISTORIAL DE DESAFÍO"), title_format)
        row += 2

        # Información del desafío
        sheet.write(row, 0, _("Nombre del Desafío:"), subtitle_format)
        sheet.merge_range(row, 1, row, 3, challenge.name, info_format)
        sheet.write(row, 4, _("Responsable:"), subtitle_format)
        sheet.merge_range(row, 5, row, 7, challenge.manager_id.name or "-", info_format)
        row += 1

        sheet.write(row, 0, _("Fecha Inicio:"), subtitle_format)
        sheet.write(row, 1, challenge.start_date.strftime("%d/%m/%Y") if challenge.start_date else "-", info_format)
        sheet.write(row, 2, _("Fecha Fin:"), subtitle_format)
        sheet.write(row, 3, challenge.end_date.strftime("%d/%m/%Y") if challenge.end_date else "-", info_format)
        sheet.write(row, 4, _("Fecha Archivado:"), subtitle_format)
        sheet.merge_range(row, 5, row, 7, challenge.date_archived.strftime("%d/%m/%Y %H:%M") if challenge.date_archived else "-", info_format)
        row += 2

        # Estadísticas
        sheet.merge_range(row, 0, row, 7, _("RESUMEN DE RESULTADOS"), title_format)
        row += 1

        stats = [
            (_("Total Participantes"), data.get("total_goals", 0), None),
            (_("Metas Alcanzadas"), data.get("total_reached", 0), "#28a745"),
            (_("Metas Fallidas"), data.get("total_failed", 0), "#dc3545"),
            (_("Metas En Progreso"), data.get("total_inprogress", 0), "#ffc107"),
        ]

        col = 0
        for label, value, color in stats:
            stat_format = workbook.add_format({
                "bold": True,
                "align": "center",
                "bg_color": color if color else "#f5f5f5",
                "font_color": "white" if color else "black",
                "border": 1,
            })
            sheet.write(row, col, label, stat_format)
            sheet.write(row + 1, col, value, workbook.add_format({"align": "center", "border": 1, "bold": True}))
            col += 2

        row += 3

        # Tasa de éxito y bonificaciones
        sheet.write(row, 0, _("Tasa de Éxito:"), subtitle_format)
        sheet.write(row, 1, data.get("success_rate", 0) / 100, percent_format)
        sheet.write(row, 2, _("Total Bonificaciones:"), subtitle_format)
        sheet.write(row, 3, data.get("total_bonification", 0), number_format)
        row += 2

        return row

    def _write_goals_section(self, workbook, sheet, title, goals, row, color):
        """Escribe una sección de metas."""
        if not goals:
            return row

        section_format = workbook.add_format({
            "bold": True,
            "font_size": 12,
            "bg_color": color,
            "font_color": "white",
            "align": "center",
        })
        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#37474f",
            "font_color": "white",
            "border": 1,
            "align": "center",
        })
        cell_format = workbook.add_format({"border": 1, "align": "left"})
        number_format = workbook.add_format({"border": 1, "num_format": "#,##0.00", "align": "right"})
        percent_format = workbook.add_format({"border": 1, "num_format": "0.00%", "align": "center"})
        date_format = workbook.add_format({"border": 1, "align": "center"})

        # Título de sección
        sheet.merge_range(row, 0, row, 8, title, section_format)
        row += 1

        # Encabezados
        headers = [
            _("Usuario"),
            _("Departamento"),
            _("Zona"),
            _("Meta"),
            _("Objetivo"),
            _("Alcanzado"),
            _("% Completado"),
            _("F. Cumplimiento"),
            _("Bonificación"),
        ]
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        row += 1

        # Datos
        for goal in goals:
            sheet.write(row, 0, goal.user_id.name or "", cell_format)
            sheet.write(row, 1, goal.department_id.name or "", cell_format)
            sheet.write(row, 2, goal.department_parent_id.name or "", cell_format)
            sheet.write(row, 3, goal.definition_name or "", cell_format)
            sheet.write(row, 4, goal.target_goal or 0, number_format)
            sheet.write(row, 5, goal.current_value or 0, number_format)
            sheet.write(row, 6, (goal.completeness or 0) / 100, percent_format)
            sheet.write(row, 7, goal.reached_date.strftime("%d/%m/%Y") if goal.reached_date else "-", date_format)
            sheet.write(row, 8, goal.bonification_amount or 0, number_format)
            row += 1

        # Subtotal de bonificaciones
        total = sum(g.bonification_amount or 0 for g in goals)
        sheet.write(row, 7, _("Subtotal:"), workbook.add_format({"bold": True, "align": "right"}))
        sheet.write(row, 8, total, workbook.add_format({"bold": True, "num_format": "#,##0.00", "border": 1}))
        row += 2

        return row

    def _write_department_section(self, workbook, sheet, goals_by_department, row):
        """Escribe metas agrupadas por departamento."""
        section_format = workbook.add_format({
            "bold": True,
            "font_size": 11,
            "bg_color": "#455a64",
            "font_color": "white",
        })
        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#607d8b",
            "font_color": "white",
            "border": 1,
        })
        cell_format = workbook.add_format({"border": 1})
        number_format = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        percent_format = workbook.add_format({"border": 1, "num_format": "0.00%"})

        for dept_name, goals in sorted(goals_by_department.items()):
            # Encabezado de departamento
            sheet.merge_range(row, 0, row, 8, f"📍 {dept_name} ({len(goals)} participantes)", section_format)
            row += 1

            # Encabezados
            headers = [_("Usuario"), _("Meta"), _("Estado"), _("Objetivo"), _("Alcanzado"), _("% Completado"), _("F. Cumplimiento"), _("Bonificación"), _("Entregada")]
            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_format)
            row += 1

            for goal in goals:
                sheet.write(row, 0, goal.user_id.name or "", cell_format)
                sheet.write(row, 1, goal.definition_name or "", cell_format)
                sheet.write(row, 2, self._get_state_label(goal.state), cell_format)
                sheet.write(row, 3, goal.target_goal or 0, number_format)
                sheet.write(row, 4, goal.current_value or 0, number_format)
                sheet.write(row, 5, (goal.completeness or 0) / 100, percent_format)
                sheet.write(row, 6, goal.reached_date.strftime("%d/%m/%Y") if goal.reached_date else "-", cell_format)
                sheet.write(row, 7, goal.bonification_amount or 0, number_format)
                sheet.write(row, 8, _("Sí") if goal.bonification_status else _("No"), cell_format)
                row += 1

            row += 1

        return row

    def generate_xlsx_report(self, workbook, data, challenge_history):
        """Genera el reporte XLSX."""
        sheet = workbook.add_worksheet(_("Historial de Desafío"))

        # Configurar anchos de columna
        sheet.set_column(0, 0, 25)  # Usuario
        sheet.set_column(1, 1, 20)  # Departamento
        sheet.set_column(2, 2, 15)  # Zona
        sheet.set_column(3, 3, 30)  # Meta
        sheet.set_column(4, 4, 12)  # Objetivo
        sheet.set_column(5, 5, 12)  # Alcanzado
        sheet.set_column(6, 6, 12)  # % Completado
        sheet.set_column(7, 7, 15)  # F. Cumplimiento
        sheet.set_column(8, 8, 12)  # Bonificación

        row = 0

        # Encabezado con información del desafío
        row = self._write_challenge_header(workbook, sheet, challenge_history, data, row)

        # Si está agrupado por departamento
        if data.get("group_by_department") and data.get("goals_by_department"):
            row = self._write_department_section(workbook, sheet, data["goals_by_department"], row)
        else:
            # Secciones por estado
            if data.get("include_reached") and data.get("reached_goals"):
                row = self._write_goals_section(
                    workbook, sheet,
                    _("✓ METAS ALCANZADAS (%s)") % len(data["reached_goals"]),
                    data["reached_goals"], row, "#28a745"
                )

            if data.get("include_failed") and data.get("failed_goals"):
                row = self._write_goals_section(
                    workbook, sheet,
                    _("✗ METAS FALLIDAS (%s)") % len(data["failed_goals"]),
                    data["failed_goals"], row, "#dc3545"
                )

            if data.get("include_inprogress") and data.get("inprogress_goals"):
                row = self._write_goals_section(
                    workbook, sheet,
                    _("⏳ METAS EN PROGRESO (%s)") % len(data["inprogress_goals"]),
                    data["inprogress_goals"], row, "#ffc107"
                )
