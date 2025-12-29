from odoo import api, fields, models


class test_connection_wizard(models.TransientModel):
    _name = 'test.connection.wizard'
    _description = "Show response message on wizard"

    def _get_whatsapp_message(self):
        return self._context['message']

    message = fields.Text("Response", default=_get_whatsapp_message, readonly=True)
