# -*- coding: utf-8 -*-
import json
import requests
from datetime import datetime
from odoo import api, fields, models
import logging
import random
from bs4 import BeautifulSoup
import re

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def write(self, vals):
        res = super(AccountMove, self).write(vals)
        for record in self:
            if vals.get('state') == 'posted':
                if record.move_type == 'in_invoice':
                    # Factura de compra
                    record.create_order_in_system_visual(record)
                elif record.move_type == 'in_refund':
                    # Nota de crédito de proveedor
                    record.create_credit_note_in_system_visual(record)
        return res

    def create_order_in_system_visual(self, invoice):
        data = None
        print("=========================")
        line = invoice.line_ids[0]
        purchase_order = line.purchase_line_id.order_id.picking_type_id.warehouse_id.external_id
        # purchase_order = line.invoice_line_ids

        document_number = invoice.l10n_latam_document_number
        provider_id = self.env['res.partner'].search(
            [('id_database_old_provider', '=', invoice.partner_id.id_database_old_provider)], limit=1)
        print(provider_id)
        data_provider = provider_id.provider_config
        print(data_provider)
        if not data_provider:
            raise ValueError(
                f"El proveedor con id_database_old_provider {invoice.partner_id.id_database_old_provider} no tiene 'provider_config'."
            )
        json_string = data_provider.replace("'", '"')
        data_json = json.loads(json_string)

        # series_eployes ={
        #     'id_user':1401,
        #     'serie': ''
        # }
        # print(data_json)
        external_id = str(
            getattr(
                line.purchase_line_id.order_id.picking_type_id.warehouse_id,
                'external_id',
                ''
            ) if line.purchase_line_id and line.purchase_line_id.order_id and
                 line.purchase_line_id.order_id.picking_type_id and
                 line.purchase_line_id.order_id.picking_type_id.warehouse_id
            else ''
        )

        tax_amounts = {
            "ice": 0,
            "irbpnr": 0,
            "iva_15": 0,
            "iva_0": 0
        }

        subtotales_list = invoice.tax_totals.get('groups_by_subtotal', {}).get(
            'Subtotal', [{}])

        tax_name_mapping = {
            "Consumos Especiales (ICE)": "ice",
            "Botellas de plástico (IRBPNR)": "irbpnr",
            "IVA 15%": "iva_15",
            "IVA 0%": "iva_0"
        }

        for tax in subtotales_list:
            tax_name = str(tax.get("tax_group_name", "")).strip()
            tax_amount = tax.get("tax_group_amount", 0)

            if tax_name in tax_name_mapping:
                tax_amounts[tax_name_mapping[tax_name]] = round(tax_amount, 2)
        lines_tax = self.filter_account_move_line_with_tax()
        lines_without_tax = self.filter_account_move_line_without_tax()

        """
        fuente = suma de sobtales 0 y 15% subtotal de la factura
        base imponible = subtotal 0
        baseimgrav = subtotal 15%
        """
        baseImponible = lines_without_tax.get('total_without_tax', 0)
        baseImpGrav = lines_tax.get('total_without_tax', 0)

        order_lines = [{
            "ALIAS": line.product_id.name or "string",
            "DESCUNIT": line.discount or 0,
            "PDESCUNIT": 0,  # kevin preguntar a persona no sabe
            "detalle": line.product_id.name or "string",
            "FECHCADU": invoice.invoice_date.strftime("%Y-%m-%d"),
            "ICE": 0,  # revisar
            "idbodega": external_id,
            "IDITEM": line.product_id.id_database_old or "string",
            "IVA": line.tax_ids[0].amount if line.tax_ids else 0,
            "LINE": str(index + 1),
            "LIVA": self.get_invoice_line_have_iva(line, subtotales_list),
            # si tiene 1 sin0 0
            "LOTE": "LOTE123",
            "NOTEUNIDAD": line.product_uom_id.name or "string",
            "PRICE": line.price_unit or 0,
            "PROMOCION": 0,  # revisar
            "QUANTITY": line.quantity or 0,
            "QUANTITYIN": line.quantity or 0,
            "unidades": 0,
            "uc": '10',
            "IdPODet": 0,  # revisar
            "idlote": "1"
        } for index, line in enumerate(invoice.invoice_line_ids)]

        tax_bases = self._get_tax_bases(invoice)

        data = {
            "po": {
                "IDSUPPLIER": str(invoice.partner_id.id_database_old_provider),
                "address": str(invoice.partner_id.street),
                "IDDEPART": "",
                "INVSUPPLIER": document_number.split('-')[
                    -1] if document_number and isinstance(document_number,
                                                          str) and '-' in document_number else "",
                "IDUSER": str(
                    self.env.user.employee_ids and self.env.user.employee_ids[
                        0].id_employeed_old or ""),
                "RESPONSABLE": str(
                    self.env.user.employee_ids and self.env.user.employee_ids[
                        0].name or ""),
                "IDBODEGA": line.purchase_line_id.order_id.picking_type_id.warehouse_id.external_id,
                "STATE": 0,
                "DATE": invoice.invoice_date.strftime("%Y-%m-%d"),
                "DATEEXP": invoice.invoice_date.strftime("%Y-%m-%d"),
                "DATEIN": invoice.invoice_date.strftime("%Y-%m-%d"),
                "DATERET": invoice.invoice_date.strftime("%Y-%m-%d"),
                "fechaCaducidad": invoice.invoice_date.strftime("%Y-%m-%d"),
                "fechaimpresion": invoice.invoice_date.strftime("%Y-%m-%d"),
                "SUBT0": tax_bases['base_iva_0'],  # Solo base con IVA 0%
                "SUBTX": tax_bases['base_iva_x'],
                "SUBTOTAL": round(invoice.amount_untaxed, 2),
                "TAX": round(invoice.amount_tax, 2),
                "IVA": 0,
                "ICE": tax_amounts["ice"],
                "TOTAL": round(invoice.amount_total, 2),
                "idporet": "",
                "idpo_afec":"",
                "BALANCE": round(invoice.amount_total, 2),
                "PAGOS": 0,  # se queda en 0
                "noretencion": 1,  # se queda en 0
                "TAXPERCENT": 15,  # 15
                "TEXT1": self.normalize_text(invoice.narration),
                "IDPLAN": "",  # revisar
                "CLAVEACCESO": invoice.l10n_ec_authorization_number,
                "tipoComprobante": "01",
                "FRC": invoice.date.strftime("%Y-%m-%d"),
                "NSC": self.extract_prefix(invoice.l10n_latam_document_number),
                "NAC": invoice.l10n_ec_authorization_number,
                "CodSustento": "06",  # --> revisar con jaimme
                "fechaautorizafe": invoice.date.strftime("%Y-%m-%d"),
                "OVERCHARGE": tax_amounts["irbpnr"],
                # tipo de contribuyente
                "RECARGO": 0,
                "srifp": invoice.l10n_ec_sri_payment_id.code or "20"
            },
            "podets": order_lines,
            "poret": {
                "idSupplier": provider_id.id_database_old_provider,
                "tpIdProv": data_json.get('tiporuc'),
                "idProv": data_json.get('RUC'),
                "tipoComprobante": data_json.get('tipoComprobante'),
                "tipoIvaRet": data_json.get('tipoIvaRet'),
                "nsc": data_json.get('Serie'),
                # "secuencial": "000000001",
                "IVA": invoice.amount_tax,  # total de impuestos
                "FUENTE": invoice.amount_untaxed,  # suma de productos con iva pero sin aplciar el iva
                "baseImponible": baseImponible,
                "baseImpGrav": baseImpGrav,  # suma de los que tienen iva sumar las lineas que tiene iva
                "baseNoGraIva": 0.00,  # proeuctos que tienen iva 0 las suma
                "porcentajeIva": "3",
                "montoIva": invoice.amount_tax,  # total de impuestos
                "montoIvaBienes": invoice.amount_tax,
                "porRetBienes": data_json.get('porRetBienes'),
                "nporRetBienes": 0.0,
                "valorRetBienes": invoice.amount_tax * 0.30,  # monto iva bienes * porcentaje bienes
                "montoIvaServicios": 0.00,
                "porRetServicios": 0,
                "nporRetServicios": 0.00,
                "valRetServicios": 0.00,
                "baseImpAir": 0.0,
                "nporcentajeAir": 0.0,
                "valRetAir": 0.0,
                "estabRetencion1": "001",
                "ptoEmiRetencion1": "010",
                "fechaEmiRet1": invoice.date.strftime("%Y-%m-%d"),
                "IDUSER": "1",  # base antigua del usuario viene del emepleado
                "SERIE": "00101007"
            }
        }
        #verificar si existe si no existe crear
        existing_record = self.env['purchase.data'].search([('account_move_id', '=', invoice.id)], limit=1)
        if existing_record:
            existing_record.write({
                'json_data': data,
                'sent': False,
                'active': True,
            })
            return

        self.env['purchase.data'].create({
            'account_move_id': invoice.id,
            'json_data': data,
            'sent': False,
            'active': True,
        })



    def filter_account_move_line_with_tax(self):
        lines_with_tax = self.invoice_line_ids.filtered(
            lambda line: line.tax_ids and any(tax.amount > 0 for tax in line.tax_ids)
        )
        total_without_tax = sum(lines_with_tax.mapped('price_subtotal'))
        total_with_tax = sum(lines_with_tax.mapped('price_total'))
        return {
            'lines': lines_with_tax,
            'total_without_tax': total_without_tax,
            'total_with_tax': total_with_tax
        }

    def filter_account_move_line_without_tax(self):
        lines_with_tax = self.invoice_line_ids.filtered(
            lambda line: line.tax_ids and any(tax.amount == 0 for tax in line.tax_ids)
        )
        total_without_tax = sum(lines_with_tax.mapped('price_subtotal'))
        total_with_tax = sum(lines_with_tax.mapped('price_total'))
        return {
            'lines': lines_with_tax,
            'total_without_tax': total_without_tax,
            'total_with_tax': total_with_tax
        }

    def get_invoice_line_have_iva(self, line, subtotales_list):
        tax_name_mapping_iva = {
            "IVA 15%": "iva_15",
        }

        if not hasattr(line, 'tax_ids') or not line.tax_ids:
            return 0

        for line_tax in line.tax_ids:
            line_tax_group_id = line_tax.tax_group_id.id

            for tax in subtotales_list:
                tax_group_id = int(tax.get('tax_group_id', 0))
                tax_name = str(tax.get('tax_group_name', '')).strip()

                if line_tax_group_id == tax_group_id and tax_name in tax_name_mapping_iva:
                    return 1

        return 0

    def generate_clave_acceso(
            self,
            ruc,
            fecha=None,
            tipo_comprobante="01",
            ambiente="2",
            serie="001003",
            numero_comprobante="000000105",
            tipo_emision="1"
    ):
        """
        Genera una clave de acceso para facturación electrónica en Ecuador.

        :param ruc: str, RUC de 13 dígitos.
        :param fecha: datetime, fecha y hora para la clave (si no se pasa, usa la actual).
        :param tipo_comprobante: str, código del tipo de comprobante (ej. '01' para factura).
        :param ambiente: str, '1' para pruebas, '2' para producción.
        :param serie: str, código de establecimiento (3 dígitos) + punto de emisión (3 dígitos).
        :param numero_comprobante: str, número secuencial de 9 dígitos.
        :param tipo_emision: str, '1' para emisión normal.
        :return: dict, con la clave de acceso en el formato {"CLAVEACCESO": "string"}.
        """
        # Validaciones básicas
        if len(ruc) != 13 or not ruc.isdigit():
            raise ValueError("El RUC debe tener 13 dígitos numéricos.")
        if len(tipo_comprobante) != 2 or not tipo_comprobante.isdigit():
            raise ValueError(
                "El tipo de comprobante debe ser un código de 2 dígitos.")
        if ambiente not in ["1", "2"]:
            raise ValueError(
                "El ambiente debe ser '1' (pruebas) o '2' (producción).")
        if len(serie) != 6 or not serie.isdigit():
            raise ValueError("La serie debe tener 6 dígitos numéricos.")
        if len(numero_comprobante) != 9 or not numero_comprobante.isdigit():
            raise ValueError(
                "El número de comprobante debe tener 9 dígitos numéricos.")
        if tipo_emision != "1":
            raise ValueError("El tipo de emisión debe ser '1'.")

        # Usar fecha actual si no se proporciona
        fecha = fecha or datetime.now()

        # Formato de fecha: DDMMYYYY
        fecha_str = fecha.strftime("%d%m%Y")

        # Generar código numérico aleatorio de 8 dígitos
        codigo_numerico = str(random.randint(0, 99999999)).zfill(8)

        # Concatenar los primeros 48 dígitos
        clave = (
                fecha_str +
                tipo_comprobante +
                ruc +
                ambiente +
                serie +
                numero_comprobante +
                codigo_numerico +
                tipo_emision
        )

        # Calcular dígito verificador (Módulo 11)
        factores = [7, 6, 5, 4, 3, 2] * 8  # Repetir el patrón 7,6,5,4,3,2
        suma = 0
        for i, digito in enumerate(clave):
            suma += int(digito) * factores[i]

        modulo = suma % 11
        digito_verificador = 11 - modulo
        if digito_verificador == 10:
            digito_verificador = 1
        elif digito_verificador == 11:
            digito_verificador = 0

        # Agregar el dígito verificador a la clave
        clave_acceso = clave + str(digito_verificador)

        return clave_acceso

    def normalize_text(self, html_text):
        if not html_text:
            return ""

        soup = BeautifulSoup(html_text, "html.parser")
        clean_text = soup.get_text(separator=" ", strip=True)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        return clean_text

    def extract_prefix(self, string):
        parts = string.rsplit('-', 1)
        if len(parts) > 1:
            resto = parts[0].replace('-', '')
            return resto
        return ''

    def _get_tax_bases(self, invoice):
        """
        Calcula las bases imponibles separadas por tipo de IVA.
        Returns:
            dict: {
                'base_iva_0': float,  # Base con IVA 0%
                'base_iva_x': float,  # Base con IVA > 0% (12%, 15%, etc.)
            }
        """
        base_iva_0 = 0.0
        base_iva_x = 0.0

        tax_totals = invoice.tax_totals or {}
        groups_by_subtotal = tax_totals.get('groups_by_subtotal', {})

        for subtotal_name, groups in groups_by_subtotal.items():
            for group in groups:
                tax_group_name = group.get('tax_group_name', '').upper()
                base_amount = group.get('tax_group_base_amount', 0.0)
                tax_amount = group.get('tax_group_amount', 0.0)

                # Si el impuesto es 0 (IVA 0%, Exento, No objeto, etc.)
                if tax_amount == 0 or 'IVA 0' in tax_group_name or 'EXENTO' in tax_group_name:
                    base_iva_0 += base_amount
                else:
                    # IVA 12%, 15%, o cualquier otro
                    base_iva_x += base_amount

        # También revisar líneas sin impuesto (podría haber productos sin IVA asignado)
        for line in invoice.invoice_line_ids:
            if not line.tax_ids:
                base_iva_0 += line.price_subtotal

        return {
            'base_iva_0': round(base_iva_0, 2),
            'base_iva_x': round(base_iva_x, 2),
        }

    def create_credit_note_in_system_visual(self, credit_note):
        """
        Crea una nota de crédito de proveedor en el sistema externo.
        Se dispara cuando una nota de crédito (in_refund) se publica.
        """
        data = None
        _logger.info(f"Procesando nota de crédito de proveedor: {credit_note.id}")

        # Obtener la línea principal para extraer información del almacén
        line = credit_note.line_ids[0] if credit_note.line_ids else None

        # Obtener el external_id del almacén
        external_id = ''
        if line and line.purchase_line_id:
            warehouse = line.purchase_line_id.order_id.picking_type_id.warehouse_id
            if warehouse:
                external_id = str(warehouse.external_id or '')

        document_number = credit_note.l10n_latam_document_number or ''

        # Buscar el proveedor
        provider_id = self.env['res.partner'].search(
            [('id_database_old_provider', '=', credit_note.partner_id.id_database_old_provider)], limit=1)

        if not provider_id:
            _logger.warning(f"Proveedor no encontrado para nota de crédito {credit_note.id}")
            provider_id = credit_note.partner_id

        data_provider = provider_id.provider_config
        data_json = {}

        if data_provider:
            try:
                json_string = data_provider.replace("'", '"')
                data_json = json.loads(json_string)
            except (json.JSONDecodeError, AttributeError) as e:
                _logger.warning(f"Error parseando provider_config: {e}")

        # Calcular impuestos
        tax_amounts = {
            "ice": 0,
            "irbpnr": 0,
            "iva_15": 0,
            "iva_0": 0
        }

        subtotales_list = credit_note.tax_totals.get('groups_by_subtotal', {}).get(
            'Subtotal', [{}]) if credit_note.tax_totals else [{}]

        tax_name_mapping = {
            "Consumos Especiales (ICE)": "ice",
            "Botellas de plástico (IRBPNR)": "irbpnr",
            "IVA 15%": "iva_15",
            "IVA 0%": "iva_0"
        }

        for tax in subtotales_list:
            tax_name = str(tax.get("tax_group_name", "")).strip()
            tax_amount = tax.get("tax_group_amount", 0)

            if tax_name in tax_name_mapping:
                tax_amounts[tax_name_mapping[tax_name]] = round(tax_amount, 2)

        lines_tax = self.filter_account_move_line_with_tax()
        lines_without_tax = self.filter_account_move_line_without_tax()

        baseImponible = lines_without_tax.get('total_without_tax', 0)
        baseImpGrav = lines_tax.get('total_without_tax', 0)

        # Obtener factura de origen (reversed_entry_id)
        origin_invoice = credit_note.reversed_entry_id
        origin_document_number = ''
        origin_authorization = ''
        idpo_afec = ''  # ID de la factura en el sistema externo

        if origin_invoice:
            origin_document_number = origin_invoice.l10n_latam_document_number or ''
            origin_authorization = origin_invoice.l10n_ec_authorization_number or ''

            # Buscar el invoice_id de la factura origen en purchase.data
            purchase_data_record = self.env['purchase.data'].search([
                ('account_move_id', '=', origin_invoice.id),
                ('sent', '=', True)
            ], limit=1)

            if purchase_data_record and purchase_data_record.invoice_id:
                idpo_afec = purchase_data_record.invoice_id
                _logger.info(f"Encontrado idpo_afect: {idpo_afec} para factura origen {origin_invoice.id}")
            else:
                _logger.warning(f"No se encontró invoice_id sincronizado para la factura origen {origin_invoice.id}")

        # Construir líneas de la nota de crédito
        order_lines = [{
            "ALIAS": line.product_id.name or "string",
            "DESCUNIT": line.discount or 0,
            "PDESCUNIT": 0,
            "detalle": line.product_id.name or "string",
            "FECHCADU": credit_note.invoice_date.strftime("%Y-%m-%d") if credit_note.invoice_date else "",
            "ICE": 0,
            "idbodega": external_id,
            "IDITEM": line.product_id.id_database_old or "string",
            "IVA": line.tax_ids[0].amount if line.tax_ids else 0,
            "LINE": str(index + 1),
            "LIVA": self.get_invoice_line_have_iva(line, subtotales_list),
            "LOTE": "LOTE123",
            "NOTEUNIDAD": line.product_uom_id.name or "string",
            "PRICE": line.price_unit or 0,
            "PROMOCION": 0,
            "QUANTITY": line.quantity or 0,
            "QUANTITYIN": line.quantity or 0,
            "unidades": 0,
            "uc": '10',
            "IdPODet": 0,
            "idlote": "1"
        } for index, line in enumerate(credit_note.invoice_line_ids)]

        # Estructura de datos para nota de crédito (según API Visual)
        tax_bases = self._get_tax_bases(credit_note)
        data = {
            "po": {
                "IDSUPPLIER": str(credit_note.partner_id.id_database_old_provider or ''),
                "address": str(credit_note.partner_id.street or ''),
                "IDDEPART": "",
                "INVSUPPLIER": document_number.split('-')[-1] if document_number and '-' in document_number else document_number,
                "IDUSER": str(
                    self.env.user.employee_ids and self.env.user.employee_ids[0].id_employeed_old or ""),
                "RESPONSABLE": str(
                    self.env.user.employee_ids and self.env.user.employee_ids[0].name or ""),
                "IDBODEGA": external_id,
                "STATE": 0,
                "DATE": credit_note.invoice_date.strftime("%Y-%m-%d") if credit_note.invoice_date else "",
                "DATEEXP": credit_note.invoice_date.strftime("%Y-%m-%d") if credit_note.invoice_date else "",
                "DATEIN": credit_note.invoice_date.strftime("%Y-%m-%d") if credit_note.invoice_date else "",
                "SUBT0": tax_bases['base_iva_0'],  # Solo base con IVA 0%
                "SUBTX": tax_bases['base_iva_x'],
                "SUBTOTAL": round(credit_note.amount_untaxed, 2),
                "TAX": round(credit_note.amount_tax, 2),
                "IVA": round(credit_note.amount_tax, 2),
                "ICE": tax_amounts["ice"],
                "TOTAL": round(credit_note.amount_total, 2),
                "idporet": "",
                "idpo_afec": idpo_afec,
                "BALANCE": round(credit_note.amount_total, 2),
                "PAGOS": 0,
                "DATERET": '2017-08-08',
                "fechaCaducidad": '2017-08-08',
                "fechaimpresion": '2017-08-08',
                "noretencion": 1,
                "TAXPERCENT": 15,
                "TEXT1": credit_note.reason or '',
                "CLAVEACCESO": credit_note.l10n_ec_authorization_number or '',
                "tiponcd": credit_note.credit_note_type.id_database_old if credit_note.credit_note_type and credit_note.credit_note_type.id_database_old else 0,
                "tipoComprobante": "04",
                "FRC": credit_note.date.strftime("%Y-%m-%d") if credit_note.date else "",
                "NSC": self.extract_prefix(credit_note.l10n_latam_document_number or ''),
                "NAC": credit_note.l10n_ec_authorization_number or '',
                "CodSustento": "06",
                "fechaautorizafe": credit_note.date.strftime("%Y-%m-%d") if credit_note.date else "",
                "OVERCHARGE": tax_amounts["irbpnr"],
                "RECARGO": 0,
                "srifp": credit_note.l10n_ec_sri_payment_id.code if credit_note.l10n_ec_sri_payment_id else "20",
            },
            "podets": order_lines,
            "poret": {
                "idSupplier": str(provider_id.id_database_old_provider or ''),
                "tpIdProv": data_json.get('tiporuc', ''),
                "idProv": data_json.get('RUC', ''),
                "tipoComprobante": "04",
                "tipoIvaRet": data_json.get('tipoIvaRet', ''),
                "nsc": data_json.get('Serie', ''),
                "IVA": credit_note.amount_tax,
                "FUENTE": credit_note.amount_untaxed,
                "baseImponible": baseImponible,
                "baseImpGrav": baseImpGrav,
                "baseNoGraIva": 0.00,
                "porcentajeIva": "3",
                "montoIva": credit_note.amount_tax,
                "montoIvaBienes": credit_note.amount_tax,
                "porRetBienes": data_json.get('porRetBienes', 0),
                "nporRetBienes": 0.0,
                "valorRetBienes": credit_note.amount_tax * 0.30,
                "montoIvaServicios": 0.00,
                "porRetServicios": 0,
                "nporRetServicios": 0.00,
                "valRetServicios": 0.00,
                "baseImpAir": 0.0,
                "nporcentajeAir": 0.0,
                "valRetAir": 0.0,
                "estabRetencion1": "001",
                "ptoEmiRetencion1": "010",
                "fechaEmiRet1": credit_note.date.strftime("%Y-%m-%d") if credit_note.date else "",
                "IDUSER": str(self.env.user.employee_ids and self.env.user.employee_ids[0].id_employeed_old or "1"),
                "SERIE": "00101007",
            }
        }

        # Verificar si existe, si no crear
        existing_record = self.env['credit.note.data'].search([
            ('account_move_id', '=', credit_note.id)
        ], limit=1)

        if existing_record:
            existing_record.write({
                'json_data': str(data),
                'sent': False,
                'active': True,
            })
            _logger.info(f"Actualizado registro de nota de crédito existente: {existing_record.id}")
            return

        self.env['credit.note.data'].create({
            'account_move_id': credit_note.id,
            'json_data': str(data),
            'sent': False,
            'active': True,
        })
        _logger.info(f"Creado nuevo registro de nota de crédito para account.move: {credit_note.id}")
