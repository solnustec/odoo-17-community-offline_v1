# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Inheriting model for adding a field to settings that allow to
            transfer stock from pos session """
    _inherit = 'res.config.settings'

    sync_data = fields.Boolean(related="pos_config_id.sync_data",
                               string="Sincronizar Datos",
                               help="Habilitar para sincronizar los datos con el sistema antiguo",
                               readonly=False)
