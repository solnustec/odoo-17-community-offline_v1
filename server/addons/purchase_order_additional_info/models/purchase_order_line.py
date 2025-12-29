# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    image_128 = fields.Image(string="Image")
    pvf = fields.Float(string='PVF', )
    pvf_css = fields.Char(string=' ',
                          compute='_compute_longitud_css',
                          store=False,
                          )

    @api.onchange('price_unit')
    def update_price_unit(self):
        """
        Updates the `pvf` field based on the `price_unit` value and product quantity.
        This method is triggered when the `price_unit` field changes.

        - Ensures the record is single (`ensure_one`).
        - Calculates the total units based on `product_qty` and `product_uom.factor_inv`.
        - Updates the `pvf` field using the formula: `price_unit / product_qty`.
        - Prints the updated `pvf` and `price_unit` values for debugging purposes.
        """
        self.ensure_one()
        if self.price_unit > 0:
            self.pvf = self.price_unit / self.product_uom.factor_inv

    @api.onchange('pvf')
    def update_pvf(self):
        """
        Updates the `price_unit` field based on the `pvf` value and product quantity.
        This method is triggered when the `pvf` field changes.

        - Ensures the record is single (`ensure_one`).
        - Calculates the total units based on `product_qty` and `product_uom.factor_inv`.
        - Updates the `price_unit` field using the formula: `pvf * product_qty`.
        - Prints the updated `price_unit` and `pvf` values for debugging purposes.
        """
        self.ensure_one()
        if self.pvf > 0:
            self.price_unit = self.pvf * self.product_uom.factor_inv

    @api.onchange('product_id')
    def onchange_purchase_product_image(self):
        for product in self:
            product.image_128 = product.product_id.image_128

    def _compute_longitud_css(self):
        for line in self:
            line.pvf_css = ''
    #     """
    #     Calcula y asigna una clase CSS al campo `pvf_css` basado en la comparación
    #     entre el costo de la última compra y el valor del campo `pvf`.
    #
    #     - Si el costo de la última compra es menor que `pvf`, se asigna la clase 'text-danger'.
    #     - Si no hay un costo de última compra o este es mayor o igual a `pvf`, no se asigna ninguna clase.
    #
    #     Lógica:
    #     1. Inicializa el costo de la última compra en 0.0.
    #     2. Si el producto está definido, obtiene la última línea de pedido asociada al producto.
    #     3. Recupera el precio unitario de la última compra, si existe.
    #     4. Compara el precio unitario con el valor de `pvf` para determinar la clase CSS.
    #     """
    #     for line in self:
    #         last_purchase = 0.0
    #         if line.product_id:
    #             # Obtiene la última línea de pedido del producto, si existe
    #             last_line = line.product_id[0].po_product_line_ids[-1] if \
    #                 line.product_id[0].po_product_line_ids else []
    #             last_purchase = last_line[0].price_unit if last_line else 0.0
    #         if last_purchase:
    #             # Asigna la clase CSS según la comparación
    #             if last_purchase < line.pvf:
    #                 line.pvf_css = 'text-danger'
    #             else:
    #                 line.pvf_css = ''
    #         else:
    #             # No hay costo de última compra, no se asigna clase
    #             line.pvf_css = ''
