# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ModuleVersion(models.Model):
    """Versiones de módulos incluidos en un paquete (definido en update_package.py)"""
    _inherit = 'branch.module.version'
    _description = 'Module Version in Package'
