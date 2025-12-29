# -*- coding: utf-8 -*-

from odoo import api, models


class GamificationChallengeHistoryPdf(models.AbstractModel):
    """PDF report for gamification challenge history."""

    _name = "report.gamification_custom.report_challenge_history"
    _description = "Reporte PDF de historial de desafíos"

    @api.model
    def _get_report_values(self, docids, data=None):
        """Get report values for the QWeb template."""
        # Obtener doc_ids del data si no viene en docids
        if not docids and data:
            docids = data.get('doc_ids', [])

        docs = self.env["gamification.challenge.history"].browse(docids)

        # Obtener report_data si viene en data
        report_data = {}
        if data:
            report_data = data.get('report_data', {})

        # Si no hay report_data, generarlo desde el registro
        if not report_data or not report_data.get("total_goals"):
            report_data = self._prepare_report_data(docs)

        return {
            "doc_ids": docids,
            "doc_model": "gamification.challenge.history",
            "docs": docs,
            "data": report_data,
        }

    def _prepare_report_data(self, docs):
        """Prepare report data from the challenge history records."""
        # Por ahora solo soportamos un registro a la vez
        if len(docs) == 1:
            record = docs[0]
            goals = record.goal_history_ids
            reached_goals = goals.filtered(lambda g: g.state == "reached")
            failed_goals = goals.filtered(lambda g: g.state == "failed")
            inprogress_goals = goals.filtered(lambda g: g.state in ["inprogress", "draft"])

            return {
                "challenge": record,
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
        return {}
