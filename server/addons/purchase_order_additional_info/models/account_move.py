import requests

from odoo import models, api, _
from odoo.exceptions import UserError
from odoo.tools.zeep import Client
import xml.etree.ElementTree as ET
from datetime import datetime, date
import unicodedata
import re


class AccountMove(models.Model):
    _inherit = 'account.move'

    PRODUCTION_ENVIRONMENT = 2

    SRI_FETCH_WS = {
        PRODUCTION_ENVIRONMENT: "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl",
    }

    def _convert_xml_to_element_tree(self, xml_str):
        xml_str = xml_str.strip()
        xml_str = xml_str.replace("\n", "").replace("\r", "")

        if xml_str.startswith("<![CDATA["):
            xml_str = xml_str[9:-3]

        try:
            xml_element_tree = ET.fromstring(xml_str)
            return xml_element_tree
        except Exception as e:
            raise UserError(_("Error parseando XML: %s") % str(e))

    def _obtain_or_create_partner(self, ruc, razonSocial):
        partner = self.env["res.partner"].search(
            [("vat", "=", ruc)], limit=1
        )
        if not partner:
            ruc_identification_type = self.env["l10n_latam.identification.type"].search(
                [("name", "=", "RUC")], limit=1
            )
            partner = self.env["res.partner"].create(
                {
                    "name": razonSocial,
                    "l10n_latam_identification_type_id": ruc_identification_type.id if ruc_identification_type else "",
                    "vat": ruc,
                    "supplier_rank": 1,
                }
            )
        return partner

    def _convert_date(self, fecha_text):
        if not fecha_text:
            return False
        try:
            return datetime.strptime(fecha_text, "%d/%m/%Y").date()
        except:
            return False

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

    def _normalize(self, text):
        if not text:
            return ""

        # convertir a minúsculas
        text = text.lower()
        # quitar tildes
        text = unicodedata.normalize("NFD", text)
        text = text.encode("ascii", "ignore").decode("utf-8")
        # quitar caracteres que no son letras o números
        text = re.sub(r"[^a-z0-9]+", "", text)

        return text

    def _obtain_credit_note_type(self, motivo):
        product_return_type = self.env["credit.note.type"].search(
            [("code", "=", 'product_return')], limit=1
        )
        early_payment_type = self.env["credit.note.type"].search(
            [("code", "=", 'early_payment')], limit=1
        )
        discount_type = self.env["credit.note.type"].search(
            [("code", "=", 'discount')], limit=1
        )
        rebate_type = self.env["credit.note.type"].search(
            [("code", "=", 'rebate')], limit=1
        )

        product_return_keywords = [self._normalize(k.keyword) for k in product_return_type.keyword_ids]
        early_payment_keywords = [self._normalize(k.keyword) for k in early_payment_type.keyword_ids]
        discount_keywords = [self._normalize(k.keyword) for k in discount_type.keyword_ids]
        rebate_keywords = [self._normalize(k.keyword) for k in rebate_type.keyword_ids]

        credit_note_type = ""

        if any(k in motivo for k in product_return_keywords):
            credit_note_type = product_return_type
        elif any(k in motivo for k in early_payment_keywords):
            credit_note_type = early_payment_type
        elif any(k in motivo for k in discount_keywords):
            credit_note_type = discount_type
        elif any(k in motivo for k in rebate_keywords):
            credit_note_type = rebate_type

        return credit_note_type

    def _find_purchase_vat_tax(self, tarifa_float):
        Tax = self.env["account.tax"]
        company = self.env.company

        candidates = Tax.search(
            [
                ("active", "=", True),
                ("type_tax_use", "in", ["purchase", "none"]),
                ("amount", "=", tarifa_float),
                ("company_id", "=", company.id),
            ]
        )

        def score(t):
            name = (t.name or "").lower()
            pts = 0
            if "iva" in name:
                pts += 2
            if "inv créd" in name or "inv cred" in name:
                pts += 3
            return pts

        if candidates:
            return max(candidates, key=score).id

        # fallback por nombre
        like = f"%{int(tarifa_float)}%"
        fallback = Tax.search(
            [
                ("active", "=", True),
                ("type_tax_use", "in", ["purchase", "none"]),
                ("name", "ilike", like),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        return fallback.id if fallback else False

    def _obtain_product_lines(self, detalles, flag_credit_note, credit_note_type_code, credit_note_account, second_credit_note_account):
        lines = []

        for d in detalles:
            codigo_interno = (d.findtext("codigoInterno") or "").strip()
            codigo_adicional = (d.findtext("codigoAdicional") or "").strip()
            desc = (d.findtext("descripcion") or "Producto").strip()
            product = ""

            if codigo_interno:
                product = self.env["product.product"].search([
                    ("default_code", "=", codigo_interno),
                    ("detailed_type", "=", "product")
                ], limit=1)
            if not product:
                if codigo_adicional:
                    product = self.env["product.product"].search([
                        ("default_code", "=", codigo_adicional),
                        ("detailed_type", "=", "product")
                    ], limit=1)
            if not product:
                product = self.env["product.product"].search([
                    ("name", "ilike", desc),
                    ("detailed_type", "=", "product")
                ], limit=1)

            qty = float(d.findtext("cantidad", "1") or 1)
            price = float(d.findtext("precioUnitario", "0") or 0)

            # Detectar IVA
            tarifa_str = None
            tarifa = None
            for imp in d.findall(".//impuestos/impuesto"):
                codigo = imp.findtext("codigo", "")
                if codigo == "2":  # IVA
                    tarifa_str = imp.findtext("tarifa")
                    if tarifa_str is None:
                        cp = imp.findtext("codigoPorcentaje", "")
                        mapa = {"0": "0", "2": "12", "5": "15"}
                        tarifa_str = mapa.get(cp, "0")
                    break

            tax_cmd = []
            if tarifa_str:
                tarifa = float(str(tarifa_str).replace(",", "."))
                tax_id = self._find_purchase_vat_tax(tarifa)
                if tax_id:
                    tax_cmd = [(6, 0, [tax_id])]

            lines_vals = {
                "product_id": product.id if product else "",
                "name": desc,
                "quantity": qty,
                "price_unit": price,
                "tax_ids": tax_cmd,
            }

            if flag_credit_note:
                if credit_note_type_code == "product_return":
                    if tarifa == 15:
                        if credit_note_account:
                            lines_vals["account_id"] = credit_note_account.id
                    elif tarifa == 0:
                        if second_credit_note_account:
                            lines_vals["account_id"] = second_credit_note_account.id
                else:
                    if credit_note_account:
                        lines_vals["account_id"] = credit_note_account.id

            lines.append(lines_vals)

        return lines

    def _get_sri_data(self):
        """
        Se ejecuta cuando cambia el campo l10n_ec_authorization_number.
        Consulta el SRI con el número de autorización y actualiza los campos relevantes.
        """
        client = Client(self.SRI_FETCH_WS[2])
        try:
            result = client.service.autorizacionComprobante(
                self.l10n_ec_authorization_number)
            response = []
            if hasattr(result, "numeroComprobantes"):
                number_of_vouchers = int(result.numeroComprobantes)
                if not number_of_vouchers:
                    raise UserError(_("La clave de acceso consultada es incorrecta"))

                data = result.autorizaciones.autorizacion[0]
                xml_str = data.comprobante
                fecha_auth_sri = data.fechaAutorizacion
                xml_element_tree = self._convert_xml_to_element_tree(xml_str)

                tag_name = xml_element_tree.tag.split("}")[-1]

                if self.move_type == 'in_invoice':
                    if tag_name == "factura":
                        #### InfoTributaria ####
                        infoTrib = xml_element_tree.find('.//infoTributaria')
                        if infoTrib is None:
                            raise UserError(_("El XML de la factura no contiene infoTributaria"))
                        razonSocial = infoTrib.findtext('razonSocial') or "Proveedor SRI"
                        ruc = infoTrib.findtext('ruc') or "9999999999"
                        partner = self._obtain_or_create_partner(ruc, razonSocial)
                        estab = infoTrib.findtext('estab', "") or ""
                        ptoEmi = infoTrib.findtext('ptoEmi', "") or ""
                        secuencial = infoTrib.findtext('secuencial', "") or ""
                        invoice_number = f"{estab}-{ptoEmi}-{secuencial}" if estab and ptoEmi and secuencial else ""

                        #### InfoFactura ####
                        infoFactura = xml_element_tree.find('.//infoFactura')
                        if infoFactura is None:
                            raise UserError(_("El XML de la factura no contiene infoFactura"))
                        fecha_emision_txt = infoFactura.findtext('fechaEmision') or ""
                        fecha_emision = self._convert_date(fecha_emision_txt)
                        fecha_autorizacion = self._convert_authorization_date(fecha_auth_sri)

                        #### Detalles ####'
                        detalles = xml_element_tree.findall(".//detalle")
                        lines = self._obtain_product_lines(detalles, False,"", "", "")

                        #### Crear diccionario de respuesta ####
                        response.append({
                            'partner': partner.id,
                            'document_number': invoice_number,
                            'fecha_emision': fecha_emision,
                            'fecha_autorizacion': fecha_autorizacion,
                            'lines': lines
                        })
                    else:
                        raise UserError(_("El numero de autorizacion no corresponde con una factura"))

                if self.move_type == 'in_refund':
                    if tag_name == "notaCredito":
                        #### Info Tributaria ####
                        infoTrib = xml_element_tree.find('.//infoTributaria')
                        if infoTrib is None:
                            raise UserError(_("El XML de la nota de credito no contiene infoTributaria"))
                        razonSocial = infoTrib.findtext('razonSocial') or "Proveedor SRI"
                        ruc = infoTrib.findtext('ruc') or "9999999999"
                        partner = self._obtain_or_create_partner(ruc, razonSocial)
                        estab = infoTrib.findtext('estab', "") or ""
                        ptoEmi = infoTrib.findtext('ptoEmi', "") or ""
                        secuencial = infoTrib.findtext('secuencial', "") or ""
                        credit_note_number = f"{estab}-{ptoEmi}-{secuencial}" if estab and ptoEmi and secuencial else ""

                        #### InfoNotaCredito ####
                        infoNotaCredito = xml_element_tree.find('.//infoNotaCredito')
                        if infoNotaCredito is None:
                            raise UserError(_("El XML de la nota de credito no contiene infoNotaCredito"))
                        fecha_emision_txt = infoNotaCredito.findtext('fechaEmision')
                        fecha_emision = self._convert_date(fecha_emision_txt)
                        fecha_autorizacion = self._convert_authorization_date(fecha_auth_sri)
                        num_doc_mod = infoNotaCredito.findtext("numDocModificado") or ""
                        ref = "Reversión de: Fact " + num_doc_mod
                        fecha_emi_doc_sust_txt = infoNotaCredito.findtext("fechaEmisionDocSustento") or ""
                        fecha_emi_doc_sust = self._convert_date(fecha_emi_doc_sust_txt)
                        credit_note_reason = infoNotaCredito.findtext("motivo") or ""
                        motivo = self._normalize(credit_note_reason)
                        credit_note_type = self._obtain_credit_note_type(motivo)
                        credit_note_type_code = ""
                        credit_note_account = ""
                        second_credit_note_account = ""

                        if credit_note_type:
                            credit_note_type_code = credit_note_type.code
                            credit_note_account = credit_note_type.account_id
                            if credit_note_type_code == "product_return":
                                second_credit_note_account = credit_note_type.second_account_id

                        #### Buscar factura relacionada a la nota de credito ####
                        related_invoice = self.env["account.move"].search([
                            ("move_type", "=", "in_invoice"),
                            ("l10n_latam_document_number", "=", num_doc_mod),
                            ("invoice_date", "=", fecha_emi_doc_sust),
                        ], limit=1)

                        #if not related_invoice:
                        #    raise UserError(_("No se encontró la factura a la cual se le desea aplicar la nota de credito. Primero cree la factura."))

                        related_invoice_partner = related_invoice.partner_id
                        partner_bank_id = related_invoice.partner_bank_id

                        #### Detalles ####'
                        detalles = xml_element_tree.findall(".//detalle")
                        lines = self._obtain_product_lines(detalles, True, credit_note_type_code, credit_note_account, second_credit_note_account)

                        #### Crear diccionario de respuesta
                        response.append({
                            'partner': related_invoice_partner.id or partner.id,
                            'partner_bank': partner_bank_id.id or "",
                            #"partner": partner.id,
                            #'partner_bank': "",
                            'document_number': credit_note_number,
                            'fecha_emision': fecha_emision,
                            'fecha_autorizacion': fecha_autorizacion,
                            'num_doc_mod': num_doc_mod,
                            'ref': ref,
                            "reason": credit_note_reason,
                            "credit_note_type": credit_note_type.id if credit_note_type else "",
                            'reversed_entry_id': related_invoice.id,
                            'lines': lines
                        })
                    else:
                        raise UserError(_("El numero de autorizacion no corresponde con una nota de credito"))
            return response

        except Exception as e:
            raise UserError(_("Problemas al traer el documento electrónico del SRI: ") + str(e))

    def sri_get_information(self):
        if not self.l10n_ec_authorization_number:
            raise UserError(_("Debe ingresar un número de autorización, vuelva a intentarlo."))

        # Validación de longitud de clave de acceso del SRI (49 dígitos)
        clave = self.l10n_ec_authorization_number.strip()
        if len(clave) != 49 or not clave.isdigit():
            raise UserError(_("El numero de autorizacion del SRI debe tener exactamente 49 dígitos numéricos."))

        data = self._get_sri_data()
        if not data:
            raise UserError(_("No se encontraron datos de la autorización en el SRI"))

        if self.move_type == 'in_invoice':
            self.write({
                'partner_id': data[0]['partner'],
                'l10n_latam_document_number': data[0]['document_number'],
                'invoice_date': data[0]['fecha_emision'],
                "l10n_ec_authorization_date": data[0]["fecha_autorizacion"],
                #'date': data[0]['fecha_emision'],
                #'invoice_date_due': data[0]['fecha_emision'],
                'invoice_line_ids': [(5, 0, 0)] + [(0, 0, l) for l in data[0]["lines"]],
                "sri_data_loaded": True,
            })

        elif self.move_type == 'in_refund':
            self.write({
                'partner_id': data[0]['partner'],
                'partner_bank_id': data[0]['partner_bank'],
                'l10n_latam_document_number': data[0]['document_number'],
                'invoice_date': data[0]['fecha_emision'],
                "l10n_ec_authorization_date": data[0]["fecha_autorizacion"],
                #'date': data[0]['fecha_emision'],
                #'invoice_date_due': data[0]['fecha_emision'],
                'ref': data[0]['ref'],
                'reason': data[0]['reason'],
                'credit_note_type': data[0]['credit_note_type'],
                'reversed_entry_id': data[0]['reversed_entry_id'],
                'invoice_line_ids': [(5, 0, 0)] + [(0, 0, l) for l in data[0]["lines"]],
                "sri_data_loaded": True,
            })