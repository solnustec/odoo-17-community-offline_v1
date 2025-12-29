from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class CustomerUpdateController(http.Controller):

    @http.route(
        "/customer/update", type="http", auth="public", website=True, csrf=False
    )
    def customer_update(self, token=None, **post):
        if not token:
            return request.redirect("/update-thank-you")
        partner = (
            request.env["res.partner"]
            .sudo()
            .search([("update_token", "=", token)], limit=1)
        )
        if not partner:
            return request.redirect("/update-thank-you")
        view_id = request.env.ref(
            "partner_custom_form.customer_update_form_template"
        ).id

        if request.httprequest.method == "POST":
            x_continuous_medication = post.get("x_continuous_medication")
            x_frequency = post.get("x_frequency")
            category_ids_to_add = []
            if x_frequency == "gt10":
                frequency_client = http.request.env["res.partner.category"].search(
                    [("name", "=", "Cliente Fiel")], limit=1
                )
                _logger.info(frequency_client)
                category_ids_to_add.append(frequency_client.id)

            if x_continuous_medication == "yes":
                continuous_medication = http.request.env["res.partner.category"].search(
                    [("name", "=", "Cliente Frecuente")], limit=1
                )
                _logger.info(continuous_medication)
                category_ids_to_add.append(continuous_medication.id)
            category_ids_to_add = [cat_id for cat_id in category_ids_to_add if cat_id]
            operations = [(4, cat_id) for cat_id in category_ids_to_add]

            partner.write(
                {
                    "name": post.get("name"),
                    "email": post.get("email"),
                    "phone": post.get("phone"),
                    "x_gender": post.get("x_gender"),
                    "x_birthday_date": post.get("x_birthday_date"),
                    "state_id": int(post.get("state_id")),
                    "city": post.get("city"),
                    "comment": post.get("comment"),
                    "category_id": operations,
                }
            )
            partner.write({"update_token": None})
            return request.redirect("/update-thank-you")
        return request.render(view_id, {"partner": partner})


class WebsiteThankYou(http.Controller):

    @http.route("/update-thank-you", type="http", auth="public", website=True)
    def thank_you(self, **kwargs):

        version = {
            "server_version": "13.0",
        }
        view_id = request.env.ref("partner_custom_form.update_thank_you_template").id

        return request.render(view_id, {"version": version})
