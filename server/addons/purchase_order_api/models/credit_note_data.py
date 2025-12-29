# -*- coding: utf-8 -*-
import json
import logging
import ast
import requests
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class CreditNoteData(models.Model):
    _name = 'credit.note.data'
    _description = 'Cola de Notas de Crédito de Proveedores'

    account_move_id = fields.Many2one('account.move', string="Nota de Crédito")
    json_data = fields.Text(string="JSON Data")
    sent = fields.Boolean(string="Sent", default=False)
    active = fields.Boolean(string="Active", default=False)
    sync_date = fields.Datetime(string="Sync Date")
    errors = fields.Char(string="Errors")
    credit_note_external_id = fields.Char(string="Credit Note External Id")

    @api.model
    def sync_credit_note_data(self):
        """
        Sincroniza las notas de crédito de proveedores con el sistema externo.
        Este cron se ejecuta después del de facturas de compra.
        """
        # api_url = self.env['ir.config_parameter'].sudo().get_param(
        #     'url_api_create_credit_note_in_system_visual')
        api_url = self.env['ir.config_parameter'].sudo().get_param(
            'url_api_create_order_in_system_visual')

        if not api_url:
            _logger.warning("No se ha configurado la URL para sincronizar notas de crédito (url_api_create_credit_note_in_system_visual)")
            return

        headers = {
            "Content-Type": "application/json",
            'Authorization': 'Bearer ' + 'cuxiloja2025__'
        }

        credit_note_data = self.env['credit.note.data'].search([
            ('active', '=', True),
            ('sent', '=', False)
        ])

        for record in credit_note_data:
            try:
                # 1. Parsear JSON de forma segura (soporta ambos formatos)
                try:
                    data_dict = ast.literal_eval(record.json_data)
                except (ValueError, TypeError) as e:
                    record.errors = f"Error parseando JSON: {str(e)}"
                    _logger.error(f"CreditNote Record {record.id}: Error parseando JSON - {e}")
                    continue

                # 2. Re-buscar idpo_afec antes de enviar
                idpo_afec = data_dict.get('po', {}).get('idpo_afec', '')

                if not idpo_afec:
                    # Intentar obtener el idpo_afec de la factura origen
                    credit_note = record.account_move_id
                    if credit_note and credit_note.reversed_entry_id:
                        purchase_data_record = self.env['purchase.data'].search([
                            ('account_move_id', '=', credit_note.reversed_entry_id.id),
                            ('sent', '=', True)
                        ], limit=1)

                        if purchase_data_record and purchase_data_record.invoice_id:
                            idpo_afec = purchase_data_record.invoice_id
                            # Actualizar el JSON con el idpo_afect encontrado
                            data_dict['po']['idpo_afec'] = idpo_afec
                            record.json_data = str(data_dict)
                            _logger.info(f"CreditNote Record {record.id}: idpo_afect actualizado a {idpo_afec}")

                # 3. Verificar si tiene idpo_afect, si no, omitir este ciclo
                if not idpo_afec:
                    record.errors = "Esperando sincronización de factura origen (idpo_afect vacío)"
                    _logger.info(f"CreditNote Record {record.id}: Omitido - factura origen aún no sincronizada")
                    continue

                # 4. Realizar petición con manejo de excepciones
                try:
                    response = requests.post(
                        api_url,
                        json=data_dict,
                        headers=headers,
                        timeout=30
                    )
                except requests.exceptions.Timeout:
                    record.errors = "Timeout: El servidor no respondió a tiempo"
                    _logger.warning(f"CreditNote Record {record.id}: Timeout en la petición")
                    continue
                except requests.exceptions.ConnectionError:
                    record.errors = "Error de conexión con el servidor"
                    _logger.error(f"CreditNote Record {record.id}: Error de conexión")
                    continue
                except requests.exceptions.RequestException as e:
                    record.errors = f"Error en la petición: {str(e)}"
                    _logger.error(f"CreditNote Record {record.id}: RequestException - {e}")
                    continue

                # 5. Procesar respuesta
                if response.status_code in (200, 201):
                    try:
                        data = response.json()
                    except json.JSONDecodeError:
                        record.errors = f"Respuesta no es JSON válido: {response.text[:200]}"
                        _logger.error(f"CreditNote Record {record.id}: Respuesta no es JSON válido")
                        continue

                    # 6. Extraer ID de forma segura
                    credit_note_id = data.get('po', {}).get('ID')
                    if not credit_note_id:
                        credit_note_id = data.get('ID') or data.get('id')
                    # 4. Extraer ID de forma segura
                    credit_note_id = data.get('po', {}).get('ID')

                    if not credit_note_id:
                        record.errors = f"Respuesta sin ID de Nota de Crédito: {response.text[:200]}"
                        _logger.warning(f"CreditNote Record {record.id}: Respuesta sin ID")
                        continue

                    # 7. Actualizar registro exitoso
                    record.write({
                        'credit_note_external_id': credit_note_id,
                        'sent': True,
                        'sync_date': fields.Datetime.now(),
                        'errors': False,
                    })
                    _logger.info(f"CreditNote Record {record.id}: Sincronizado exitosamente - ID: {credit_note_id}")

                    # 8. Actualizar la factura afectada en Visual
                    self._update_affected_invoice_in_visual(record, idpo_afec, headers)

                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:500]}"
                    record.errors = error_msg
                    _logger.error(f"CreditNote Record {record.id}: {error_msg}")

            except Exception as e:
                record.errors = f"Error inesperado: {str(e)}"
                _logger.exception(f"CreditNote Record {record.id}: Error inesperado")

    def _update_affected_invoice_in_visual(self, record, idpo_afect, headers):
        """
        Actualiza la factura afectada en Visual después de sincronizar la nota de crédito.
        Envía el total de la NC, los pagos y el balance pendiente.
        """
        try:
            # Obtener URL base del parámetro del sistema
            api_url_update = self.env['ir.config_parameter'].sudo().get_param(
                'url_api_update_invoice_in_system_visual')

            if not api_url_update:
                _logger.warning("No se ha configurado url_api_update_invoice_in_system_visual")
                return

            # Construir URL con el idpo_afect
            full_url = f"{api_url_update.rstrip('/')}/{idpo_afect}"

            # Obtener datos de la nota de crédito y factura origen
            credit_note = record.account_move_id
            nc_total = round(credit_note.amount_total, 2)

            # Calcular balance (saldo pendiente de la factura origen)
            balance = 0
            if credit_note.reversed_entry_id:
                origin_invoice = credit_note.reversed_entry_id
                # amount_residual es el saldo pendiente después de aplicar la NC
                balance = round(origin_invoice.amount_residual, 2)

            # Estructura del JSON a enviar
            update_data = {
                "nc": nc_total,
                "pagos": nc_total,
                "balance": balance
            }

            _logger.info(f"Actualizando factura en Visual: {full_url} con datos: {update_data}")

            # Realizar petición PUT
            response = requests.put(
                full_url,
                json=update_data,
                headers=headers,
                timeout=30
            )

            if response.status_code in (200, 201):
                _logger.info(f"Factura {idpo_afect} actualizada exitosamente en Visual")
            else:
                _logger.error(f"Error actualizando factura {idpo_afect}: HTTP {response.status_code} - {response.text[:200]}")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error de conexión actualizando factura {idpo_afect}: {str(e)}")
        except Exception as e:
            _logger.exception(f"Error inesperado actualizando factura {idpo_afect}: {str(e)}")
