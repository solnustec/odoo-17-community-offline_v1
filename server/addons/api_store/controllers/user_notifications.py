import json

from .api_security import validate_api_static_token
from .jwt import validate_jwt
from odoo import http
from odoo.http import request, Response


class UserNotification(http.Controller):
    @http.route('/api/store/user/notifications', type='http',
                auth='public',
                methods=['GET'],
                csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def get_user_notifications(self):
        jwt_data = getattr(request, '_jwt_data', {})
        user_id = jwt_data.get('user_id')
        if not user_id:
            return http.Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "El token proporcionado no es valido",
                        "data": None
                    }
                ),
                status=403,
                mimetype='application/json'
            )

        notifications = request.env['user.notification'].sudo().search(
            [('user_id', '=', user_id)],
            order='id DESC'
        )
        if not notifications:
            return Response(
                json.dumps({
                    "status": "success",
                    "message": "No hay notificaciones para el usuario",
                    "data": []
                }),
                status=200,
                mimetype='application/json'
            )

        notifications_data = [{
            'id': notification.id,
            'name': notification.name,
            'message': notification.message,
            'is_read': notification.is_read,
            'date_created': self._format_datetime_ecuador(notification.create_date)
        } for notification in notifications]
        # notifications_data = sorted(notifications_data,
        #                             key=lambda x: x['id'],
        #                             reverse=True)

        return Response(
            json.dumps({
                "status": "success",
                "message": "Notificaciones del usuario",
                "data": notifications_data
            }),
            status=200,
            mimetype='application/json'
        )

    def _format_datetime_ecuador(self, dt):
        """Convert datetime to Ecuador timezone (UTC-5)"""
        import pytz
        from datetime import datetime, date

        if not dt:
            return None

        # Si es date, convertir a datetime
        if isinstance(dt, date) and not isinstance(dt, datetime):
            dt = datetime.combine(dt, datetime.min.time())

        ecuador_tz = pytz.timezone('America/Guayaquil')
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt.astimezone(ecuador_tz).strftime('%Y-%m-%d %H:%M:%S')

    @http.route('/api/store/user/notifications/read', type='http',
                auth='public',
                methods=['POST'],
                csrf=False, cors="*")
    @validate_api_static_token
    @validate_jwt
    def mark_notifications_as_read(self):
        jwt_data = getattr(request, '_jwt_data', {})
        user_id = jwt_data.get('user_id')
        data = json.loads(request.httprequest.data.decode('utf-8'))
        notification_id = data.get('notification_id')
        if not user_id:
            return http.Response(
                json.dumps(
                    {
                        "status": "error",
                        "message": "El token proporcionado no es valido",
                        "data": None
                    }
                ),
                status=403,
                mimetype='application/json'
            )
        if notification_id and int(notification_id) > 0:
            notifications = request.env['user.notification'].sudo().search([
                ('user_id', '=', user_id), ('is_read', '=', False), ('id', '=', notification_id)
            ])
        else:
            notifications = request.env['user.notification'].sudo().search([
                ('user_id', '=', user_id), ('is_read', '=', False)
            ])
        notifications.write({'is_read': True})

        return Response(
            json.dumps({
                "status": "success",
                "message": "Notificaciones marcadas como leídas",
                "data": None
            }),
            status=200,
            mimetype='application/json'
        )
