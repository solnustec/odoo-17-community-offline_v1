# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplateInherit(models.Model):
    _inherit = 'product.template'

    class_id = fields.Many2one(
        "asset.class",
        string="Clase",
        help="Clasificación principal (ej. Computación, Vehículos, Muebles)."
    )

    subclass_id = fields.Many2one(
        "asset.subclass",
        string="Subclase",
        domain="[('class_id', '=', class_id)]",
        help="Subcategoría específica dentro de la clase seleccionada."
    )

    asset_brand_id = fields.Many2one(
        "asset.brand",
        string="Marca",
        domain="[('class_id', '=', class_id)]",
        help="Marca asociada a la clase seleccionada."
    )

    # ---- Extender TYPE ----
    type = fields.Selection(
        selection_add=[('activos_bienes', 'Activos/Bienes')],
        default='product',
        ondelete={'activos_bienes': 'set default'},
    )

    # ---- Extender DETAILED_TYPE ----
    detailed_type = fields.Selection(
        selection_add=[('activos_bienes', 'Activos/Bienes')],
        ondelete={'activos_bienes': 'set default'},
    )

    # Atributos adicionales del activo
    asset_model = fields.Char(string="Modelo")
    asset_serial = fields.Char(string="Serie")
    asset_specification = fields.Char(string="Especificaciones")
    asset_material = fields.Char(string="Material Producto")
    asset_color = fields.Char(string="Color Producto")

    # ---- Mantener type sincronizado ----
    @api.depends('detailed_type')
    def _compute_type(self):
        for rec in self:
            if rec.detailed_type in ('consu', 'product', 'service'):
                rec.type = rec.detailed_type
            elif rec.detailed_type == 'activos_bienes':
                rec.type = 'activos_bienes'
            else:
                rec.type = 'product'
