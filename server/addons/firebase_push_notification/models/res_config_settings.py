
from firebase_admin import initialize_app, _apps, messaging
from firebase_admin import credentials

from odoo import  models, _




class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def test_firebase_connection(self):
        try:
            self.env['firebase.service'].test_connection()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'message': _("Conexión con Firebase exitosa 🎉"),
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'danger',
                    'message': _("Error al conectar con Firebase: %s" % e),
                }
            }
