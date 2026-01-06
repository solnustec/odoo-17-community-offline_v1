# -*- coding: utf-8 -*-
"""Configuración del módulo de reabastecimiento automático."""
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    """Settings para reabastecimiento automático."""
    _inherit = 'res.config.settings'

    # Habilitar el módulo
    auto_replenishment_enabled = fields.Boolean(
        string='Habilitar Reabastecimiento Automático',
        config_parameter='stock_auto_replenishment.enabled',
        help='Activa el procesamiento automático de orderpoints con trigger=auto',
    )

    # Modo: individual o agrupado
    auto_replenishment_mode = fields.Selection([
        ('individual', 'Individual (1 transferencia por producto)'),
        ('grouped', 'Agrupado (comportamiento estándar Odoo)'),
    ],
        string='Modo de Transferencias',
        config_parameter='stock_auto_replenishment.mode',
        default='individual',
        help='Individual: crea 1 picking por orderpoint/producto.\n'
             'Agrupado: usa el mecanismo estándar de Odoo que agrupa.',
    )

    # Límite por ejecución
    auto_replenishment_batch_limit = fields.Integer(
        string='Límite por ejecución',
        config_parameter='stock_auto_replenishment.batch_limit',
        default=100,
        help='Número máximo de procurements por ejecución del cron.',
    )

    # Verificar stock
    auto_replenishment_check_stock = fields.Boolean(
        string='Verificar stock en origen',
        config_parameter='stock_auto_replenishment.check_stock',
        default=True,
        help='Solo crear transferencias si hay stock disponible en origen.',
    )

    # Auto-confirmar
    auto_replenishment_auto_confirm = fields.Boolean(
        string='Auto-confirmar transferencias',
        config_parameter='stock_auto_replenishment.auto_confirm',
        default=True,
        help='Confirmar y reservar stock automáticamente al crear.',
    )

    # Días para expiración de transferencias
    auto_replenishment_expiration_days = fields.Integer(
        string='Días para cancelar transferencias',
        config_parameter='stock_auto_replenishment.expiration_days',
        default=5,
        help='Cancelar automáticamente transferencias no validadas después de X días. 0 = desactivado.',
    )

    @api.model
    def get_values(self):
        """Obtiene los valores de configuración."""
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()

        res.update({
            'auto_replenishment_enabled': ICP.get_param(
                'stock_auto_replenishment.enabled', 'False') == 'True',
            'auto_replenishment_mode': ICP.get_param(
                'stock_auto_replenishment.mode', 'individual'),
            'auto_replenishment_batch_limit': int(ICP.get_param(
                'stock_auto_replenishment.batch_limit', '100')),
            'auto_replenishment_check_stock': ICP.get_param(
                'stock_auto_replenishment.check_stock', 'True') == 'True',
            'auto_replenishment_auto_confirm': ICP.get_param(
                'stock_auto_replenishment.auto_confirm', 'True') == 'True',
            'auto_replenishment_expiration_days': int(ICP.get_param(
                'stock_auto_replenishment.expiration_days', '5')),
        })
        return res

    def set_values(self):
        """Guarda los valores de configuración."""
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()

        ICP.set_param(
            'stock_auto_replenishment.enabled',
            str(self.auto_replenishment_enabled)
        )
        ICP.set_param(
            'stock_auto_replenishment.mode',
            self.auto_replenishment_mode or 'individual'
        )
        ICP.set_param(
            'stock_auto_replenishment.batch_limit',
            str(self.auto_replenishment_batch_limit)
        )
        ICP.set_param(
            'stock_auto_replenishment.check_stock',
            str(self.auto_replenishment_check_stock)
        )
        ICP.set_param(
            'stock_auto_replenishment.auto_confirm',
            str(self.auto_replenishment_auto_confirm)
        )
        ICP.set_param(
            'stock_auto_replenishment.expiration_days',
            str(self.auto_replenishment_expiration_days)
        )
