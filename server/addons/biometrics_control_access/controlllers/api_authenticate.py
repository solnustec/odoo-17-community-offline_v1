
from odoo import http
import odoo
from odoo.exceptions import AccessError
from odoo.http import request


class AuthenticateBiometricsController(http.Controller):
    @http.route('/web/session/authenticate/biometrics', type='json', auth="none")
    def authenticate(self, db, login, password, base_location=None):
        if not http.db_filter([db]):
            raise AccessError("Database not found.")

        # Authenticate user
        pre_uid = request.session.authenticate(db, login, password)

        # Check if authentication failed
        if pre_uid is False:
            raise AccessError("Invalid credentials.")

        # Create environment
        registry = odoo.modules.registry.Registry(db)
        with registry.cursor() as cr:
            env = odoo.api.Environment(cr, pre_uid, {})

            # Get the user
            user = env['res.users'].browse(pre_uid)

            authorized_groups = [
                env.ref('biometrics_control_access.group_biometrics_access_team_admin'),
            ]

            # Check if user belongs to any of the authorized groups
            if not any(group in user.groups_id for group in authorized_groups):
                raise AccessError("User does not have required access permissions.")

            # Set session details
            request.session.db = db
            request.session.uid = pre_uid

            # Rotate session token
            if not request.db:
                http.root.session_store.rotate(request.session, env)
                request.future_response.set_cookie(
                    'session_id', request.session.sid,
                    max_age=http.SESSION_LIFETIME, httponly=True
                )

            return env['ir.http'].session_info()