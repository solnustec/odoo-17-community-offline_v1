from odoo import http
from odoo.http import request


class PosSessionController(http.Controller):

    @http.route("/pos/update_out_money", type="json", auth="user")
    def update_out_money(self, session_id, out_money_value):
        """Llama al método update_out_money desde el frontend"""
        try:
            result = (
                request.env["pos.session"]
                .sudo()
                .update_out_money(session_id, out_money_value)
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}


class ForceLogoutController(http.Controller):
    @http.route("/custom/force_logout", type="http", auth="public")
    def custom_force_logout(self, **kw):

        #  logout estándar (borra sesión server-side)
        request.session.logout(keep_db=False)

        # respuesta HTTP normal (puede ser un redirect, una página, etc.)
        response = request.redirect("/")

        # Borra la cookie, setea valor vacío y fecha expirada
        response.set_cookie(
            "session_id",
            value="",
            expires="Thu, 01 Jan 1970 00:00:00 GMT",
            max_age=0,
            path="/",
            domain=None,
            secure=False,
            httponly=True,
            samesite="Lax",
        )
        return response
