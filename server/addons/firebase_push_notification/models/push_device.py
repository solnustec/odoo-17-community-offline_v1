from odoo import fields, models, api


class PushDevice(models.Model):
    _name = 'push.device'
    _description = 'Web Push Notification'

    name = fields.Char(string="Dispositivo", help="Name of the device")

    platform = fields.Selection([
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('web', 'Web'),
    ], string='Platform', help="Plataforma")

    active = fields.Boolean(default=True,
                            help="Whether this token is currently active")

    user_id = fields.Many2one("res.users", string="Usuario",
                              help="Corresponding Firebase User")
    register_id = fields.Char(string="Token del dispositivo",
                              help="Firebase Registration Token")
    created_at = fields.Datetime(string="Creado el",
                                 default=fields.Datetime.now,
                                 help="Fecha de creación del registro")

    def deactivate_invalid_token(self):
        """Desactivar o eliminar dispositivo con token inválido"""
        self.ensure_one()
        self.unlink()  # Elimina el registro
        # O si prefieres desactivar: self.write({'active': False})

    # @api.constrains('register_id')
    # def _check_or_update_register_id(self):
    #     for record in self:
    #         if record.register_id:
    #             existing = self.search([
    #                 ('register_id', '=', record.register_id),
    #                 ('id', '!=', record.id),
    #             ], limit=1)
    #             if existing:
    #                 existing.user_id = record.user_id.id

    @api.model
    def find_by_user(self, user_id):
        """
        Busca un dispositivo por el id del usuario
        # devices = self.env['push.device'].find_by_user(user_id)
        """
        device = self.env['push.device'].sudo().search([('user_id', '=', user_id)], limit=1)

        return device
