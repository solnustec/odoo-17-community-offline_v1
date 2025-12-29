from odoo import models, fields


class UserNotification(models.Model):
    _name = 'user.notification'
    _description = 'User Notification'

    name = fields.Char(
        string='Notification Name',
        required=False,
        help='Name of the notification'
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=False,
        ondelete='set null',
        help='User to whom the notification is addressed'
    )
    message = fields.Char(
        string='Message',
        required=False,
        help='Content of the notification message'
    )
    is_read = fields.Boolean(
        string='Is Read',
        default=False,
        help='Indicates whether the notification has been read by the user'
    )
    date_created = fields.Datetime(
        string='Date Created',
        default=fields.Datetime.now(),
        help='Timestamp when the notification was created'
    )
