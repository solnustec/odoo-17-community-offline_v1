from odoo import models, api

class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def get_product_by_id_database_old(self, id_database_old):
        """
        Buscar el ID del product.product basado en el campo id_database_old (en product.template).
        """
        product = self.search([('product_tmpl_id.id_database_old', '=', id_database_old.lstrip('0'))], limit=1)
        if product:
            return {
                'product_id': product.id,
                'name': product.name,
            }
        return False
