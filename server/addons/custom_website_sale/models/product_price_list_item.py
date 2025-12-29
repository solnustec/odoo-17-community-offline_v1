from odoo import models, fields, api


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    unit_size = fields.Char(string="Unidad de medida Ecommerce", required=False)

    def write(self, vals):
        """
            inserta el valor de unit_size, cuando se actualizar el valor de
             product.list.item en el product.template para que se pueda ver
            el nombre del producto en la pagina web
        """
        result = super(ProductPricelistItem, self).write(vals)
        if 'unit_size' in vals:
            for item in self:
                if item.product_tmpl_id:
                    item.product_tmpl_id.write({
                        'unit_size_display': item.unit_size
                    })

        return result

    def create(self, vals):
        """
            inserta el valor de unit_size, cuando se genera un nuevo registro en product.list.item
            en el product.template para que se pueda ver el
            nombre del producto en la pagina web
        """
        record = super(ProductPricelistItem, self).create(vals)
        if 'unit_size' in vals:
            if record.product_tmpl_id:
                record.product_tmpl_id.write({
                    'unit_size_display': record.unit_size
                })

        return record


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    unit_size_display = fields.Char(
        string="Unit Size",
    )


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model
    def create(self, vals):
        #por cajas en sitio web
        product = self.env['product.product'].browse(vals.get('product_id'))
        order = self.env['sale.order'].sudo().browse(vals.get('order_id'))
        get_order = order.read()
        if get_order[0].get('origin') == False:
            if product and product.product_tmpl_id.sale_uom_ecommerce:
                purchase_uom = product.product_tmpl_id.uom_po_id
                if purchase_uom:
                    vals['product_uom'] = purchase_uom.id
                    price = product.lst_price
                    if product.uom_id != purchase_uom:
                        price = product.uom_id._compute_price(price, purchase_uom)
                    vals['price_unit'] = price

        return super().create(vals)
