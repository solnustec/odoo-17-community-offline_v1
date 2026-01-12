from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mode_strict = fields.Boolean(
        string="Modo estricto",
        default=False,
        help="Habilita la validación de lotes en inventario"
    )

    # Configuración de visibilidad de botones de inspección por tipo de picking
    qc_show_in_incoming = fields.Boolean(
        string="Recepciones",
        default=True,
        help="Mostrar botones de inspección de calidad en recepciones"
    )
    qc_show_in_outgoing = fields.Boolean(
        string="Entregas",
        default=False,
        help="Mostrar botones de inspección de calidad en entregas"
    )
    qc_show_in_internal = fields.Boolean(
        string="Transferencias internas",
        default=False,
        help="Mostrar botones de inspección de calidad en transferencias internas"
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        mode_strict = ICP.get_param('quality_control_stock_oca.mode_strict')
        qc_show_in_incoming = ICP.get_param('quality_control_stock_oca.qc_show_in_incoming', 'True')
        qc_show_in_outgoing = ICP.get_param('quality_control_stock_oca.qc_show_in_outgoing', 'False')
        qc_show_in_internal = ICP.get_param('quality_control_stock_oca.qc_show_in_internal', 'False')

        res.update(
            mode_strict=mode_strict if mode_strict else False,
            qc_show_in_incoming=qc_show_in_incoming in ('True', True, '1', 1),
            qc_show_in_outgoing=qc_show_in_outgoing in ('True', True, '1', 1),
            qc_show_in_internal=qc_show_in_internal in ('True', True, '1', 1),
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('quality_control_stock_oca.mode_strict', self.mode_strict)
        ICP.set_param('quality_control_stock_oca.qc_show_in_incoming', self.qc_show_in_incoming)
        ICP.set_param('quality_control_stock_oca.qc_show_in_outgoing', self.qc_show_in_outgoing)
        ICP.set_param('quality_control_stock_oca.qc_show_in_internal', self.qc_show_in_internal)