from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    coupon = fields.Integer(string='Coupon',
                            help='Coupon asociado al producto, utilizado en promociones',
                            default=0)

    sales_stock_total = fields.Float(
        string='Sales Stock Total',
        help='Total de ventas del producto en stock, utilizado para reportes de ventas',
    )

    # producto dado de baja
    is_discontinued = fields.Boolean(
        string='Is Discontinued',
        help='Indica si el producto ha sido dado de baja',
        default=False,
    )

    def write(self, vals):
        # get context skip_update_form_product_api ANTES de super()
        ctx = self.env.context
        res = super(ProductTemplate, self).write(vals)
        if ctx.get('skip_update_form_product_api'):
            #contexo para evitar la creacion de registros en product.sync desde otros metodos write
            for product in self:
                if 'is_discontinued' in vals and vals['is_discontinued']:
                    self.env['product.sync'].sudo().create({
                        'product_id': product.id,
                        'downgrade': True,
                        'id_database_old': product.id_database_old
                    })
                elif any(campo in vals for campo in ['laboratory_id', 'brand_id']):
                    domain = [('product_id', '=', product.id),
                              ('id_database_old', '=', product.id_database_old),
                              ('downgrade', '=', False), ('status', '=', False)]
                    existing = self.env['product.sync'].sudo().search(domain, limit=1)
                    if not existing:
                        self.env['product.sync'].sudo().create({
                            'product_id': product.id,
                            'id_database_old': product.id_database_old
                        })
        return res

    # TODO por revisar se generan muchos registros en product.sync
    # def create(self, vals_list):
    #     res = super(ProductTemplate, self).create(vals_list)
    #     for product in res:
    #         if product.detailed_type == 'product':
    #             self.env['product.sync'].sudo().create({
    #                 'product_id': product.id,
    #                 'id_database_old': "-1",
    #                 'new':True
    #             })
    #     return res

    # def write(self, vals):
    #     res = super(ProductTemplate, self).write(vals)
    #     if 'active' in vals:
    #         for product in self:
    #             #si no tiene id_database_old, significa que es un producto nuevo
    #             if product.id_database_old == "-1" and vals['active']:
    #                 # Si el producto es nuevo y se activa
    #                 self.env['product.sync'].sudo().create({
    #                         'product_id': product.id,
    #                         'new': True,
    #                     })
    #             elif vals['active'] and product.id_database_old != "-1":
    #                 # Si el producto se activa y ya existe en la base de datos antigua
    #                 self.env['product.sync'].sudo().create({
    #                     'product_id': product.id,
    #                     'upgrade':True,
    #                     'id_database_old': product.id_database_old
    #                 })
    #             elif  vals['active'] is False and product.id_database_old != "-1":
    #                 # Si el producto se desactiva y ya existe en la base de datos antigua
    #                 self.env['product.sync'].sudo().create({
    #                     'product_id': product.id,
    #                     'downgrade': True,
    #                     'id_database_old': product.id_database_old
    #                 })
    #     return res
