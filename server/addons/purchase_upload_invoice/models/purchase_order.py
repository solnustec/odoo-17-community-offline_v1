from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    sri_authorization_code = fields.Char(
        string='SRI Authorization Code',
        help='Code provided by SRI for the electronic invoice authorization.',
        tracking=True
    )
    is_created_from_xml = fields.Boolean(
        string='Created from XML',
        help='Indicates if the purchase order was created from an XML file.',
        default=False,
        tracking=True
    )
    invoice_number = fields.Char(
        string='Invoice Number',
        help='The invoice number associated with the purchase order.',
        tracking=True
    )
    emission_date = fields.Date(
        string='Fecha de Emisión',
        help='Fecha de emisión de la factura .',
        tracking=True
    )

    authorization_date = fields.Date(
        string='Fecha de Autorización',
        help='Fecha de autorización del SRI.',
        tracking=True
    )

    def _prepare_invoice(self):
        """Prepare the dict of values to create the new invoice for a purchase order.
        """
        self.ensure_one()
        # Obtener los valores preparados por el método original
        invoice_vals = super(PurchaseOrder, self)._prepare_invoice()

        # Agregar los valores de los campos personalizados para completar los valores de
        # de la factura desde la orden de compra
        invoice_vals.update({
            'l10n_ec_authorization_number': self.sri_authorization_code or '',
            'l10n_latam_document_number': self.invoice_number or '',
            'invoice_date':self.emission_date,
            'l10n_ec_authorization_date': self.authorization_date,
            'sri_data_loaded': self.is_created_from_xml,
        })

        return invoice_vals