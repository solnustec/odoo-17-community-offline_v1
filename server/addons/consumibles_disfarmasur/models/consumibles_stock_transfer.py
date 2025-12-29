# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ConsumiblesStockTransfer(models.Model):
    _name = 'consumibles.stock.transfer'
    _description = 'Transferencia de Stock de Consumibles'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Referencia',
        required=True
    )

    date = fields.Date(
        string='Fecha',
        default=fields.Date.context_today,
        required=True
    )

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Bodega destino',
        required=True
    )

    line_ids = fields.One2many(
        'consumibles.stock.transfer.line',
        'transfer_id',
        string='Detalle de productos'
    )

    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmado'),
            ('cancel', 'Cancelado')
        ],
        default='draft',
        tracking=True
    )

    def action_confirm(self):
        Kardex = self.env['consumibles.product.kardex']

        for transfer in self:
            if transfer.state != 'draft':
                raise ValidationError(
                    _('Solo puedes confirmar transferencias en borrador.')
                )

            if not transfer.line_ids:
                raise ValidationError(_('No hay productos para transferir.'))

            # 1️⃣ VALIDAR STOCK (DESDE KARDEX)
            for line in transfer.line_ids:
                if line.qty <= 0:
                    raise ValidationError(_('La cantidad debe ser mayor a cero.'))

                last_kardex = Kardex.search([
                    ('product_id', '=', line.product_id.id),
                    ('product_type_id', '=', line.product_type_line_id.product_type_id.id),
                ], order='date desc, id desc', limit=1)

                available_qty = last_kardex.balance_qty if last_kardex else 0.0

                if available_qty < line.qty:
                    raise ValidationError(
                        f"No hay stock suficiente para:\n"
                        f"{line.product_id.name} - {line.product_type_line_id.product_type_id.name}\n"
                        f"Disponible: {available_qty}"
                    )

            # 2️⃣ CREAR SALIDA EN KARDEX
            for line in transfer.line_ids:
                last_kardex = Kardex.search([
                    ('product_id', '=', line.product_id.id),
                    ('product_type_id', '=', line.product_type_line_id.product_type_id.id),
                ], order='date desc, id desc', limit=1)

                previous_balance = last_kardex.balance_qty if last_kardex else 0.0
                new_balance = previous_balance - line.qty

                Kardex.with_context(allow_kardex_create=True).create({
                    'product_id': line.product_id.id,
                    'product_type_id': line.product_type_line_id.product_type_id.id,
                    'date': fields.Datetime.now(),
                    'reference': transfer.name,
                    'movement_type': 'out',
                    'qty_in': 0.0,
                    'qty_out': line.qty,
                    'balance_qty': new_balance,
                    'cost': last_kardex.cost if last_kardex else 0.0,
                    'origin_model': 'consumibles.stock.transfer',
                    'origin_id': transfer.id,
                })

            transfer.state = 'confirmed'

    def action_cancel(self):
        Kardex = self.env['consumibles.product.kardex']

        for transfer in self:
            if transfer.state != 'confirmed':
                transfer.state = 'cancel'
                continue

            for line in transfer.line_ids:
                last_kardex = Kardex.search([
                    ('product_id', '=', line.product_id.id),
                    ('product_type_id', '=', line.product_type_line_id.product_type_id.id),
                ], order='date desc, id desc', limit=1)

                previous_balance = last_kardex.balance_qty if last_kardex else 0.0

                Kardex.with_context(allow_kardex_create=True).create({
                    'product_id': line.product_id.id,
                    'product_type_id': line.product_type_line_id.product_type_id.id,
                    'date': fields.Datetime.now(),
                    'reference': f"REVERSO {transfer.name}",
                    'movement_type': 'in',
                    'qty_in': line.qty,
                    'qty_out': 0.0,
                    'balance_qty': previous_balance + line.qty,
                    'cost': last_kardex.cost if last_kardex else 0.0,
                    'origin_model': 'consumibles.stock.transfer',
                    'origin_id': transfer.id,
                })

            transfer.state = 'cancel'


class ConsumiblesStockTransferLine(models.Model):
    _name = 'consumibles.stock.transfer.line'
    _description = 'Detalle Transferencia de Stock'

    transfer_id = fields.Many2one(
        'consumibles.stock.transfer',
        string='Transferencia',
        required=True,
        ondelete='cascade'
    )

    product_id = fields.Many2one(
        'consumibles.product.template',
        string='Producto',
        required=True
    )

    product_type_line_id = fields.Many2one(
        'consumibles.product.type.line',
        string='Tipo de producto',
        required=True,
        domain="[('product_id', '=', product_id)]"
    )

    qty = fields.Float(
        string='Cantidad',
        required=True
    )
