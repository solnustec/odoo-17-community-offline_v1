from odoo import models, api, fields
import logging


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        try:
            res = super(StockPicking, self).button_validate()
            self.send_validation_email()
            return res
        except Exception as e:
            logging.error(f"Error al ejecutar el botón de validación: {str(e)}")
            raise

    def send_validation_email(self):
        _logger = logging.getLogger(__name__)
        try:

            sale_order = self.env['sale.order'].search([('picking_ids', 'in', self.ids)], limit=1)
            if not sale_order:
                _logger.warning("⚠️ No se encontró orden de venta asociada")
                return

            if not sale_order.partner_id.email:
                _logger.error("❌ El cliente no tiene email configurado")
                return

            template = self.env.ref('email_format.email_template_stock_dispatch', raise_if_not_found=False)
            if not template:
                _logger.error("❌ Plantilla no encontrada!")
                return

            ctx = {
                'delivery_subtotal': sale_order.delivery_subtotal_mail,
                'discount_promotions': sale_order.discount_promotions_mail,
                'default_model': 'sale.order',
                'default_res_id': sale_order.id,
            }

            template.with_context(ctx).send_mail(sale_order.id, force_send=True)

        except Exception as e:
            _logger.error("Error: %s", str(e), exc_info=True)
            raise