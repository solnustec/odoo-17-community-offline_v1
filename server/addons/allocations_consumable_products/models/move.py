from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime
import requests
import json
import pytz

class ConsumableMove(models.Model):
    _name = 'allocations.consumable.move'
    _description = 'Movimiento de Consumibles'
    _order = 'date desc, id desc'

    name = fields.Char(string='Referencia', default='Nuevo', copy=False)
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now, required=True)

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén destino',
        required=True
    )

    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación (opcional)',
        domain="[('usage', '=', 'internal')]"
    )

    state = fields.Selection(
        [('draft', 'Borrador'), ('done', 'Confirmado')],
        default='draft',
        tracking=True
    )

    # 🔥 NUEVO CAMPO DE ESTADO DE CAMBIO
    status_change = fields.Selection([
        ('created', 'Creado'),
        ('modified', 'Modificado'),
        ('canceled', 'Cancelado'),
    ], default='created', string="Estado de Cambio", tracking=True)

    line_ids = fields.One2many('allocations.consumable.move.line', 'move_id', string='Líneas')

    sent_to_visual = fields.Boolean(string="Enviado a Visual", default=False)

    # 🔥 Acción para cancelar registro
    def action_cancel(self):
        for rec in self:

            # 🔁 Revertir stock de cada línea
            for line in rec.line_ids:
                for alloc in line.allocation_ids:
                    intake_line = alloc.intake_line_id
                    if intake_line:
                        intake_line.qty_moved -= alloc.qty_taken
                        if intake_line.qty_moved < 0:
                            intake_line.qty_moved = 0

                # Borrar asignaciones
                line.allocation_ids.unlink()

            # Marcar como cancelado
            rec.status_change = 'canceled'

    # 🔥 Acción para enviar al visual
    def action_send_visual(self):
        self.ensure_one()

        # if self.sent_to_visual:
        #     raise UserError(_("Esta transferencia ya fue enviada al sistema Visual."))

        list_product_transfer = []
        counter_product = 0

        for move in self.line_ids:

            # ⚠️ Validación
            if not move.product_id.id_visual:
                raise UserError(
                    _(
                        "No se puede enviar la transferencia.\n\n"
                        "El producto:\n- %s\nno tiene un ID Visual configurado.\n\n"
                        "Solo fundas pueden enviarse al sistema Visual."
                    ) % move.product_id.display_name
                )

            counter_product += 1

            product_data = {
                "externo": "0",
                "idExterno": "0",
                "LINE": str(counter_product),
                "IDITEM": move.product_id.id_visual,
                "QUANTITY": move.qty_required,
                "RECIBIDA": 0,
                "FECHCADU": "2017-08-08",
                "nota": "Transferencia generada por Odoo",
                "YA": 0,
                "idlote": ""
            }

            list_product_transfer.append(product_data)

        response = self.get_products_visual(list_product_transfer)
        self.sent_to_visual = True

        # Mostrar mensaje
        return {
            "effect": {
                "fadeout": "slow",
                "message": "Transferencia enviada correctamente al Sistema Visual",
                "type": "rainbow_man",
            }
        }

    def get_local_time(self, dt):
        """
        Convierte datetime UTC de Odoo a hora local (America/Guayaquil)
        y devuelve HH:MM:SS
        """
        if not dt:
            return None

        dt_local = fields.Datetime.context_timestamp(self, dt)
        return dt_local.strftime("%H:%M:%S")

    def get_products_visual(self, list_product_transfer):
        data = {
            "transfer": {
                "date": self.date.strftime("%Y-%m-%d"),
                "GENERADO": 0,
                "MONEDA": 1,
                "tomardesde": 0,
                "hora": self.get_local_time(self.date),
                "bloqueado": 0,
                "TOTAL": 0,
                "nota": "PAGINA 1",
                "itemseries": 0,
                "TIPOCAMBIO": 1.0,
                "numero": "",
                "idBodFROM": "271",
                "Externo": 0,
                "tipo": 0,
                "responsable": self.create_uid.name,
                "idBodTO": self.warehouse_id.external_id,
                "transito": 0,
                "sync": 0,
                "idUser": self.create_uid.employee_id.id_employeed_old,
                "idIn": "",
                "IdExterno": 0,
                "express": 1,
                "STATE": 1,
                "idOut": "",
                "YA": 0,  # dejarlo en 1 si sale de bodega central
                "autosync": 0,
                "VOID": 0,
                "idsupplier": "",
                "guiaremision": 0,
            },
            "transferdets": list_product_transfer
        }
        url_api_transfer = self.env['ir.config_parameter'].sudo().get_param(
            'url_api_create_transfer_in_visual')

        if not url_api_transfer:
            return


        api_url = url_api_transfer
        headers = {
            "Content-Type": "application/json",
            'Authorization': 'Bearer ' + 'cuxiloja2025__'
        }
        try:
            response = requests.post(api_url, data=json.dumps(data), headers=headers, timeout=5)
            if response.status_code == 200 or response.status_code == 201:
                print("Transferencia enviada correctamente.")
            else:
                print(f"Error en la solicitud: {response.status_code}, {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"Error en la conexión con la API: {e}")
        return data

    # 🔥 Detectar cambios y marcar como "modified"
    def write(self, vals):
        for rec in self:

            # ⛔ Si está cancelado no puede modificarse
            if rec.status_change == 'canceled':
                raise UserError(_("Este registro está cancelado y no puede ser modificado."))

            # --- 🔥 Lógica para marcar como MODIFICADO ---
            campos_modificados = [f for f in vals.keys() if f not in ['state', 'status_change', 'name']]

            # Si el registro ya fue confirmado y se modificó algo real
            if rec.state == 'done' and campos_modificados:
                if rec.status_change == 'created':
                    vals['status_change'] = 'modified'

            # Si está en borrador NO cambiar estado
            # (no hacemos nada)

        return super(ConsumableMove, self).write(vals)

    # ⛔ Bloquear eliminación si está cancelado
    def unlink(self):
        for rec in self:
            if rec.status_change == 'canceled':
                raise UserError(_("No puedes eliminar un registro cancelado."))
        return super(ConsumableMove, self).unlink()

    # Acción original confirm
    def action_confirm(self):
        for move in self:
            if not move.line_ids:
                raise UserError(_('Debes agregar al menos una línea.'))
            for line in move.line_ids:
                line._allocate_from_intakes()
            move.state = 'done'
            if move.name == 'Nuevo':
                move.name = self.env['ir.sequence'].next_by_code('allocations.consumable.move') or 'MV-0000'

    def action_print_receipt(self):
        return self.env.ref(
            'allocations_consumable_products.action_report_consumable_move_receipt'
        ).report_action(self)


class ConsumableMoveLine(models.Model):
    _name = 'allocations.consumable.move.line'
    _description = 'Línea de Movimiento de Consumibles'
    _order = 'id'

    move_id = fields.Many2one('allocations.consumable.move', string='Movimiento', required=True, ondelete='cascade')
    product_id = fields.Many2one('allocations.consumable.products', string='Consumible', required=True)
    qty_required = fields.Float(string='Cantidad requerida', required=True, default=1.0)
    allocation_note = fields.Text(string='Nota de asignación', readonly=True)
    allocation_ids = fields.One2many('allocations.consumable.move.alloc', 'move_line_id', string='Asignaciones')

    warehouse_id = fields.Many2one(
        related='move_id.warehouse_id',
        string='Destino',
        store=True,
        readonly=True
    )

    move_date = fields.Datetime(
        related='move_id.date',
        string='Fecha movimiento',
        store=True,
        readonly=True
    )

    def unlink(self):
        """
        Si la línea tiene asignaciones, se revertirá el stock movido antes de eliminarla.
        """
        for line in self:
            if line.allocation_ids:
                for alloc in line.allocation_ids:
                    intake_line = alloc.intake_line_id
                    if intake_line:
                        # 🔁 Restablecer cantidad movida
                        intake_line.qty_moved -= alloc.qty_taken
                        if intake_line.qty_moved < 0:
                            intake_line.qty_moved = 0
                line.allocation_ids.unlink()
        return super(ConsumableMoveLine, self).unlink()

    def write(self, vals):
        for line in self:
            if line.move_id.state == 'done' and 'qty_required' in vals:
                new_qty = vals['qty_required']
                old_qty = line.qty_required

                if new_qty != old_qty:
                    # 1️⃣ Revertir asignaciones actuales
                    for alloc in line.allocation_ids:
                        intake = alloc.intake_line_id
                        if intake:
                            intake.qty_moved -= alloc.qty_taken
                            if intake.qty_moved < 0:
                                intake.qty_moved = 0
                    line.allocation_ids.unlink()
                    res = super(ConsumableMoveLine, line).write(vals)

                    # Reasignar solo si la nueva cantidad es positiva
                    if new_qty > 0:
                        line._allocate_from_intakes()

                    return res

        # Si no había cambios en qty_required o no estaba confirmado
        return super().write(vals)

    def _allocate_from_intakes(self):
        for line in self:
            if line.qty_required <= 0:
                raise UserError(_('La cantidad requerida debe ser mayor a 0.'))

            remaining = line.qty_required
            note_parts = []
            Allocation = self.env['allocations.consumable.move.alloc']

            # FIFO por fecha de compra e ID
            candidates = self.env['allocations.consumable.intake.line'].search([
                ('product_id', '=', line.product_id.id),
                ('qty_available', '>', 0),
            ], order='date_purchase asc, id asc')

            for intake_line in candidates:
                if remaining <= 0:
                    break
                take = min(remaining, intake_line.qty_available)
                if take <= 0:
                    continue

                # registrar asignación
                Allocation.create({
                    'move_line_id': line.id,
                    'intake_line_id': intake_line.id,
                    'qty_taken': take,
                })

                intake_line.qty_moved += take

                price = f"{intake_line.unit_cost:.2f}" if intake_line.unit_cost else "0.00"
                note_parts.append(
                    f"Cantidad: {take:g} de factura {intake_line.bill_number or '-'} (USD {price})"
                )

                remaining -= take

            if remaining > 0:
                raise UserError(_(
                    "No hay stock suficiente de %s. Faltan %s unidades.",
                ) % (line.product_id.display_name, remaining))

            line.allocation_note = ", ".join(note_parts)


class ConsumableMoveAllocation(models.Model):
    _name = 'allocations.consumable.move.alloc'
    _description = 'Detalle de Asignación desde Ingresos (FIFO)'

    move_line_id = fields.Many2one('allocations.consumable.move.line', string='Línea movimiento', required=True,
                                   ondelete='cascade')
    intake_line_id = fields.Many2one('allocations.consumable.intake.line', string='Línea de ingreso', required=True,
                                     ondelete='restrict')

    qty_taken = fields.Float(string='Cantidad tomada', required=True)
    bill_number = fields.Char(related='intake_line_id.bill_number', store=True, readonly=True)
    date_purchase = fields.Date(related='intake_line_id.date_purchase', store=True, readonly=True)
