from odoo import models, api

class ProductCategory(models.Model):
    _inherit = 'product.category'

    # methods for set as default the Metodo de costo Costo promedio (AVCO) and Valuación de inventario  Automatizado in all categories
    # The python code for the manual configuration of the server action be the next (affects product.category model):

    # records = env['product.category'].with_context(bypass_restrictions=True).search([])
    # records.write({
    #     'property_cost_method': 'average',
    #     'property_valuation': 'real_time',
    # })

    # @api.model
    # def create(self, vals):
    #     vals.update({
    #         'property_cost_method': 'average',
    #         'property_valuation': 'real_time',
    #     })
    #     return super().create(vals)
    #
    # def write(self, vals):
    #     if not self.env.context.get('bypass_restrictions'):
    #         vals.pop('property_cost_method', None)
    #         vals.pop('property_valuation', None)
    #     return super().write(vals)

