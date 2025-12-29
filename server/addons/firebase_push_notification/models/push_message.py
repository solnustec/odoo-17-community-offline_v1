from odoo import models, fields, api


class PushMessage(models.Model):
    _name = 'push.message'
    _description = 'Push Notification Message'

    name = fields.Char(string="Titulo de la notificación", required=True,
                       tracking=True, )
    body = fields.Text(string="Message", required=True, tracking=True,
                       )
    image = fields.Binary(string="Image", tracking=True,
                          )
    image_url = fields.Char(string="Image URL",
                            help="Optional image in the notification",
                            compute='_compute_image_url', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sending', 'Enviando'),
        ('done', 'Enviado'),
    ], default='draft', string="State", tracking=True)
    user_id = fields.Many2one('res.users', string='User',
                              default=lambda self: self.env.user,
                              readonly=True, tracking=True)
    device_ids = fields.Many2many('push.device', string='Dispositivos',
                                  help="Destinatarios de la notificación, si esta vacio se envia a todos los usuarios",
                                  )
    message_lines = fields.One2many('push.message.line', 'push_message_id',
                                    string='Notification Lines',
                                    ondelete='cascade')

    create_date = fields.Datetime(string='Created On', readonly=True)
    send_date = fields.Datetime(string='Fecha programada de envio',
                                default=fields.Datetime.now)

    @api.model
    def create(self, vals):
        record = super().create(vals)
        devices = record.device_ids

        # Si no hay dispositivos seleccionados, puedes cargar todos si deseas
        if not devices:
            devices = self.env['push.device'].search([('active', '=', True)])

        lines = []
        for device in devices:
            lines.append({
                'push_message_id': record.id,
                'device_id': device.register_id,
                'sent_at': record.send_date,
            })

        self.env['push.message.line'].create(lines)
        return record

    def action_process_push_notification(self):
        self.write({'state': 'sending'})
        return True

    def _compute_image_url(self):
        for record in self:
            attachment = self.env['ir.attachment'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', record.id),
                ('res_field', '=', 'image')
            ], limit=1)
            attachment.write({'public': True})
            if attachment:
                record.image_url = attachment.image_src  # o el campo que contenga la URL de S3
            else:
                record.image_url = False


class PushMessageLine(models.Model):
    _name = 'push.message.line'
    _description = 'Push Notification Recipient'

    push_message_id = fields.Many2one('push.message',
                                      string='Notification',
                                      required=True, ondelete='cascade')
    device_id = fields.Char(string='Device Token', required=True)
    sent_at = fields.Datetime(string='Sent On', readonly=True)

    state = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('error', 'Error'),
    ], default='pending', string='Status')

    error_message = fields.Text(string="Error",
                                help="If failed, store error here")

    @api.model
    def send_pending_notifications(self):
        lines = self.search([('state', '=', 'pending')], limit=50)
        firebase = self.env['firebase.service']

        for line in lines:
            try:
                push_message = line.push_message_id
                firebase.send_push_notification(
                    registration_token=line.device_id,
                    title=push_message.name,
                    body=push_message.body,
                    data={}
                )
                line.write({
                    'state': 'sent',
                    'sent_at': fields.Datetime.now()
                })
            except Exception as e:
                line.write({
                    'state': 'error',
                    'error_message': str(e)
                })
