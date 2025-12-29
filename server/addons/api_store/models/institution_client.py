from odoo import models, api, fields


class InstitutionClient(models.Model):
    _inherit = 'institution.client'

    @api.model
    def get_institution_discount_by_partner(self, partner_id):
        # veriffy if discoutn day

        try:
            week_day = self.get_weekday_selection_value()
            promotions_day = self.env['promotions_by_day.promotions_by_day'].sudo().search([
                ('weekday', '=', week_day),
                ('active', '=', True)
            ], limit=1)
            if promotions_day:
                return {
                    'institution_id': -1,
                    'institution_name': promotions_day.name,
                    'available_amount': 0,
                    'additional_discount_percentage': promotions_day.discount_percent or 0.0,
                }
        except Exception as e:
            print(e)
            pass

        institution_client = self.search([
            ('partner_id', '=', partner_id),
            ('institution_id.type_credit_institution', '=', 'discount')])
        if institution_client:
            institution_client = institution_client.sorted(
                key=lambda r: r.institution_id.additional_discount_percentage or 0.0,
                reverse=True
            )
            return {
                'institution_id': institution_client[0].institution_id.id_institutions,
                'institution_name': institution_client[0].institution_id.name,
                'available_amount': institution_client[0].available_amount,
                'additional_discount_percentage': institution_client[
                    0].institution_id.additional_discount_percentage,
            }

        return None

    def get_weekday_selection_value(self):
        today = fields.Date.context_today(self)
        # Normalizar a Monday = 0 .. Sunday = 6
        return int(today.weekday())
