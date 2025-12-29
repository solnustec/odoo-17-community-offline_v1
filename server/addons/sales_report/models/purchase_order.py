from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    brand_name = fields.Char(
        string='Marca',
        help='Marca seleccionada desde el reporte de ventas',
        tracking=True
    )

    laboratory_name = fields.Char(
        string='Laboratorio',
        help='Laboratorio seleccionado desde el reporte de ventas',
        tracking=True
    )


    # --- Comentado temporalmente: campos de marcas/laboratorios por aprobación ---
    # order_brands = fields.Many2many(
    #     'product.brand',
    #     string='Marcas',
    #     compute='_compute_order_brands_laboratories',
    #     store=False,
    #     help='Marcas de los productos en esta orden'
    # )
    # 
    # order_laboratories = fields.Many2many(
    #     'product.laboratory',
    #     string='Laboratorios',
    #     compute='_compute_order_brands_laboratories',
    #     store=False,
    #     help='Laboratorios de los productos en esta orden'
    # )
    # 
    # @api.depends('order_line.product_id')
    # def _compute_order_brands_laboratories(self):
    #     """Computar las marcas y laboratorios de todos los productos en la orden"""
    #     for order in self:
    #         brand_ids = []
    #         laboratory_ids = []
    #         for line in order.order_line:
    #             if line.product_id:
    #                 if line.product_id.brand_id:
    #                     brand_ids.append(line.product_id.brand_id.id)
    #                 if line.product_id.laboratory_id:
    #                     laboratory_ids.append(line.product_id.laboratory_id.id)
    #         order.order_brands = [(6, 0, list(set(brand_ids)))]
    #         order.order_laboratories = [(6, 0, list(set(laboratory_ids)))]

    # Campo simple de texto para guardar la marca seleccionada desde el frontend
