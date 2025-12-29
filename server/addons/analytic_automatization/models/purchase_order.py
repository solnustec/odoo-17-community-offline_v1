from odoo import models, api, exceptions, _
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.constrains('order_line')
    def _check_analytic_distribution(self):
        """Verifica que todas las líneas tengan una cuenta analítica asignada."""
        for order in self:
            for line in order.order_line:
                if not line.analytic_distribution:
                    raise ValidationError(
                        _("La línea '%s' en la orden de compra '%s' no tiene una cuenta analítica asignada.") %
                        (line.name, order.name)
                    )

    def action_confirm(self):
        """Sobrescribe la confirmación para validar las cuentas analíticas antes de confirmar."""
        for order in self:
            for line in order.order_line:
                if not line.analytic_distribution:
                    raise ValidationError(
                        _("La línea '%s' en la orden de compra '%s' no tiene una cuenta analítica asignada.") %
                        (line.name, order.name)
                    )
        return super(PurchaseOrder, self).action_confirm()
