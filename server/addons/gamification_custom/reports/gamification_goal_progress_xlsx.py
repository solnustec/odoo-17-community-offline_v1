# -*- coding: utf-8 -*-

from odoo import _, models


class GamificationGoalProgressXlsx(models.AbstractModel):
    """XLSX report for gamification goals progress."""

    _name = "report.gamification_custom.goal_progress_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte XLSX de progreso de metas"

    def _write_header(self, sheet, header, formats):
        for col, title in enumerate(header):
            sheet.write(0, col, title, formats["header"])

    def _write_goal_row(self, sheet, row, goal, formats):
        sheet.write(row, 0, goal.user_id.name or "", formats["default"])
        sheet.write(row, 1, goal.definition_id.name or goal.display_name or "", formats["default"])
        sheet.write(row, 2, goal.challenge_id.name or "", formats["default"])
        state_label = dict(goal._fields["state"].selection).get(goal.state, goal.state)
        sheet.write(row, 3, state_label, formats["default"])
        sheet.write_number(row, 4, (goal.completeness or 0.0) / 100.0, formats["percentage"])
        sheet.write(row, 5, goal.x_reached_date and goal.x_reached_date.strftime("%d/%m/%Y") or "", formats["default"])
        sheet.write(row, 6, goal.x_bonification or "", formats["default"])
        sheet.write_number(row, 7, goal.x_bonification_amount or 0.0, formats["money"])

    def generate_xlsx_report(self, workbook, data, goals):
        sheet = workbook.add_worksheet(_("Progreso de metas"))

        formats = {
            "header": workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1}),
            "default": workbook.add_format({"border": 1}),
            "percentage": workbook.add_format({"border": 1, "num_format": "0.00%"}),
            "money": workbook.add_format({"border": 1, "num_format": "#,##0.00"}),
        }

        header = [
            _("Usuario"),
            _("Meta"),
            _("Desafío"),
            _("Estado"),
            _("Avance"),
            _("Fecha de cumplimiento"),
            _("Bonificación"),
            _("Bonificación monetaria"),
        ]

        self._write_header(sheet, header, formats)

        for row, goal in enumerate(goals, start=1):
            self._write_goal_row(sheet, row, goal, formats)