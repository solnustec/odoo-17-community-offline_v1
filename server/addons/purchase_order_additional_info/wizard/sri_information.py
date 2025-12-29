from odoo import models, fields, api

class SriErrorWizard(models.TransientModel):
    _name = 'sri.information.wizard'
    _description = 'Wizard para Error SRI'

    message = fields.Text(string="Mensaje", readonly=True)

    def action_accept(self):
        # Lógica para "Aceptar"
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        # Lógica para "Cancelar"
        return {'type': 'ir.actions.act_window_close'}