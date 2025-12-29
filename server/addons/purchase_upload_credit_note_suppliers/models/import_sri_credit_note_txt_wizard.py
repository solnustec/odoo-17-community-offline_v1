import base64
import csv
from odoo import models, fields, _
from odoo.exceptions import UserError
import xml.etree.ElementTree as ET
from datetime import datetime, date
import unicodedata
import re

SRI_AUTORIZACION_URL = (
    "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
)


class ImportSRICreditNoteWizard(models.TransientModel):
    _name = "import.sri.credit.note.txt.wizard"
    _description = "Importar Notas de Crédito SRI desde TXT"

    file = fields.Binary(string="Archivo TXT del SRI", required=True)
    filename = fields.Char(string="Nombre del archivo")

    # ============================================================
    # CONSULTAR AL SRI Y OBTENER XML
    # ============================================================
    def _get_xml_from_sri(self, access_key):
        try:
            import zeep
        except ImportError:
            raise UserError(_("Falta 'zeep'. Instálalo con: pip install zeep"))

        client = zeep.Client(SRI_AUTORIZACION_URL)
        result = client.service.autorizacionComprobante(access_key)

        autorizaciones = getattr(result, "autorizaciones", None)
        if not autorizaciones or not autorizaciones.autorizacion:
            raise UserError(_("No se encontró autorización para la clave: %s") % access_key)

        autorizacion = autorizaciones.autorizacion[0]

        xml_str = autorizacion.comprobante
        fecha_auth_sri = autorizacion.fechaAutorizacion

        if not xml_str:
            raise UserError(_("El SRI no devolvió XML para la clave %s") % access_key)

        return xml_str, fecha_auth_sri

    # ============================================================
    # CONVERTIR XML A ELEMENT TREE
    # ============================================================
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

    # ============================================================
    # OBTENER O CREAR PARTNER
    # ============================================================
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

    # ============================================================
    # CONVERSION A FECHA (DATE) CUANDO ES TEXTO
    # ============================================================
    def _convert_date(self, fecha_text):
        if not fecha_text:
            return False
        try:
            return datetime.strptime(fecha_text, "%d/%m/%Y").date()
        except:
            return False

    # ============================================================
    # CONVERSION A FECHA (DATE) PARA LA FECHA DE AUTORIZACION
    # ============================================================
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

    # ============================================================
    # NORMALIZAR TEXTO
    # ============================================================
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

    # ============================================================
    # OBTENER TIPO DE NOTA DE CREDITO
    # ============================================================
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

    # ============================================================
    # BUSCAR IMPUESTO IVA EN ODOO
    # ============================================================
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

    # ============================================================
    # OBTENER LINEAS PARA CADA PRODUCTO
    # ============================================================
    def _obtain_product_lines(self, detalles, credit_note_type_code, credit_note_account, second_credit_note_account):
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
                tarifa = float(tarifa_str.replace(",", "."))
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

    # ============================================================
    # PARSEAR XML DE NOTA DE CRÉDITO DEL SRI
    # ============================================================
    def _parse_credit_note_xml(self, xml_element_tree, fecha_auth_sri):
        # --- Obtener tag ---
        tag_name = xml_element_tree.tag.split("}")[-1]
        if tag_name != "notaCredito":
            raise UserError(_("El XML no corresponde a una Nota de Crédito del SRI."))

        # --- infoTributaria ---
        infoTrib = xml_element_tree.find(".//infoTributaria")
        if infoTrib is None:
            raise UserError(_("El XML no contiene infoTributaria"))

        razonSocial = infoTrib.findtext("razonSocial") or "Proveedor SRI"
        ruc = infoTrib.findtext("ruc") or "9999999999"
        partner = self._obtain_or_create_partner(ruc, razonSocial)

        access_key = infoTrib.findtext("claveAcceso")
        estab = infoTrib.findtext("estab") or ""
        ptoEmi = infoTrib.findtext("ptoEmi") or ""
        secuencial = infoTrib.findtext("secuencial") or ""

        credit_note_number = f"{estab}-{ptoEmi}-{secuencial}" if estab and ptoEmi and secuencial else ""

        # --- infoNotaCredito ---
        infoNC = xml_element_tree.find(".//infoNotaCredito")
        if infoNC is None:
            raise UserError(_("El XML no contiene infoNotaCredito"))

        # Número de documento modificado (factura original)
        num_doc_mod = infoNC.findtext("numDocModificado") or ""

        # Referencia
        ref = "Reversión de: Fact " + num_doc_mod

        # Fecha de emision del documento modificado (factura original)
        fecha_emi_doc_sust_txt = infoNC.findtext("fechaEmisionDocSustento") or ""
        fecha_emi_doc_sust = self._convert_date(fecha_emi_doc_sust_txt)

        # Fecha de emision de la nota de credito
        fecha_text = infoNC.findtext("fechaEmision") or ""
        fecha_emision = self._convert_date(fecha_text)

        # Fecha de autorizacion de la nota de credito
        fecha_autorizacion = self._convert_authorization_date(fecha_auth_sri)

        # Motivo y Tipo de nota de credito
        credit_note_reason = infoNC.findtext("motivo") or ""
        motivo = self._normalize(credit_note_reason)
        credit_note_type = self._obtain_credit_note_type(motivo)

        # Codigo y cuentas de la nota de credito de acuerdo al tipo
        credit_note_type_code = ""
        credit_note_account = ""
        second_credit_note_account = ""

        if credit_note_type:
            credit_note_type_code = credit_note_type.code
            credit_note_account = credit_note_type.account_id
            if credit_note_type_code == "product_return":
                second_credit_note_account = credit_note_type.second_account_id

        # --- Buscar factura relacionada a la nota de credito ---
        related_invoice = self.env["account.move"].search([
            ("move_type", "=", "in_invoice"),
            ("l10n_latam_document_number", "=", num_doc_mod),
            ("invoice_date", "=", fecha_emi_doc_sust),
        ], limit=1)

        #if not related_invoice:
        #    raise UserError(_("No se encontró la factura a la cual se le desea aplicar la nota de credito. Primero cree la factura."))

        related_invoice_partner = related_invoice.partner_id
        partner_bank_id = related_invoice.partner_bank_id

        # --- Detalles ---
        detalles = xml_element_tree.findall(".//detalle")
        lines = self._obtain_product_lines(detalles, credit_note_type_code, credit_note_account, second_credit_note_account)

        return {
            "access_key": access_key,
            "partner": related_invoice_partner.id or partner.id,
            'partner_bank': partner_bank_id.id or "",
            #"partner": partner.id,
            #'partner_bank': "",
            "document_number": credit_note_number,
            "fecha_emision": fecha_emision,
            "fecha_autorizacion": fecha_autorizacion,
            "num_doc_mod": num_doc_mod,
            "ref": ref,
            "reason": credit_note_reason,
            "credit_note_type": credit_note_type.id if credit_note_type else "",
            'reversed_entry_id': related_invoice.id,
            "lines": lines,
        }

    # ============================================================
    # IMPORTAR NOTAS DE CRÉDITO
    # ============================================================
    def action_import(self):
        if not self.file:
            raise UserError(_("Debe seleccionar un archivo TXT."))

        # Leer Archivo TSV del SRI
        decoded = base64.b64decode(self.file).decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(decoded.splitlines(), delimiter="\t")

        access_keys = []
        for row in reader:
            clave = (row.get("CLAVE_ACCESO") or "").strip()

            # Validar clave REAL del SRI: 49 dígitos exactos
            if clave.isdigit() and len(clave) == 49:
                access_keys.append(clave)

        if not access_keys:
            raise UserError(_("No se encontraron claves de acceso válidas (49 dígitos) en el TXT."))

        moves = self.env["account.move"]

        # Crear Notas de credito desde el XML
        for key in access_keys:
            try:
                xml_str, fecha_auth_sri = self._get_xml_from_sri(key)
                xml_element_tree = self._convert_xml_to_element_tree(xml_str)
                data = self._parse_credit_note_xml(xml_element_tree, fecha_auth_sri)

                # Crear nota de credito en borrador
                move = self.env["account.move"].create(
                    {
                        # Tipo de documento (Nota de credito de proveedores)
                        "move_type": "in_refund",

                        # Clave de acceso
                        "l10n_ec_authorization_number": data["access_key"],

                        # Proveedor
                        "partner_id": data["partner"],

                        # Banco del proveedor
                        "partner_bank_id": data["partner_bank"],

                        # Número de documento
                        "l10n_latam_document_number": data["document_number"],

                        # Fechas
                        "invoice_date": data["fecha_emision"],
                        "l10n_ec_authorization_date": data["fecha_autorizacion"],
                        #"date": data["fecha_emision"],
                        #"invoice_date_due": data["fecha_emision"],

                        # Referencia
                        "ref": data["ref"],

                        # Motivo de la nota de credito
                        "reason": data["reason"],

                        # Tipo de nota de credito
                        "credit_note_type": data["credit_note_type"],

                        # Relacionar nota de credito con factura
                        "reversed_entry_id": data["reversed_entry_id"],

                        # Lineas
                        "invoice_line_ids": [(0, 0, l) for l in data["lines"]],

                        # Flag para saber si la nota se ha importado desde txt
                        "sri_data_loaded": True,
                    }
                )

                moves += move

            except Exception as e:
                raise UserError(_("Error procesando la nota de credito que se desea importar con clave %s: %s") % (key, e))

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            #"view_mode": "tree,form",
            #"view_id": self.env.ref("account.view_in_invoice_refund_tree").id,
            "views": [
                (self.env.ref("account.view_in_invoice_refund_tree").id, "tree"),
                (self.env.ref("account.view_move_form").id, "form"),
            ],
            "domain": [("id", "in", moves.ids)],
            "name": _("Notas de Crédito importadas del SRI"),
        }