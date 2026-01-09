from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class ConsumableMove(models.Model):
    _name = 'allocations.consumable.move'
    _description = 'Movimiento de Consumibles'
    _order = 'date desc, id desc'

    name = fields.Char(string='Referencia', default='Nuevo', copy=False, index=True)
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now, required=True, index=True)

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén destino',
        required=True,
        index=True
    )

    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación (opcional)',
        domain="[('usage', '=', 'internal')]"
    )

    state = fields.Selection(
        [('draft', 'Borrador'), ('done', 'Confirmado')],
        default='draft',
        tracking=True,
        index=True
    )

    status_change = fields.Selection([
        ('created', 'Creado'),
        ('modified', 'Modificado'),
        ('canceled', 'Cancelado'),
    ], default='created', string="Estado de Cambio", tracking=True, index=True)

    line_ids = fields.One2many('allocations.consumable.move.line', 'move_id', string='Líneas')

    sent_to_visual = fields.Boolean(string="Enviado a Visual", default=False)

    def action_cancel(self):
        """
        Cancela el movimiento y revierte todas las asignaciones de stock.
        Restaura las cantidades movidas en las líneas de ingreso.
        """
        for rec in self:
            _logger.info(f"Cancelando movimiento {rec.name} (ID: {rec.id})")

            # Revertir stock de cada línea
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
            _logger.info(f"Movimiento {rec.name} cancelado exitosamente")

    def action_send_visual(self):
        """
        Envía el movimiento al sistema Visual externo.
        Valida que todos los productos tengan ID Visual configurado.
        """
        self.ensure_one()

        _logger.info(f"Iniciando envío de movimiento {self.name} al sistema Visual")

        list_product_transfer = []
        counter_product = 0

        for move in self.line_ids:
            # Validación de ID Visual
            if not move.product_id.id_visual:
                _logger.warning(f"Producto {move.product_id.name} sin ID Visual configurado")
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

        if response and response.status_code in [200, 201]:
            self.sent_to_visual = True
            _logger.info(f"Movimiento {self.name} enviado exitosamente al Visual")
            return {
                "effect": {
                    "fadeout": "slow",
                    "message": "Transferencia enviada correctamente al Sistema Visual",
                    "type": "rainbow_man",
                }
            }
        else:
            error_msg = f"Error al enviar al Visual (código: {response.status_code if response else 'Sin respuesta'})"
            _logger.error(error_msg)
            raise UserError(_(error_msg))

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
        """
        Realiza la petición HTTP al sistema Visual para registrar la transferencia.
        Obtiene la URL y token desde parámetros de configuración del sistema.
        """
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
                "YA": 0,
                "autosync": 0,
                "VOID": 0,
                "idsupplier": "",
                "guiaremision": 0,
            },
            "transferdets": list_product_transfer
        }

        # Obtener configuraciones del sistema
        IrConfigParam = self.env['ir.config_parameter'].sudo()
        url_api_transfer = IrConfigParam.get_param('url_api_create_transfer_in_visual')
        api_token = IrConfigParam.get_param('visual_api_token', 'cuxiloja2025__')

        if not url_api_transfer:
            _logger.error("URL de API Visual no configurada en parámetros del sistema")
            raise UserError(_("La URL del API Visual no está configurada. Contacte al administrador."))

        headers = {
            "Content-Type": "application/json",
            'Authorization': f'Bearer {api_token}'
        }

        try:
            _logger.info(f"Enviando transferencia al Visual: {url_api_transfer}")
            response = requests.post(
                url_api_transfer,
                json=data,
                headers=headers,
                timeout=120
            )

            if response.status_code in [200, 201]:
                _logger.info(f"Transferencia enviada exitosamente al Visual (código: {response.status_code})")
                return response
            else:
                _logger.error(f"Error en Visual - Código: {response.status_code}, Respuesta: {response.text}")
                raise UserError(_(
                    f"Error Visual ({response.status_code}): {response.text}"
                ))

        except requests.exceptions.Timeout:
            _logger.error("Timeout al conectar con Visual API")
            raise UserError(_("Tiempo de espera agotado al conectar con Visual. Intente nuevamente."))
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error de conexión con Visual: {str(e)}")
            raise UserError(_("Error de conexión con Visual: %s") % e)

    def write(self, vals):
        """
        Sobrescribe el método write para:
        - Bloquear modificaciones de registros cancelados
        - Detectar y marcar movimientos confirmados que fueron modificados
        """
        for rec in self:
            # Validar que registros cancelados no puedan modificarse
            if rec.status_change == 'canceled':
                raise UserError(_("Este registro está cancelado y no puede ser modificado."))

            # Detectar campos modificados (excluyendo campos de control)
            campos_modificados = [f for f in vals.keys() if f not in ['state', 'status_change', 'name']]

            # Si el registro ya fue confirmado y se modificó algo real
            if rec.state == 'done' and campos_modificados:
                if rec.status_change == 'created':
                    vals['status_change'] = 'modified'
                    _logger.info(f"Movimiento {rec.name} marcado como modificado")

        return super(ConsumableMove, self).write(vals)

    def unlink(self):
        """
        Sobrescribe unlink para bloquear la eliminación de registros cancelados.
        """
        for rec in self:
            if rec.status_change == 'canceled':
                raise UserError(_("No puedes eliminar un registro cancelado."))
        return super(ConsumableMove, self).unlink()

    def action_confirm(self):
        """
        Confirma el movimiento:
        - Valida que tenga líneas
        - Asigna stock usando FIFO
        - Genera número de secuencia
        """
        for move in self:
            if not move.line_ids:
                raise UserError(_('Debes agregar al menos una línea.'))

            _logger.info(f"Confirmando movimiento {move.name}")

            for line in move.line_ids:
                line._allocate_from_intakes()

            move.state = 'done'
            if move.name == 'Nuevo':
                move.name = self.env['ir.sequence'].next_by_code('allocations.consumable.move') or 'MV-0000'

            _logger.info(f"Movimiento {move.name} confirmado exitosamente")

    def action_print_receipt(self):
        """Genera el reporte PDF del movimiento."""
        return self.env.ref(
            'allocations_consumable_products.action_report_consumable_move_receipt'
        ).report_action(self)


class ConsumableMoveLine(models.Model):
    _name = 'allocations.consumable.move.line'
    _description = 'Línea de Movimiento de Consumibles'
    _order = 'id'

    move_id = fields.Many2one('allocations.consumable.move', string='Movimiento', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('allocations.consumable.products', string='Consumible', required=True, index=True)
    qty_required = fields.Float(string='Cantidad requerida', required=True, default=1.0, digits=(16, 3))
    allocation_note = fields.Text(string='Nota de asignación', readonly=True)
    allocation_ids = fields.One2many('allocations.consumable.move.alloc', 'move_line_id', string='Asignaciones')

    warehouse_id = fields.Many2one(
        related='move_id.warehouse_id',
        string='Destino',
        store=True,
        readonly=True,
        index=True
    )

    move_date = fields.Datetime(
        related='move_id.date',
        string='Fecha movimiento',
        store=True,
        readonly=True,
        index=True
    )

    def unlink(self):
        """
        Revierte las asignaciones de stock antes de eliminar la línea.
        Restaura qty_moved en las líneas de ingreso afectadas.
        """
        for line in self:
            if line.allocation_ids:
                _logger.info(f"Revirtiendo asignaciones de línea de movimiento ID {line.id}")
                for alloc in line.allocation_ids:
                    intake_line = alloc.intake_line_id
                    if intake_line:
                        # Restablecer cantidad movida
                        intake_line.qty_moved -= alloc.qty_taken
                        if intake_line.qty_moved < 0:
                            intake_line.qty_moved = 0
                line.allocation_ids.unlink()
        return super(ConsumableMoveLine, self).unlink()

    def write(self, vals):
        """
        Sobrescribe write para manejar cambios en qty_required de líneas confirmadas.
        Revierte y recalcula asignaciones FIFO cuando cambia la cantidad requerida.
        """
        for line in self:
            if line.move_id.state == 'done' and 'qty_required' in vals:
                new_qty = vals['qty_required']
                old_qty = line.qty_required

                if new_qty != old_qty:
                    _logger.info(f"Modificando cantidad de línea {line.id}: {old_qty} -> {new_qty}")

                    # Revertir asignaciones actuales
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
        """
        Asigna stock desde líneas de ingreso usando método FIFO.
        Busca líneas disponibles ordenadas por fecha de compra y las asigna
        hasta cubrir la cantidad requerida.
        """
        for line in self:
            if line.qty_required <= 0:
                raise UserError(_('La cantidad requerida debe ser mayor a 0.'))

            remaining = line.qty_required
            note_parts = []
            Allocation = self.env['allocations.consumable.move.alloc']

            # FIFO: ordenar por fecha de compra e ID
            candidates = self.env['allocations.consumable.intake.line'].search([
                ('product_id', '=', line.product_id.id),
                ('qty_available', '>', 0),
            ], order='date_purchase asc, id asc')

            _logger.debug(f"Asignando {line.qty_required} unidades de {line.product_id.name}. Candidatos: {len(candidates)}")

            for intake_line in candidates:
                if remaining <= 0:
                    break
                take = min(remaining, intake_line.qty_available)
                if take <= 0:
                    continue

                # Registrar asignación
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
                _logger.warning(f"Stock insuficiente para {line.product_id.name}. Faltan {remaining} unidades")
                raise UserError(_(
                    "No hay stock suficiente de %s. Faltan %s unidades.",
                ) % (line.product_id.display_name, remaining))

            line.allocation_note = ", ".join(note_parts)
            _logger.debug(f"Asignación completada para línea {line.id}")


class ConsumableMoveAllocation(models.Model):
    _name = 'allocations.consumable.move.alloc'
    _description = 'Detalle de Asignación desde Ingresos (FIFO)'

    move_line_id = fields.Many2one(
        'allocations.consumable.move.line',
        string='Línea movimiento',
        required=True,
        ondelete='cascade',
        index=True
    )
    intake_line_id = fields.Many2one(
        'allocations.consumable.intake.line',
        string='Línea de ingreso',
        required=True,
        ondelete='restrict',
        index=True
    )

    qty_taken = fields.Float(string='Cantidad tomada', required=True, digits=(16, 3))
    bill_number = fields.Char(related='intake_line_id.bill_number', store=True, readonly=True)
    date_purchase = fields.Date(related='intake_line_id.date_purchase', store=True, readonly=True)
