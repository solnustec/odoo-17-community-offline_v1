# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    allow_check_info = fields.Boolean(string="Allow Check Info")

    @api.model
    def load_credit_cards(self):
        return self.env['credit.card'].search_read([], ['id', 'name_card'])

    @api.model
    def _load_pos_data(self):
        # Cargar los datos normales del POS, como productos, bancos, etc.
        pos_data = super(PosConfig, self)._load_pos_data()

        # Agregar las tarjetas de crédito al diccionario de datos
        pos_data['credit_cards'] = self.load_credit_cards()

        return pos_data


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_allow_check_info = fields.Boolean(string="Allow Check Info",
                                          related="pos_config_id.allow_check_info",
                                          readonly=False)
