
from odoo import api, http, models, tools, SUPERUSER_ID
from odoo.http import request, Response, ROUTING_KEYS, Stream

from werkzeug.exceptions import BadRequest, NotFound, Unauthorized

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'
    _description = "HTTP Routing"

    # ------------------------------------------------------
    # Routing map
    # ------------------------------------------------------

    @classmethod
    def _auth_method_my_api_key(cls):
        api_key = request.httprequest.headers.get("Authorization")
        if not api_key:
            raise BadRequest("Authorization header with API key missing")

        user_id = request.env["res.users.apikeys"]._check_credentials(
            scope="rpc", key=api_key
        )
        if not user_id:
            raise BadRequest("API key invalid")

        request.update_env(user_id)
