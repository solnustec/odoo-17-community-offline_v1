from collections import OrderedDict
from datetime import datetime, date
import logging

from odoo import models, api, fields

from odoo.exceptions import UserError
from odoo.tools.zeep import Client

_logger = logging.getLogger(__name__)

PRODUCTION_ENVIRONMENT = 2
SRI_FETCH_WS = {
    PRODUCTION_ENVIRONMENT: "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl",
}


class ImportXmlWizard(models.TransientModel):
    _name = 'import.xml.wizard'
    _description = 'Importar XML para Orden de Compra'

    file = fields.Binary(string="Archivo XML", required=False)
    access_token = fields.Char(string="Clave de Acceso SRI", required=True)

    def _calculate_discount_percentage(self, cantidad, precio_unitario, descuento):
        """
        Calcula el porcentaje de descuento a partir del valor absoluto.

        Fórmula: descuento_porcentaje = (descuento / subtotal_bruto) * 100

        Args:
            cantidad: Cantidad total
            precio_unitario: Precio unitario
            descuento: Descuento en valor absoluto del XML

        Returns:
            float: Porcentaje de descuento (0-100)
        """
        try:
            cantidad = float(cantidad) if cantidad else 0.0
            precio_unitario = float(precio_unitario) if precio_unitario else 0.0
            descuento = float(descuento) if descuento else 0.0

            if cantidad <= 0 or precio_unitario <= 0:
                return 0.0

            subtotal_bruto = cantidad * precio_unitario

            if subtotal_bruto <= 0:
                return 0.0

            porcentaje = (descuento / subtotal_bruto) * 100

            return round(porcentaje, 2)
        except (ValueError, TypeError, ZeroDivisionError):
            return 0.0

    def _get_additional_info_text(self, det_adicional_list):
        """
        Extrae información adicional relevante para mostrar en la nota.

        Args:
            det_adicional_list: Lista de diccionarios con @nombre y @valor

        Returns:
            str: Texto con la información adicional formateada
        """
        if not det_adicional_list:
            return ""

        # Asegurar que es una lista
        if isinstance(det_adicional_list, dict):
            det_adicional_list = [det_adicional_list]

        info_parts = []
        for det in det_adicional_list:
            nombre = det.get('@nombre', '')
            valor = det.get('@valor', '')
            if nombre and valor:
                info_parts.append(f"{nombre}: {valor}")

        return " | ".join(info_parts) if info_parts else ""

    def _convert_authorization_date(self, fecha_auth):
        if not fecha_auth:
            return False

        # Si es datetime, extraer date
        if isinstance(fecha_auth, datetime):
            return fecha_auth.date()

        # Si ya es date, retornar directamente la fecha
        if isinstance(fecha_auth, date):
            return fecha_auth

        # Si es string
        if isinstance(fecha_auth, str):
            try:
                # Formato ISO con timezone
                fecha_str = fecha_auth.split('T')[0]  # Tomar solo la parte de fecha
                return datetime.strptime(fecha_str, "%Y-%m-%d").date()
            except:
                return False

        return False

    def import_xml(self):
        existing_order = self.env['purchase.order'].search([
            ('sri_authorization_code', '=', self.access_token),
            ('is_created_from_xml', '=', True),('state', '!=', 'cancel')],
            limit=1)
        if existing_order:
            raise UserError(
                f"Ya existe una orden de compra con la clave de acceso {self.access_token}.")
        order_id = self.process_sri_authorization(self.access_token)
        if order_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Órdenes de Compra',
                'res_model': 'purchase.order',
                'res_id': order_id,
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'search_default_draft': 1,
                    'default_state': 'draft',
                },
                'domain': [('state', '=', 'draft')],
            }
        raise UserError(
            "error"
        )

    def process_sri_authorization(self, authorization_number):
        """
        Procesa un número de autorización del SRI y actualiza los campos de la orden de compra.
        Args:
            authorization_number (str): Número de autorización a consultar.
        """
        if not authorization_number and len(authorization_number) < 49:
            raise UserError(
                "Debe ingresar un número de autorización y vuelva a intentarlo.")

        # Consulta al SRI
        client = Client(SRI_FETCH_WS[PRODUCTION_ENVIRONMENT])
        purchase_order = None
        # try:
        result = client.service.autorizacionComprobante(
            authorization_number)
        if not hasattr(result, "numeroComprobantes") or not int(
                result.numeroComprobantes):
            raise UserError("La clave de acceso consultada es incorrecta.")

        if hasattr(result, "numeroComprobantes"):
            number_of_vouchers = int(result.numeroComprobantes)
            if not number_of_vouchers:
                raise UserError(
                    "La clave de acceso consultada es incorrecta")
            data = result.autorizaciones.autorizacion[0]

            def to_dict(obj):
                if isinstance(obj, OrderedDict):
                    obj = dict(obj)
                    for key in obj:
                        obj[key] = to_dict(obj[key])
                    return obj
                elif isinstance(obj, list):
                    obj = [to_dict(el) for el in obj]
                return obj

            import xmltodict
            invoice = to_dict(xmltodict.parse(data.comprobante))
            fecha_auth_sri = data.fechaAutorizacion
            factura = invoice.get('factura', {})
            detalles = factura.get("detalles")
            invoice_products = detalles.get("detalle")
            info_tributaria = factura.get('infoTributaria', {})
            info_factura = factura.get('infoFactura', {})
            emission_date = info_factura.get('fechaEmision')
            authorization_date = self._convert_authorization_date(fecha_auth_sri)
            invoice_number = info_tributaria.get(
                'estab') + "-" + info_tributaria.get(
                'ptoEmi') + "-" + info_tributaria.get('secuencial')
            if not invoice_products or not factura or not detalles:
                raise UserError(
                    "El XML no contiene productos o detalles válidos.")

            if factura and detalles and invoice_products:
                info_tributaria = factura.get('infoTributaria', {})
                ruc = info_tributaria.get('ruc')
                partner = self.env['res.partner'].search(
                    [('vat', '=', ruc)])

                if not partner:
                    # crear el partner si no existe
                    partner = self.env['res.partner'].create({
                        'name': factura.get('razonSocialComprador',
                                            'Proveedor Desconocido'),
                        'vat': ruc,
                        'is_company': True,
                        'street': factura.get('direccionComprador', ''),
                        'city': factura.get('ciudadComprador', ''),
                        'country_id': 63,  # Ecuador
                    })
                    purchase_order = self.env['purchase.order'].create({
                        "partner_id": partner.id,
                        'is_created_from_xml': True,
                        'invoice_number': invoice_number,
                        "sri_authorization_code": authorization_number,
                    })
                else:
                    purchase_order = self.env['purchase.order'].create({
                        "partner_id": partner.id,
                        'is_created_from_xml': True,
                        'invoice_number': invoice_number,
                        "sri_authorization_code": authorization_number,
                    })
            if type(invoice_products) is list:
                _logger.info("Procesando %d productos de la factura", len(invoice_products))
                for detail_product in invoice_products:
                    product_name = detail_product.get('descripcion', '')
                    default_code = detail_product.get('codigoPrincipal', '')
                    cantidad = detail_product.get('cantidad', '0')
                    precio_unitario = detail_product.get('precioUnitario', '0')
                    # Obtener descuento directamente del campo 'descuento' del detalle
                    descuento_xml = detail_product.get('descuento', '0')

                    detalles_adicionales = detail_product.get('detallesAdicionales', {}) or {}
                    det_adicional = detalles_adicionales.get('detAdicional', {})

                    # Asegurar que det_adicional sea una lista
                    det_adicional_list = det_adicional if isinstance(det_adicional, list) else [det_adicional] if det_adicional else []

                    # Calcular el descuento porcentual
                    discount_percentage = self._calculate_discount_percentage(
                        cantidad, precio_unitario, descuento_xml
                    )

                    # Obtener información adicional para la nota
                    additional_info = self._get_additional_info_text(det_adicional_list)

                    _logger.debug(
                        "Producto: %s, Código: %s, Cantidad: %s, Precio: %s, "
                        "Descuento XML: %s, Descuento %%: %s",
                        product_name, default_code, cantidad, precio_unitario,
                        descuento_xml, discount_percentage
                    )

                    # seccion impuestos
                    impuestos_list = detail_product.get('impuestos', {}).get(
                        'impuesto', [])
                    if isinstance(impuestos_list, dict):
                        impuestos_list = [impuestos_list]
                    impuestos_list_filtrados = [d for d in impuestos_list if d.get('valor', '0.00') != '0.00']

                    for impuesto in impuestos_list_filtrados:
                        if isinstance(impuesto, dict):
                            tax = None
                            sri_code = impuesto.get('codigoPorcentaje', '')
                            tarifa = impuesto.get('tarifa', '0')
                            try:
                                tarifa_float = float(tarifa)
                            except (ValueError, TypeError):
                                tarifa_float = 0.0

                            if impuesto.get('codigo') == '2' and tarifa_float > 0.00:
                                # IVA
                                tax = self.env['account.tax'].search(
                                    [('amount', '=', tarifa),
                                     ('type_tax_use', '=', 'purchase'),
                                     ('l10n_ec_code_taxsupport', '=', sri_code if len(sri_code) > 1 else f"0{sri_code}")], limit=1)
                            elif impuesto.get('codigo') == '3' and tarifa_float > 0.00:
                                # ICE
                                tax = self.env['account.tax'].search(
                                    [('type_tax_use', '=', 'purchase'),
                                     ('l10n_ec_code_applied', '=', sri_code)], limit=1)
                            elif impuesto.get('codigo') == '5' and tarifa_float > 0.00:
                                # IRBPNR
                                tax = self.env['account.tax'].search(
                                    [('amount', '=', tarifa),
                                     ('type_tax_use', '=', 'purchase'),
                                     ('l10n_ec_code_applied', '=', sri_code)], limit=1)
                            impuesto["tax"] = [tax] if tax else []

                    # Buscar producto
                    product_id = self.env['product.product'].search([
                        '|',
                        '|',
                        ('name', 'ilike', product_name),
                        ('default_code', '=', default_code),
                        ('multi_barcode_ids.product_multi_barcode', '=', default_code),
                    ], limit=1)

                    tax_ids = [item['tax'][0].id for item in impuestos_list_filtrados if item.get('tax') and item['tax'][0]]

                    if product_id:
                        # Producto encontrado - crear línea normal
                        purchase_order.write({
                            'order_line': [(0, 0, {
                                'product_id': product_id.id,
                                'name': product_id.name,
                                'product_qty': float(cantidad),
                                'price_unit': float(precio_unitario),
                                'discount': discount_percentage,
                                'taxes_id': [(6, 0, tax_ids)] if tax_ids else [],
                            })]
                        })
                    else:
                        # Producto NO encontrado - crear nota informativa (formato original)
                        nota_info = f"[{default_code}] {product_name} | Cant: {cantidad} | P.Unit: {precio_unitario} | Desc: {descuento_xml} ({discount_percentage}%)"
                        if additional_info:
                            nota_info += f" | {additional_info}"
                        purchase_order.write({
                            'order_line': [(0, 0, {
                                'name': nota_info,
                                'product_qty': 0,
                                'price_unit': 0.0,
                                'display_type': 'line_note',
                                'product_uom': False,
                                'product_id': False,
                            })]
                        })


            elif type(invoice_products) is dict:
                _logger.info("Procesando 1 producto de la factura (dict)")
                product_name = invoice_products.get('descripcion', '')
                default_code = invoice_products.get('codigoPrincipal', '')
                cantidad = invoice_products.get('cantidad', '0')
                precio_unitario = invoice_products.get('precioUnitario', '0')
                # Obtener descuento directamente del campo 'descuento' del detalle
                descuento_xml = invoice_products.get('descuento', '0')

                detalles_adicionales = invoice_products.get('detallesAdicionales', {}) or {}
                det_adicional = detalles_adicionales.get('detAdicional') if detalles_adicionales else None

                # Asegurar que det_adicional sea una lista
                det_adicional_list = det_adicional if isinstance(det_adicional, list) else [det_adicional] if det_adicional else []

                # Calcular el descuento porcentual
                discount_percentage = self._calculate_discount_percentage(
                    cantidad, precio_unitario, descuento_xml
                )

                # Obtener información adicional para la nota
                additional_info = self._get_additional_info_text(det_adicional_list)

                _logger.debug(
                    "Producto: %s, Código: %s, Cantidad: %s, Precio: %s, "
                    "Descuento XML: %s, Descuento %%: %s",
                    product_name, default_code, cantidad, precio_unitario,
                    descuento_xml, discount_percentage
                )

                impuestos = invoice_products.get('impuestos', {}) or {}
                impuesto = impuestos.get('impuesto', {}) if impuestos else {}
                sri_code = impuesto.get('codigoPorcentaje', '')
                tarifa = impuesto.get('tarifa', '0')

                product_id = self.env['product.product'].search([
                    '|',
                    '|',
                    ('name', 'ilike', product_name),
                    ('default_code', '=', default_code),
                    ('multi_barcode_ids.product_multi_barcode', '=', default_code),
                ], limit=1)

                tax = None
                try:
                    if float(tarifa) > 0:
                        tax = self.env['account.tax'].search(
                            [('amount', '=', tarifa),
                             ('type_tax_use', '=', 'purchase'),
                             ('l10n_ec_code_taxsupport', '=', sri_code if len(sri_code) > 1 else f"0{sri_code}")], limit=1)
                except (ValueError, TypeError):
                    pass

                if product_id:
                    # Producto encontrado - crear línea normal
                    purchase_order.write({
                        'order_line': [(0, 0, {
                            'product_id': product_id.id,
                            'name': product_id.name,
                            'product_qty': float(cantidad),
                            'price_unit': float(precio_unitario),
                            'discount': discount_percentage,
                            'taxes_id': [(6, 0, tax.ids)] if tax else [],
                        })]
                    })
                else:
                    # Producto NO encontrado - crear nota informativa (formato original)
                    nota_info = f"[{default_code}] {product_name} | Cant: {cantidad} | P.Unit: {precio_unitario} | Desc: {descuento_xml} ({discount_percentage}%)"
                    if additional_info:
                        nota_info += f" | {additional_info}"
                    purchase_order.write({
                        'order_line': [(0, 0, {
                            'name': nota_info,
                            'product_qty': 0,
                            'price_unit': 0.0,
                            'display_type': 'line_note',
                            'product_uom': False,
                            'product_id': False,
                        })]
                    })
            #formta date yyyy-mm-dd
            emission_date = datetime.strptime(emission_date, '%d/%m/%Y').date()
            emission_date_formated  = emission_date.strftime('%Y-%m-%d')
            purchase_order.sri_authorization_code = authorization_number
            purchase_order.invoice_number = invoice_number
            purchase_order.emission_date = emission_date_formated
            purchase_order.authorization_date = authorization_date
        return purchase_order.id

    def _get_product(self, product_ref):
        """Buscar producto"""
        if not product_ref:
            return None

        # Buscar por referencia interna
        product = self.env['product.product'].search([
            ('default_code', '=', product_ref)
        ], limit=1)

        if not product:
            # Buscar por nombre
            product = self.env['product.product'].search([
                ('name', '=', product_ref)
            ], limit=1)

        return product

