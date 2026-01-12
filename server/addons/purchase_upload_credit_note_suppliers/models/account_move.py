from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from markupsafe import Markup


class AccountMove(models.Model):
    _inherit = 'account.move'

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        help='Almacén/Bodega asociada a la nota de crédito'
    )

    stock_picking_id = fields.Many2one(
        'stock.picking',
        string='Devolución de inventario',
        readonly=True,
        copy=False
    )

    l10n_ec_authorization_date = fields.Date(
        string="Fecha de autorización SRI",
        copy=False
    )

    reason = fields.Text(
        string="Motivo",
        store = True,
        help="Motivo o razón por la cual se emitió la nota de crédito."
    )

    credit_note_type = fields.Many2one(
        'credit.note.type',
        string="Tipo de nota de crédito",
        help="Tipo de nota de crédito de acuerdo al motivo"
    )

    sri_data_loaded = fields.Boolean(
        string="Datos cargados desde el SRI",
        default=False,
        copy=False,
        help="Campo para identificar si la factura/nota de crédito fue importada desde el SRI. Cuando esta activado (True) no se permite modificar el proveedor."
    )

    def _check_credit_note_amount_vs_invoice_balance(self):
        for move in self:
            if move.move_type != 'in_refund':
                continue

            if not move.reversed_entry_id:
                continue

            invoice = move.reversed_entry_id
            if invoice.state != 'posted':
                continue

            currency = invoice.currency_id
            #rounding = currency.rounding  # normalmente 0.01

            # Monto de la NC (redondeado)
            credit_amount = currency.round(abs(move.amount_total))

            # NC posteadas (excluyendo la actual)
            posted_refunds = self.env['account.move'].search([
                ('move_type', '=', 'in_refund'),
                ('reversed_entry_id', '=', invoice.id),
                ('state', '=', 'posted'),
                ('id', '!=', move.id),
            ])

            credited_amount = sum(
                currency.round(abs(r.amount_total))
                for r in posted_refunds
            )

            real_residual = currency.round(
                abs(invoice.amount_total) - credited_amount
            )

            # ----------------------------------------
            # COMPARACIÓN CON TOLERANCIA CONTABLE
            # ----------------------------------------
            #if credit_amount > real_residual + rounding:
            if credit_amount > real_residual:
                raise ValidationError(_(
                    "No se puede confirmar la Nota de Crédito.\n\n"
                    "El valor de la nota de crédito (%.2f) "
                    "supera el saldo pendiente de la factura (%.2f)."
                ) % (credit_amount, real_residual))

    @api.onchange('credit_note_type')
    def _onchange_credit_note_type(self):
        for line in self.invoice_line_ids:
            line._apply_credit_note_account_rules(True)

    #@api.onchange('reversed_entry_id')
    #def _onchange_reversed_entry_id(self):
    #    invoice_number = self.reversed_entry_id.l10n_latam_document_number
    #    if invoice_number:
    #        self.ref = "Reversión de: Fact " + invoice_number

    def _create_stock_return_from_credit_note(self):
        self.ensure_one()
        # ---------------------------------------------------------
        # PASO 1: Validaciones básicas y factura original
        # ---------------------------------------------------------
        # picking = self.stock_picking_id
        # if picking:
        #     self.message_post(
        #         body=Markup(
        #             _(
        #                 "La devolución de inventario "
        #                 "<a href='/web#id=%s&model=stock.picking&view_type=form'>"
        #                 "<b>%s</b></a> ya fue creada previamente."
        #             ) % (
        #                 picking.id,
        #                 picking.name,
        #             )
        #         )
        #     )
        #     return

        # Solo aplica para notas de credito de proveedores
        if self.move_type != 'in_refund':
            return

        # Verificar si la nota de credito tiene almacen/bodega seleccionada
        if not self.warehouse_id:
            return

        # Verificar si la nota de credito tiene factura seleccionada
        if not self.reversed_entry_id:
            raise UserError(_("Debe seleccionar la factura a la cual se le aplica la nota de credito"))

        invoice = self.reversed_entry_id

        # Verificar si la factura de la nota de credito esta publicada
        if invoice.state != 'posted':
            raise UserError(_("La factura de la nota de credito (%s) debe estar en estado Publicado.") % (invoice.name or invoice.id))

        # ---------------------------------------------------------
        # PASO 2: Obtener Orden de Compra desde la factura
        # ---------------------------------------------------------
        purchase_orders = invoice.invoice_line_ids.mapped('purchase_order_id').filtered(lambda po: po)

        if not purchase_orders:
            raise UserError(_("No se encontró una Orden de Compra asociada a la factura de la nota de credito (%s).\n") % (invoice.name or invoice.id))

        # Se selecciona la primera orden de compra
        po = purchase_orders[0]

        # ------------------------------------------------------------------------
        # PASO 3: Obtener recepción (stock.picking) desde la Orden de Compra (OC)
        # ------------------------------------------------------------------------
        if not po.picking_ids:
            raise UserError(_("La Orden de Compra no tiene recepciones asociadas.") % (po.name))

        pickings = po.picking_ids.filtered(
            lambda p: (
                    p.state == 'done'
                    and p.picking_type_id.code == 'incoming'
                    and p.location_id.usage != 'internal'
            )
        ).sorted('date_done')

        if not pickings:
            raise UserError(_("La Orden de Compra %s no tiene recepciones de tipo Recepcion en estado Confirmado") % (po.name))

        picking = pickings[0]

        # ---------------------------------------------------------
        # PASO 4: Crear wizard estándar de devolución
        # ---------------------------------------------------------
        wizard = self.env['stock.return.picking'].with_context(
            active_id=picking.id,
            active_ids=[picking.id],
            active_model='stock.picking',
        ).create({})

        if not wizard.product_return_moves:
            raise UserError(_(
                "El wizard de devolución no generó líneas.\n\n"
                "Orden de Compra: %s\n"
                "Recepción: %s\n\n"
                "Esto suele ocurrir si Odoo considera que no hay cantidades que se pueden devolver"
                "(por devoluciones previas) o si el picking no corresponde al producto."
            ) % (po.name, picking.name))

        warehouse = self.warehouse_id

        # Si el almacen es Bodega Matilde se coloca como ubicacion a Proveedores, caso contrario se asigna la ubicacion del almacen
        if warehouse.code == "BODMA":
            partner_location = self.env['stock.location'].search(
                [
                    ('usage', '=', 'supplier'),
                    ('name', '=', 'Vendors'),
                    ('location_id.name', '=', 'Partners'),
                ],
                limit=1
            )

            if not partner_location:
                raise UserError(_(
                    "No se encontró la ubicación de proveedor 'Partners / Vendors'.\n\n"
                    "Esta ubicación es obligatoria para devoluciones desde el almacén Bodega Matilde (BODMA).\n"
                    "Verifique la configuración de inventario."
                ))

            location = partner_location
        else:
            location = warehouse.lot_stock_id

        wizard.write({
            'warehouse_id': warehouse.id,
            'location_id': location.id,
        })

        # ---------------------------------------------------------
        # PASO 5: Validación de líneas de Nota de Crédito
        # ---------------------------------------------------------
        all_lines = self.invoice_line_ids

        invalid_qty_lines = all_lines.filtered(lambda l: l.quantity <= 0)

        if invalid_qty_lines:
            error_lines = "\n".join([
                f"- Línea {l.name or l.id} | Cantidad: {l.quantity}"
                for l in invalid_qty_lines
            ])
            raise UserError(_(
                "Todas las líneas de la Nota de Crédito deben tener cantidad mayor a cero.\n\n"
                "Las siguientes líneas no cumplen esta condición:\n%s"
            ) % error_lines)

        nc_lines = all_lines

        lines_with_product = nc_lines.filtered(lambda l: l.product_id)
        lines_without_product = nc_lines.filtered(lambda l: not l.product_id)

        # Ninguna línea tiene producto → NC contable, no hay devolución
        if not lines_with_product:
            self.message_post(
                body=Markup(
                    _("Esta Nota de Crédito no contiene productos.<br/>"
                      "No se genera devolución de inventario.")
                )
            )
            return

        # Mezcla de líneas con y sin producto → ERROR
        if lines_with_product and lines_without_product:
            error_lines = "\n".join([
                f"- Línea {l.name or l.id} | Cantidad: {l.quantity}"
                for l in lines_without_product
            ])
            raise UserError(_(
                "La Nota de Crédito contiene líneas sin producto y líneas con producto.\n\n"
                "Todas las líneas deben tener producto para realizar una devolución de stock.\n\n"
                "Líneas sin producto:\n%s"
            ) % error_lines)

        # ---------------------------------------------------------
        # PASO 6: Validación de productos contra el wizard (product_id)
        # ---------------------------------------------------------
        credit_note_products = lines_with_product.mapped('product_id')
        wizard_products = wizard.product_return_moves.mapped('product_id')

        invalid_products = credit_note_products - wizard_products
        if invalid_products:
            invalid_names = "\n".join([f"- {t.display_name}" for t in invalid_products])
            raise UserError(_(
                "No se puede realizar la devolución.\n\n"
                "Hay productos en la Nota de Crédito que no pertenecen a la recepción seleccionada:\n%s"
            ) % invalid_names)

        # ---------------------------------------------------------
        # PASO 7: Ajustar cantidades del wizard desde la NC (por TEMPLATE)
        # ---------------------------------------------------------
        for return_line in wizard.product_return_moves:
            matched_nc_lines = lines_with_product.filtered(
                lambda l: l.product_id == return_line.product_id
            )
            nc_qty = sum(matched_nc_lines.mapped('quantity'))

            if nc_qty > 0:
                return_line.quantity = nc_qty
            else:
                return_line.unlink()

        if not wizard.product_return_moves:
            raise UserError(_(
                "Después de ajustar cantidades, no quedaron líneas en el wizard.\n"
                "Revise que las cantidades de la Nota de Crédito sean > 0 y correspondan al picking."
            ))

        # ---------------------------------------------------------
        # PASO 8: Ejecutar devolución y obtener picking retornado
        # ---------------------------------------------------------
        res = wizard.create_returns()
        picking_return = self.env['stock.picking'].browse(res.get('res_id'))

        if not picking_return:
            raise UserError(_("No se pudo crear el picking de devolución."))

        # ---------------------------------------------------------
        # PASO 9: Validar picking automáticamente
        # ---------------------------------------------------------
        # Confirmar:
        # Pasar de borrador a confirmado
        # Crear movimientos de stock (stock.move)
        picking_return.action_confirm()

        # Asignar/Reservar:
        # Reserva el stock necesario, verifica que hay stock disponible
        # Crea las líneas detalladas (stock.move.line), asigna lotes y ubicaciones específicas
        picking_return.action_assign()

        # Validar/Ejecutar:
        # Cambia estado a completado, ejecuta fisicamente los movimientos de stock
        # Actualiza las cantiades en ubicaciones, mueve el stock del origen al destino
        picking_return.button_validate()

        # ---------------------------------------------------------
        # PASO 10: Enlazar devolución y mostrar mensaje
        # ---------------------------------------------------------
        self.stock_picking_id = picking_return.id

        # Nombre del almacen
        warehouse_name = self.warehouse_id.display_name

        self.message_post(
            body=Markup(
                _(
                "✅ Se creó y validó la devolución de inventario:<br/>"
                "• <b>Recepción original:</b> "
                "<a href='/web#id=%s&model=stock.picking&view_type=form'>%s</a> "
                "(%s → %s)<br/>"
                "• <b>Devolución:</b> "
                "<a href='/web#id=%s&model=stock.picking&view_type=form'>%s</a> "
                "(%s → %s)<br/>"
                "• <b>Almacén de destino:</b> %s<br/>"
                "• <b>Ubicación de destino:</b> %s<br/><br/>"
                "Los productos han sido devueltos a la ubicación de destino<br/>"
                ) % (
                    picking.id, picking.name,
                    picking.location_id.display_name,
                    picking.location_dest_id.display_name,
                    picking_return.id, picking_return.name,
                    picking_return.location_id.display_name,
                    picking_return.location_dest_id.display_name,
                    warehouse_name,
                    location.display_name,
                )
            )
        )

    def action_post(self):
        for move in self:
            # ----------------------------------------
            # VALIDACIONES (ANTES de postear)
            # ----------------------------------------

            # Validar el ingreso de la factura al confirmar la nota de credito de proveedores
            if move.move_type == 'in_refund' and not move.reversed_entry_id:
                raise UserError(_("Debe seleccionar la factura antes de confirmar"))

            # Almacén obligatorio para NC de proveedor
            if move.move_type == 'in_refund' and not move.warehouse_id:
                raise UserError(_("Debe ingresar el almacén/bodega antes de confirmar"))

            # Fecha de autorización obligatoria
            if move.move_type in ['in_invoice', 'in_refund'] and not move.l10n_ec_authorization_date:
                raise UserError(_("Debe ingresar la fecha de autorización antes de confirmar"))

            # Validación de monto NC vs factura
            if move.move_type == 'in_refund':
                move._check_credit_note_amount_vs_invoice_balance()

        # ----------------------------------------
        # POSTEO REAL
        # ----------------------------------------
        res = super().action_post()

        # ----------------------------------------
        # ACCIONES POST-POSTEO
        # ----------------------------------------
        for move in self:
            if move.move_type == 'in_refund':
                move._create_stock_return_from_credit_note()

        return res

    def button_draft(self):
        for move in self:
            # ---------------------------------------------------------
            # PASO 1: Validaciones básicas
            # ---------------------------------------------------------
            # Solo aplica para notas de crédito de proveedores
            if move.move_type != 'in_refund':
                continue

            # ------------------------------------------------------------------------
            # PASO 2: Obtener devolución (stock.picking) desde la Nota de crédito
            # ------------------------------------------------------------------------
            # Verificar si tiene devolución asociada
            picking = move.stock_picking_id
            if not picking:
                continue

            # Verificar que el picking existe
            if not picking.exists():
                move.stock_picking_id = False
                continue

            # Solo revertir si la devolución está validada
            if picking.state != 'done':
                # Si no está validada, simplemente cancelarla
                if picking.state not in ('cancel', 'draft'):
                    try:
                        picking.action_cancel()
                    except:
                        pass
                move.stock_picking_id = False
                continue

            # --------------------------------------------------------------------------
            # PASO 3: Crear wizard estándar de devolución (en este caso para reversión)
            # --------------------------------------------------------------------------
            # Crear wizard de retorno para revertir la devolución
            wizard = self.env['stock.return.picking'].with_context(
                active_id=picking.id,
                active_ids=[picking.id],
                active_model='stock.picking',
            ).create({})

            if not wizard.product_return_moves:
                move.message_post(
                    body=Markup(_(
                        "⚠️ No se pudo crear la reversión automática de la devolución "
                        "<a href='/web#id=%s&model=stock.picking&view_type=form'><b>%s</b></a>.<br/>"
                        "El picking no tiene líneas disponibles para revertir.<br/>"
                        "Se limpiará el vínculo con la devolución."
                    ) % (picking.id, picking.name))
                )
                move.stock_picking_id = False
                continue

            # Ubicación origen: De dónde salieron en la devolución los productos = a dónde deben regresar los productos
            origin_location_id = picking.location_id

            # Almacén: Se lo obtiene de la ubicación
            origin_warehouse = self.env['stock.warehouse'].search([
                ('lot_stock_id', '=', origin_location_id.id),
            ], limit=1)

            # Configurar wizard
            wizard.write({
                'warehouse_id': origin_warehouse.id if origin_warehouse else False,
                'location_id': origin_location_id.id,
            })

            # --------------------------------------------------------------------
            # PASO 4: Ejecutar devolución (reversión) y obtener picking retornado
            # --------------------------------------------------------------------
            # Ejecutar la reversión
            res = wizard.create_returns()
            picking_reverse = self.env['stock.picking'].browse(res.get('res_id'))

            if not picking_reverse:
                raise UserError(_("No se pudo crear el picking de reversión."))

            # Personalizar el origen de la reversión
            picking_reverse.write({
                'origin': f'Reversión de {picking.name}'
            })

            # ---------------------------------------------------------
            # PASO 5: Validar picking automáticamente
            # ---------------------------------------------------------
            # Confirmar
            picking_reverse.action_confirm()
            # Asignar/Reservar
            picking_reverse.action_assign()
            # Validar/Ejecutar
            picking_reverse.button_validate()

            # -------------------------------------------------------------------
            # PASO 6: Limpiar devolución de la nota de crédito y mostrar mensaje
            # -------------------------------------------------------------------
            # Limpiar stock_picking_id después de validar
            move.stock_picking_id = False

            # Nombre del almacen
            warehouse_name = origin_warehouse.name if origin_warehouse else "No especificado"

            move.message_post(
                body=Markup(
                    _(
                    "✅ Se creó y validó la reversión de la devolución:<br/>"
                    "• <b>Devolución original:</b> "
                    "<a href='/web#id=%s&model=stock.picking&view_type=form'>%s</a> "
                    "(%s → %s)<br/>"
                    "• <b>Reversión:</b> "
                    "<a href='/web#id=%s&model=stock.picking&view_type=form'>%s</a> "
                    "(%s → %s)<br/>"
                    "• <b>Almacén de destino:</b> %s<br/>"
                    "• <b>Ubicación de destino:</b> %s<br/><br/>"
                    "Los productos han sido devueltos a la ubicación de destino.<br/>"
                    "Puede volver a confirmar la Nota de Crédito para generar una nueva devolución."
                    ) % (
                    picking.id, picking.name,
                    picking.location_id.display_name,
                    picking.location_dest_id.display_name,
                    picking_reverse.id, picking_reverse.name,
                    picking_reverse.location_id.display_name,
                    picking_reverse.location_dest_id.display_name,
                    warehouse_name,
                    picking_reverse.location_dest_id.display_name,
                    )
                )
            )

        # Llamar a la función padre para completar el proceso
        return super().button_draft()