from odoo import models

class PosSession(models.Model):
    _inherit = "pos.session"

    def _pos_ui_models_to_load(self):
        res = super()._pos_ui_models_to_load()
        res.append("promotions_by_day.promotions_by_day")
        return res

    def _loader_params_promotions_by_day_promotions_by_day(self):
        return {
            "search_params": {
                "domain": [("active", "=", True)],
                "fields": ["name", "weekday", "discount_percent", "active"],
            }
        }

    def _get_pos_ui_promotions_by_day_promotions_by_day(self, params):
        promos = self.env["promotions_by_day.promotions_by_day"].search_read(
            **params["search_params"]
        )
        print("🔍 Promociones enviadas al POS:", promos)
        return promos