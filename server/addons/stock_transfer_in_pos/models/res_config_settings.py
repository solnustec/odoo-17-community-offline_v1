# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Ranjith R(odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.

###############################################################################
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Inheriting model for adding a field to settings that allow to
            transfer stock from pos session """
    _inherit = 'res.config.settings'

    is_stock_transfer = fields.Boolean(
        related="pos_config_id.stock_transfer",
        string="Habilitar Transferencias de Stock",
        help="Habilita la opción para transferir stock desde la sesión del POS",
        readonly=False
    )
    show_auto_transfers = fields.Boolean(
        related="pos_config_id.show_auto_transfers",
        string="Permitir ver transferencias automáticas",
        help="Si está habilitado, el usuario podrá ver y validar las "
             "transferencias generadas automáticamente por el sistema de "
             "reabastecimiento. Por defecto está deshabilitado.",
        readonly=False,
    )
