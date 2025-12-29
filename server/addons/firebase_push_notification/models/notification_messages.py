from odoo import models, fields


class NotificationMessage(models.Model):
    _name = 'notification.message'
    type = fields.Selection([
        ('login', 'Inicio de Sesión'),
        ('reward_claimed', 'Recompensa Reclamada'),
        ('order_payment', 'Generar Pago de Orden'),
        ('order_shipped', 'Orden Enviada'),
        ('order_canceled', 'Orden Cancelada'),
        ('order_canceled_text', 'Texto para cancelar la orden'),
        ('payment_failed', 'Pago Fallido'),
        ('payment_successful', 'Pago Exitoso'),
        ('promotion', 'Promoción'),
        ('cart_confirmed', 'Carrito Confirmado'),
    ], string='Tipo de mensaje', required=True, unique=True)
    title = fields.Char(string='Titulo de la notificación', required=True)
    body = fields.Text(string='Contenido de la notificación', required=True,
                       help="Puedes usar {{usuario_nombre}}, {{order_numero}}, {{order_total}}, {{recompensa}} como marcadores de posición.")

    def get_message_by_type(self, message_type):
        return self.search([('type', '=', message_type)], limit=1)
