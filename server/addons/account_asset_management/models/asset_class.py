# -*- coding: utf-8 -*-
from odoo import fields, models


class AssetClass(models.Model):
    _name = "asset.class"
    _description = "Clase de Activo"
    _order = "name"

    name = fields.Char("Clase", required=True, index=True, help="Categoría de alto nivel del activo.")
    active = fields.Boolean(default=True)

    subclass_ids = fields.One2many(
        "asset.subclass",
        "class_id",
        string="Subclases",
        help="Lista de subclases asociadas a esta clase."
    )
    brand_ids = fields.One2many(
        "asset.brand",
        "class_id",
        string="Marcas",
        help="Lista de marcas asociadas a esta clase."
    )

    profile_id = fields.Many2one(
        "account.asset.profile",
        string="Perfil del Activo",
        help="Perfil contable que se usará para los activos de esta clase."
    )

    _sql_constraints = [
        ("asset_class_name_uniq", "unique(name)", "Ya existe una clase con ese nombre."),
    ]


class AssetSubclass(models.Model):
    _name = "asset.subclass"
    _description = "Subclase de Activo"
    _order = "name"

    name = fields.Char(
        "Subclase",
        required=True,
        index=True,
        help="Subcategoría específica dentro de la clase del activo."
    )
    class_id = fields.Many2one(
        "asset.class",
        string="Clase",
        required=True,
        ondelete="restrict",
        help="Clase a la cual pertenece esta subclase."
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('unique_subclass_per_class', 'unique(name, class_id)',
         'Ya existe una subclase con ese nombre para esta clase.'),
    ]


class AssetBrand(models.Model):
    _name = "asset.brand"
    _description = "Marca de Activo"
    _order = "name"

    name = fields.Char("Marca", required=True, index=True)
    active = fields.Boolean(default=True)

    class_id = fields.Many2one(
        "asset.class",
        string="Clase",
        required=True,
        ondelete="cascade",
        help="Clase a la cual pertenece esta marca."
    )

    _sql_constraints = [
        ('unique_brand_per_class', 'unique(name, class_id)',
         'Ya existe esta marca para la clase seleccionada.'),
    ]
