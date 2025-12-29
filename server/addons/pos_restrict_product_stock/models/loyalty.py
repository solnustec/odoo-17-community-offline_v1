from odoo import models, fields, api
from odoo.tools import logging



class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    def write(self, vals):
        if vals.get('active') is False:
            vals.update({
                'date_from': None,
                'date_to': None,
                'ecommerce_ok': False,
                'pos_ok': False,
                'sale_ok': False,
            })

        res = super().write(vals)

        for program in self:
            product_ids = program.rule_ids.mapped('product_ids')
            product_tmpl_ids = product_ids.mapped('product_tmpl_id')

            for product in product_ids:
                product._compute_discount()

            for product_tmpl in product_tmpl_ids:
                product_tmpl._compute_ecommerce_discount(
                    loyalty_program_id=program.id,
                    active=program.active,
                    ecommerce_ok=program.ecommerce_ok
                )
                product_tmpl._compute_ecommerce_required_points(
                    loyalty_program_id=program.id,
                    active=program.active,
                    ecommerce_ok=program.ecommerce_ok
                )
        return res

    def create(self, vals_list):
        res = super().create(vals_list)
        for vals in vals_list:
            if 'reward_ids' in vals or 'rule_ids' in vals:
                affected_products = res.mapped('rule_ids.product_ids')
                affected_templates = affected_products.mapped('product_tmpl_id')
                if res.id:
                    for product in affected_products:
                        product._compute_discount()

                    for template in affected_templates:
                        template._compute_ecommerce_discount(
                            loyalty_program_id=res.id, active=True,
                            ecommerce_ok=res.ecommerce_ok)
                        template._compute_ecommerce_required_points(
                            loyalty_program_id=res.id,
                            active=True,
                            ecommerce_ok=res.ecommerce_ok
                    )
        return res

    def unlink(self):
        affected_products = self.mapped('rule_ids.product_ids')
        affected_templates = affected_products.mapped('product_tmpl_id')
        res = super().unlink()
        for product in affected_products:
            product._compute_discount()
        for tmlp in affected_templates:
            tmlp._compute_ecommerce_discount()
            tmlp._compute_ecommerce_required_points()
        return res