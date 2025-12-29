import base64
import csv
import xml.etree.ElementTree as ET
from odoo import models, fields, _
from odoo.exceptions import UserError

SRI_AUTORIZACION_URL = (
    "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
)


class ImportSRIWizard(models.TransientModel):
    _name = "import.sri.txt.wizard"
    _description = "Importar Facturas SRI desde TXT"

    file = fields.Binary(string="Archivo TXT del SRI", required=True)
    filename = fields.Char(string="Nombre del archivo")

    # ============================================================
    # CONSULTA AL SRI (usa web service oficial)
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
            raise UserError(_("No se encontró autorización para: %s") % access_key)

        autorizacion = autorizaciones.autorizacion[0]

        xml_str = autorizacion.comprobante
        if not xml_str:
            raise UserError(_("El SRI no devolvió XML para: %s") % access_key)

        return xml_str.strip()

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
    # PARSEAR XML DEL SRI
    # ============================================================
    def _parse_invoice_xml(self, xml_str):
        xml_str = xml_str.replace("\n", "").replace("\r", "")
        if xml_str.startswith("<![CDATA["):
            xml_str = xml_str[9:-3]

        try:
            root = ET.fromstring(xml_str)
        except Exception as e:
            raise UserError(_("Error parseando XML: %s") % str(e))

        info_factura = root.find(".//infoFactura")
        if info_factura is None:
            raise UserError(_("El XML no contiene infoFactura"))

        partner_name = info_factura.findtext("razonSocialComprador") or "Proveedor SRI"
        partner_ruc = info_factura.findtext("identificacionComprador") or "9999999999"

        # --------- FECHAS ---------
        fecha_text = info_factura.findtext("fechaEmision") or ""
        fecha_emision = False
        if fecha_text:
            try:
                d, m, y = fecha_text.split("/")
                fecha_emision = f"{y}-{m}-{d}"
            except Exception:
                fecha_emision = False

        # --------- Número documento ---------
        infoTrib = root.find(".//infoTributaria")
        estab = infoTrib.findtext("estab", "") if infoTrib else ""
        ptoEmi = infoTrib.findtext("ptoEmi", "") if infoTrib else ""
        secuencial = infoTrib.findtext("secuencial", "") if infoTrib else ""

        numero_documento = f"{estab}-{ptoEmi}-{secuencial}" if estab and ptoEmi and secuencial else ""

        # --------- Líneas ---------
        detalles = root.findall(".//detalle")
        lines = []

        for d in detalles:
            desc = d.findtext("descripcion") or "Producto"
            qty = float(d.findtext("cantidad", "1") or 1)
            price = float(d.findtext("precioUnitario", "0") or 0)

            tarifa_str = None
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

            lines.append(
                {
                    "name": desc,
                    "quantity": qty,
                    "price_unit": price,
                    "tax_ids": tax_cmd,
                }
            )

        return {
            "partner_name": partner_name,
            "partner_vat": partner_ruc,
            "fecha_emision": fecha_emision,
            "document_number": numero_documento,
            "lines": lines,
        }

    # ============================================================
    # PROCESAR IMPORTACIÓN COMPLETA
    # ============================================================
    def action_import(self):
        if not self.file:
            raise UserError(_("Debe seleccionar un archivo TXT."))

        # ===========================
        # LEER ARCHIVO TSV DEL SRI
        # ===========================
        decoded = base64.b64decode(self.file).decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(decoded.splitlines(), delimiter="\t")

        access_keys = []
        for row in reader:
            clave = (row.get("CLAVE_ACCESO") or "").strip()

            # Validar clave REAL del SRI: 49 dígitos exactos
            if clave.isdigit() and len(clave) == 49:
                access_keys.append(clave)

        if not access_keys:
            raise UserError(_("No se encontraron claves válidas (49 dígitos) en el TXT."))

        moves = self.env["account.move"]

        # ===========================
        # CREAR FACTURAS DESDE XML
        # ===========================
        for key in access_keys:
            try:
                xml_str = self._get_xml_from_sri(key)
                data = self._parse_invoice_xml(xml_str)

                # Buscar o crear proveedor
                partner = self.env["res.partner"].search(
                    [("vat", "=", data["partner_vat"])], limit=1
                )
                if not partner:
                    partner = self.env["res.partner"].create(
                        {
                            "name": data["partner_name"],
                            "vat": data["partner_vat"],
                            "supplier_rank": 1,
                        }
                    )

                # Crear factura borrador
                move = self.env["account.move"].create(
                    {
                        "move_type": "in_invoice",
                        "partner_id": partner.id,

                        # Número de documento
                        "l10n_latam_document_number": data["document_number"],

                        # FECHAS
                        "invoice_date": data["fecha_emision"],
                        "date": data["fecha_emision"],
                        "invoice_date_due": data["fecha_emision"],

                        # Líneas
                        "invoice_line_ids": [(0, 0, l) for l in data["lines"]],
                    }
                )

                moves += move

            except Exception as e:
                raise UserError(_("Error procesando clave %s: %s") % (key, e))

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "tree,form",
            "domain": [("id", "in", moves.ids)],
            "name": _("Facturas importadas del SRI"),
        }
