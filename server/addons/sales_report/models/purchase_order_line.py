# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    free_product_qty = fields.Float(string='Free Product Qty', default=0.0, help='Cantidad de producto gratis (promoción)')

    # Cantidad realmente pagada (sin productos gratis)
    paid_quantity = fields.Float(string='Paid Quantity', default=0.0,
                                 help='Cantidad pagada (no incluye productos gratis)')

    # Sobrescribir product_qty para que sea calculado basado en paid_quantity + free_product_qty
    product_qty = fields.Float(
        string='Quantity', 
        digits='Product Unit of Measure', 
        required=True,
        compute='_compute_product_qty', 
        store=True, 
        readonly=False,
        inverse='_inverse_product_qty'
    )


    @api.depends('paid_quantity', 'free_product_qty')
    def _compute_product_qty(self):
        """
        """
        super()._compute_product_qty()
        
        # Luego aplicar nuestra lógica personalizada
        for line in self:
            if line.paid_quantity or line.free_product_qty:
                line.product_qty = line.paid_quantity + line.free_product_qty

    def _inverse_product_qty(self):
        """
        Cuando se cambia product_qty, actualiza paid_quantity manteniendo free_product_qty
        """
        for line in self:
            if line.product_qty >= line.free_product_qty:
                line.paid_quantity = line.product_qty - line.free_product_qty
            else:
                # Si la cantidad total es menor que la cantidad gratis, ajustar
                line.free_product_qty = line.product_qty
                line.paid_quantity = 0.0

    @api.depends('paid_quantity', 'free_product_qty')
    def _compute_price_unit_and_date_planned_and_name(self):
        """
        """
        super()._compute_price_unit_and_date_planned_and_name()
        
        # Luego calcular el descuento basado en la cantidad gratis
        for line in self:
            if line.paid_quantity or line.free_product_qty:
                total_quantity = line.paid_quantity + line.free_product_qty
                if total_quantity > 0:
                    # Calcular el porcentaje de descuento basado en la cantidad gratis
                    discount_percentage = (line.free_product_qty / total_quantity) * 100
                    # Sumar al descuento del proveedor si existe
                    line.discount = line.discount + round(discount_percentage, 2)


