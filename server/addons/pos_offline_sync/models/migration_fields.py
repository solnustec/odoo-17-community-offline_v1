# -*- coding: utf-8 -*-
"""
Extensiones de modelos para soporte de migración.

Agrega campos id_database_old a modelos que no lo tienen
pero que son necesarios para la migración inicial.
"""
from odoo import models, fields


class AccountTax(models.Model):
    """
    Extensión de account.tax para sincronización/migración offline.
    """
    _inherit = 'account.tax'

    id_database_old = fields.Char(
        string='ID Base de Datos Origen',
        copy=False,
        index=True,
        help='ID del registro en la base de datos de origen (para migraciones)'
    )


class PosPaymentMethod(models.Model):
    """
    Extensión de pos.payment.method para sincronización/migración offline.
    """
    _inherit = 'pos.payment.method'

    id_database_old = fields.Char(
        string='ID Base de Datos Origen',
        copy=False,
        index=True,
        help='ID del registro en la base de datos de origen (para migraciones)'
    )


class UomUom(models.Model):
    """
    Extensión de uom.uom para sincronización/migración offline.
    Este campo puede ser sobrescrito si product_multi_uom_pos está instalado.
    """
    _inherit = 'uom.uom'

    id_database_old = fields.Char(
        string='ID Base de Datos Origen',
        copy=False,
        index=True,
        help='ID del registro en la base de datos de origen (para migraciones)'
    )


class UomCategory(models.Model):
    """
    Extensión de uom.category para sincronización/migración offline.
    """
    _inherit = 'uom.category'

    id_database_old = fields.Char(
        string='ID Base de Datos Origen',
        copy=False,
        index=True,
        help='ID del registro en la base de datos de origen (para migraciones)'
    )
