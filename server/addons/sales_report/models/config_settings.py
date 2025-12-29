# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auto_adjust_stock_from_sales_summary = fields.Boolean(
        string='Ajuste Automático de Stock desde Resumen de Ventas',
        readonly=False,
        help='Si está activo, al crear registros en el resumen de ventas por producto y almacén, '
             'se reducirá automáticamente el stock del producto en el almacén correspondiente '
             'usando la estrategia de remoción configurada (FEFO, FIFO, etc.)',
        default=False
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        auto_adjust = self.env['ir.config_parameter'].sudo().get_param(
            'product_warehouse_sale_summary.auto_adjust_stock_from_sales_summary',
            default='False'
        )

        res.update(
            auto_adjust_stock_from_sales_summary=auto_adjust == 'True',
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'product_warehouse_sale_summary.auto_adjust_stock_from_sales_summary',
            self.auto_adjust_stock_from_sales_summary
        )
