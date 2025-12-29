from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    # agregar el campo a los datos del pos
    def _loader_params_pos_payment_method(self):
        result = super()._loader_params_pos_payment_method()
        result['search_params']['fields'].append('payment_restrictions')
        return result
