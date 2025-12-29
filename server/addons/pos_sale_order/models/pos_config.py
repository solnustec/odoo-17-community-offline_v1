# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'
    sync_data = fields.Boolean(string="Sincronizar Datos", default=True,
                               help="Habilitar para sincronizar los datos con el sistema antiguo", )
