from odoo import models, fields, api
from odoo.exceptions import UserError


class PublicProductCategory(models.Model):
    _inherit = 'product.public.category'

    # categoria principal de la app movil
    is_main_app_category = fields.Boolean(string='Es categoría principal de la app', default=False,
                                          help='Indica si esta categoría es la que se visualiza en la pagina principal de la aplicación móvil.')

    # controlar que que la categoria is_main_app_category solo haya una
    @api.constrains('is_main_app_category')
    def _check_main_app_category(self):
        main_categories = self.search([('is_main_app_category', '=', True)])
        if len(main_categories) > 1:
            raise UserError(f"Solo puede haber una categoría principal de la app móvil. deshabilite la otra categoria {main_categories[1].name} antes de realizar cambios.")
