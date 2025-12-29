import json

from datetime import timezone, timedelta, datetime

import requests

from odoo import models, fields, api


class JsonStorage(models.Model):
    _name = 'json.storage'
    _description = 'JSON Storage'

    json_data = fields.Text(string='JSON Data', required=False)
    pos_order_id = fields.Many2one(
        'pos.config',
        string='Puntos de Venta',
        help='Seleccione los puntos de venta asociados a esta institución.'
    )
    pos_order = fields.Many2one(
        'pos.order',
        string='Orden de Punto de Venta',
        help='Seleccione la orden de punto de venta asociada a esta institución.'
    )
    employee = fields.Char(string='Dependiente', required=True)
    id_point_of_sale = fields.Char(string='ID Punto de Venta', required=True)

    sync_date = fields.Datetime(string='Sync Date', readonly=False)
    db_key = fields.Char(string='Llave de Base de Datos', readonly=False,
                         required=False)
    sent = fields.Boolean(string='Sincronizado', default=False)
    create_date = fields.Datetime(string='Created On',default=fields.Datetime.now, readonly=False)
    client_invoice = fields.Char(string='Nro.cedula cliente', required=True)
    id_database_old_invoice_client = fields.Char(string='id sis.visual', required=True)
    is_access_key = fields.Boolean(string='Tiene clave de accesso', default=False)



    @api.model
    def update_key_access_to_json_storage(self):
        records = self.search([('is_access_key', '=', False),('sent','=',False)])
        if not records:
            return
        pos_orders = records.mapped('pos_order')
        invoices = self.env['account.move'].sudo().search([
            ('pos_order_ids', 'in', pos_orders.ids),
            ('l10n_ec_authorization_number', '!=', False),
        ])
        invoice_map = {invoice.pos_order_ids.id: invoice for invoice in invoices}
        for record in records:
            invoice = invoice_map.get(record.pos_order.id)

            if not invoice:
                continue
            try:
                l10n_number = self.extract_number_with_dashes(invoice.name)
                # Actualizar pos.order
                record.pos_order.sudo().write({
                    'key_order': invoice.l10n_ec_authorization_number
                })
                # Actualizar json_data
                data = json.loads(record.json_data)
                data[0]["factura"]["pto_emision"] = f"{l10n_number}"
                data[0]["factura"]["claveacceso"] = invoice.l10n_ec_authorization_number
                record.json_data = json.dumps(data,indent=2, ensure_ascii=False)
                # record.json_data = data
                # Marcar como procesado
                record.is_access_key = True

            except Exception as e:
                record.is_access_key = False
                print("Error updating record %s: %s", record.id, e)
        # for record in records:
        #     invoice_id = self.env['account.move'].sudo().search(
        #         [('pos_order_ids', 'in', record.pos_order.id)], limit=1)
        #     if invoice_id.l10n_ec_authorization_number:
        #         try:
        #             order_id =self.env['pos.order'].sudo().browse(record.pos_order.id)
        #             order_id.sudo().write({
        #                 'key_order': invoice_id.l10n_ec_authorization_number
        #             })
        #             data = json.loads(record.json_data)
        #             data[0]["factura"]["claveacceso"] = invoice_id.l10n_ec_authorization_number
        #             record.json_data = data
        #             record.is_access_key = True
        #         except Exception as e:
        #             record.is_access_key = False
        #             print(f"Error updating record {record.id}: {e}")
        #             continue

    def extract_number_with_dashes(self, s):
        import re
        """
        Extrae la primera secuencia de dígitos posiblemente separada por guiones.
        Ej: "Fact 001-200-000001210'" -> "001-200-000001210"
        """
        if not s:
            return ""
        m = re.search(r'(\d+(?:-\d+)*)', s)
        return m.group(1) if m else ""


class JsonStorageNoteCredit(models.Model):
    _name = 'json.note.credit'
    _description = 'JSON Note Credit'

    json_data = fields.Text(string='JSON Data', required=False)
    pos_order_id = fields.Many2one(
        'pos.config',
        string='Puntos de Venta',
        help='Seleccione los puntos de venta asociados a esta institución.'
    )
    id_point_of_sale = fields.Char(string='ID Punto de Venta', required=True)
    sync_date = fields.Datetime(string='Sync Date', readonly=False)
    date_invoices = fields.Char(string='Fecha de la factura', readonly=False,required=False)
    db_key = fields.Char(string='Llave de Base de Datos', readonly=False,
                         required=False)
    sent = fields.Boolean(string='Sincronizado', default=False)
    create_date = fields.Datetime(string='Created On',default=fields.Datetime.now, readonly=False)
    is_access_key = fields.Boolean(string='Tiene clave de accesso', default=False)


class JsonStorageStockRegulation(models.Model):
    _name = 'json.stock.regulation'
    _description = 'JSON Storage Stock Regulation'

    json_data = fields.Char(string='JSON Data', required=False)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén',
                                   required=True)
    laboratory_id = fields.Many2one('product.laboratory', string='Laboratorio',
                                    required=True)
    pos_config_id = fields.Many2one('pos.config', string='Punto de Venta',
                                    required=True)
    id_point_of_sale = fields.Char(string='ID Punto de Venta', required=True)
    create_date = fields.Datetime(string='Created On',
                                  default=fields.Datetime.now, readonly=True)
    sync_date = fields.Datetime(string='Sync Date', readonly=True)
    db_key = fields.Char(string='Llave de Base de Datos', readonly=True,
                         required=False)
    json_formated = fields.Char(string='Json para enviar a la Api-VF', )
    sent = fields.Boolean(string='Sincronizado', default=False)
    sent_to_vf = fields.Boolean(string='Habilitado para enviar a la Api-VF', default=False)
    sync_date_vf = fields.Datetime(string='Sync Date Api-VF')

    @api.model
    def sync_stock_regulation_json_to_vf(self):
        table_name = self.generate_stock_regulation_table_name()
        records = self.search([('sent', '=', True), ('sent_to_vf', '=', True), ])
        for record in records:
            try:
                base_url = self.env['ir.config_parameter'].sudo().get_param(
                    'web.stock.regulation.vf.url')
                url = f"{base_url}/sync_regula_stock/1191751422001/{table_name}"
                headers = {
                    'Content-Type': 'application/json',
                }
                response = requests.post(url, headers=headers, data=record.json_formated)
                if response.status_code == 200:
                    record.sudo().write({'sync_date_vf': fields.Datetime.now()})
            except Exception as e:
                print(f"Error syncing record  to VF: {e}")
                continue

    @api.model
    def generate_stock_regulation_table_name(self, utc_offset_hours: int = -5) -> str:
        """
        Retorna 'regula_stock_YYYYMM' usando la fecha actual con offset UTC-5 por defecto.
        """
        tz = timezone(timedelta(hours=utc_offset_hours))
        now = datetime.now(tz)
        return f"regula_stock_{now.year}{now.month:02d}"


class JsonPosCloseSession(models.Model):
    _name = 'json.pos.close.session'
    _description = 'JSON Pos Close Session'

    json_data = fields.Char(string='JSON Data', required=False)
    pos_session_id = fields.Many2one('pos.session', string='Sesión',
                                     required=True)
    pos_config_id = fields.Many2one('pos.config', string='Punto de Venta',
                                    required=True)
    id_point_of_sale = fields.Char(string='ID Punto de Venta', required=True)

    create_date = fields.Datetime(string='Created On', readonly=True)
    sync_date = fields.Datetime(string='Sync Date', readonly=True)
    db_key = fields.Char(string='Llave de Base de Datos', readonly=True,
                     required=False)
    sent = fields.Boolean(string='Sincronizado', default=False)

class JsonPosTransfers(models.Model):
    _name = 'json.pos.transfers'
    _description = 'JSON Transfers'

    # json_data = fields.Text(string='JSON Data', required=False)
    external_id = fields.Char(string='ID de Bodega Externo', required=True)
    point_of_sale_series = fields.Char(string='Serie punto de venta', required=True)
    stock_picking_id = fields.Many2one('stock.picking', string='Transferencias', required=True)
    sync_date = fields.Datetime(string='Sync Date', readonly=True)
    db_key = fields.Char(string='Llave de Base de Datos', readonly=True,
                     required=False)
    sent = fields.Boolean(string='Sincronizado', default=False)
    employee = fields.Char(string='Dependiente', required=True)
    origin = fields.Char(string='Origen', required=True)
    destin = fields.Char(string='Destino', required=True)


class JsonPosTransfersEdits(models.Model):
    _name = 'json.pos.transfers.edits'
    _description = 'JSON Transfers Edits'

    json_data = fields.Text(string='JSON Data', required=False)
    external_id = fields.Char(string='ID de Bodega Externo', required=True)
    point_of_sale_series = fields.Char(string='Serie punto de venta', required=True)
    stock_picking_id = fields.Many2one('stock.picking', string='Transferencias', required=True)
    sync_date = fields.Datetime(string='Sync Date', readonly=True)
    db_key = fields.Char(string='Llave de Base de Datos', readonly=True,
                     required=False)
    sent = fields.Boolean(string='Sincronizado', default=False)
    employee = fields.Char(string='Dependiente', required=True)
    origin = fields.Char(string='Origen', required=True)
    destin = fields.Char(string='Destino', required=True)

