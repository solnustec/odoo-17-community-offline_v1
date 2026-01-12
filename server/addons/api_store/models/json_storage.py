import json
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class JsonStorage(models.Model):
    _inherit = 'json.storage'

    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        index=True,
        help='Related invoice for this JSON storage record. for app mobile store.',
    )

    @api.model
    def fix_zero_iditem_in_json(self, date_from=None, date_to=None, dry_run=True):
        """
        Corrige los registros donde iditem = 0 en el campo cdet.data del JSON.
        Soporta tanto registros de facturas (invoice_id) como de POS (pos_order).

        Uso desde el shell de Odoo:
            env['json.storage'].fix_zero_iditem_in_json(
                date_from='2025-01-01 00:00:00',
                date_to='2025-01-15 23:59:59',
                dry_run=False
            )

        Uso como acción programada:
            Modelo: json.storage
            Método: fix_zero_iditem_in_json
            Argumentos: [["2025-01-01 00:00:00", null, false]]

        Args:
            date_from: Fecha desde (string 'YYYY-MM-DD HH:MM:SS')
            date_to: Fecha hasta (string 'YYYY-MM-DD HH:MM:SS') o None
            dry_run: Si True, solo reporta sin hacer cambios

        Returns:
            dict con estadísticas
        """
        # Buscar registros que tengan invoice_id O pos_order
        domain = ['|', ('invoice_id', '!=', False), ('pos_order', '!=', False)]
        if date_from:
            domain.append(('create_date', '>=', date_from))
        if date_to:
            domain.append(('create_date', '<=', date_to))

        records = self.sudo().search(domain, order='create_date asc')

        stats = {
            'total_revisados': 0,
            'con_problemas': 0,
            'corregidos': 0,
            'sin_relacion': 0,
            'lineas_no_coinciden': 0,
            'errores': 0,
            'ids_corregidos': [],
            'detalles': []
        }

        _logger.info(
            "Iniciando corrección de iditem. Modo: %s, Registros: %d",
            'DRY-RUN' if dry_run else 'EJECUCIÓN', len(records)
        )

        for record in records:
            stats['total_revisados'] += 1
            try:
                if not record.json_data:
                    continue

                json_data = json.loads(record.json_data)
                if not json_data or not isinstance(json_data, list):
                    continue

                factura_wrapper = json_data[0] if json_data else {}
                factura = factura_wrapper.get('factura', {})
                cdet = factura.get('cdet', {})
                data = cdet.get('data', [])

                if not data:
                    continue

                # Verificar si hay algún iditem = 0
                has_zero = any(
                    isinstance(line, list) and len(line) > 0 and line[0] == 0
                    for line in data
                )
                if not has_zero:
                    continue

                stats['con_problemas'] += 1

                # Obtener líneas del documento relacionado (factura o POS order)
                order_lines = []
                doc_name = ""

                if record.pos_order:
                    # Es un POS order - obtener líneas del pos.order
                    pos_order = record.pos_order
                    doc_name = pos_order.name or f"POS-{pos_order.id}"
                    order_lines = [
                        line for line in pos_order.lines
                        if line.product_id
                        and line.product_id.product_tmpl_id
                        and line.product_id.product_tmpl_id.id_database_old
                        and line.product_id.product_tmpl_id.id_database_old != '-999'
                    ]
                elif record.invoice_id:
                    # Es una factura - obtener líneas de account.move
                    invoice = record.invoice_id
                    doc_name = invoice.name or f"INV-{invoice.id}"
                    order_lines = [
                        line for line in invoice.invoice_line_ids
                        if line.product_id
                        and line.product_id.product_tmpl_id
                        and line.product_id.product_tmpl_id.id_database_old
                        and line.product_id.product_tmpl_id.id_database_old != '-999'
                    ]
                else:
                    stats['sin_relacion'] += 1
                    continue

                if len(order_lines) != len(data):
                    _logger.warning(
                        "Record %d (%s): líneas no coinciden (JSON:%d, Doc:%d)",
                        record.id, doc_name, len(data), len(order_lines)
                    )
                    stats['lineas_no_coinciden'] += 1
                    continue

                # Construir datos corregidos
                new_data = []
                cambios = []

                for idx, (order_line, json_line) in enumerate(zip(order_lines, data)):
                    if not isinstance(json_line, list) or len(json_line) < 7:
                        new_data.append(json_line)
                        continue

                    id_db_old = (
                        order_line.product_id.id_database_old
                        or order_line.product_id.product_tmpl_id.id_database_old
                    )
                    try:
                        correct_iditem = int(id_db_old) if id_db_old else 0
                    except (ValueError, TypeError):
                        correct_iditem = 0

                    if json_line[0] == 0 and correct_iditem != 0:
                        cambios.append({
                            'linea': idx + 1,
                            'producto': order_line.product_id.display_name,
                            'old': 0,
                            'new': correct_iditem
                        })
                        new_data.append([correct_iditem] + json_line[1:])
                    else:
                        new_data.append(json_line)

                if cambios:
                    stats['ids_corregidos'].append(record.id)
                    stats['detalles'].append({
                        'record_id': record.id,
                        'documento': doc_name,
                        'cambios': cambios
                    })

                    if not dry_run:
                        cdet['data'] = new_data
                        factura['cdet'] = cdet
                        factura_wrapper['factura'] = factura
                        json_data[0] = factura_wrapper
                        record.sudo().write({
                            'json_data': json.dumps(json_data, indent=4)
                        })
                        stats['corregidos'] += 1
                        _logger.info(
                            "Corregido record %d (%s) - %d líneas",
                            record.id, doc_name, len(cambios)
                        )

            except Exception as e:
                stats['errores'] += 1
                _logger.error("Error en record %d: %s", record.id, str(e))

        _logger.info(
            "Corrección finalizada. Revisados: %d, Con problemas: %d, "
            "Corregidos: %d, Sin relación: %d, Líneas no coinciden: %d, Errores: %d",
            stats['total_revisados'], stats['con_problemas'],
            stats['corregidos'], stats['sin_relacion'],
            stats['lineas_no_coinciden'], stats['errores']
        )

        return stats
