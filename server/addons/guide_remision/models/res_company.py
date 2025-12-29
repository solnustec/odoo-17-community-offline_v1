from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = 'res.company'

    establecimiento = fields.Char(string='Establecimiento')
    punto_emision = fields.Char(string='Punto de Emisión')
    l10n_ec_obligado_contabilidad = fields.Boolean(
        string='¿Obligado a llevar contabilidad?',
        help='Indica si la empresa está obligada a llevar contabilidad según la legislación ecuatoriana.',
        default=False
    )
    l10n_ec_establishment_code = fields.Char(string='Código de Establecimiento')

    l10n_ec_edi_certificate_id = fields.Many2one(
        'l10n_ec_edi.certificate',
        string='Certificado Electrónico',
        help='Certificado utilizado para firmar documentos electrónicos'
    )
    numero_guia_remision = fields.Char(string="Número de Guía de Remisión(Producción)", default='000000001', copy=False)
    numero_guia_pruebas = fields.Char(string="Número de Guía de Remisión(Pruebas)", default='000000001', copy=False)

    def _get_certificate(self):
        """
        Obtiene el certificado configurado para la compañía.
        """
        if self.l10n_ec_edi_certificate_id:
            return self.l10n_ec_edi_certificate_id

        certificate_id = self.env['ir.config_parameter'].sudo().get_param('l10n_ec_edi.certificate_id')

        if not certificate_id:
            raise ValidationError("No se ha configurado un certificado electrónico para esta compañía.")

        certificate = self.env['l10n_ec_edi.certificate'].browse(int(certificate_id))

        if not certificate or certificate_id == 0:
            raise ValidationError("El certificado configurado no es válido.")

        return certificate

