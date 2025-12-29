# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


# =========================================================
# INGRESO DE CONSUMIBLES (CABECERA)
# =========================================================
class ConsumiblesIntake(models.Model):
    _name = 'consumibles.intake'
    _description = 'Ingreso de Consumibles'
    _order = 'date desc, id desc'

    partner_id = fields.Many2one(
        'res.partner',
        string='Proveedor',
        domain=[('supplier_rank', '>', 0)],
        required=True
    )

    date = fields.Date(
        string='Fecha de la factura',
        default=fields.Date.context_today,
        required=True
    )

    invoice_number = fields.Char(
        string='Número de factura',
        required=True,
        copy=False
    )

    line_ids = fields.One2many(
        'consumibles.intake.line',
        'intake_id',
        string='Detalle de productos'
    )

    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmado'),
            ('cancel', 'Cancelado'),
        ],
        default='draft',
        tracking=True
    )

    total_amount = fields.Float(
        string='Total factura',
        compute='_compute_total_amount',
        store=True
    )

    # -----------------------------------------------------
    # CONFIRMAR INGRESO
    # -----------------------------------------------------
    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if not rec.line_ids:
                raise ValidationError('No puedes confirmar una factura sin productos.')

            for line in rec.line_ids:
                if line.qty <= 0:
                    raise ValidationError('La cantidad debe ser mayor a cero.')

                # 🔥 CREAR MOVIMIENTO KARDEX
                last_kardex = self.env['consumibles.product.kardex'].search([
                    ('product_id', '=', line.product_id.id),
                    ('product_type_id', '=', line.product_type_line_id.product_type_id.id),
                ], order='date desc, id desc', limit=1)

                previous_balance = last_kardex.balance_qty if last_kardex else 0.0
                new_balance = previous_balance + line.qty

                self.env['consumibles.product.kardex'].create({
                    'product_id': line.product_id.id,
                    'product_type_id': line.product_type_line_id.product_type_id.id,
                    'date': fields.Datetime.now(),
                    'reference': rec.invoice_number,
                    'movement_type': 'in',
                    'qty_in': line.qty,
                    'qty_out': 0.0,
                    'balance_qty': new_balance,
                    'cost': line.cost,
                    'origin_model': 'consumibles.intake',
                    'origin_id': rec.id,
                })

            rec.state = 'confirmed'

    # -----------------------------------------------------
    # CANCELAR (REVERSA STOCK)
    # -----------------------------------------------------
    def action_cancel(self):
        for rec in self:
            if rec.state != 'confirmed':
                return

            for line in rec.line_ids:
                line.product_type_line_id.stock_qty -= line.qty

            rec.state = 'cancel'

    @api.depends('line_ids.line_total')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('line_total'))

    def name_get(self):
        result = []
        for rec in self:
            parts = []

            if rec.invoice_number:
                parts.append(rec.invoice_number)

            if rec.date:
                parts.append(rec.date.strftime('%d/%m/%Y'))

            if rec.partner_id:
                parts.append(rec.partner_id.name)

            name = ' | '.join(parts) if parts else f'Ingreso {rec.id}'
            result.append((rec.id, name))

        return result


# =========================================================
# INGRESO DE CONSUMIBLES (LÍNEAS)
# =========================================================
class ConsumiblesIntakeLine(models.Model):
    _name = 'consumibles.intake.line'
    _description = 'Detalle de Ingreso de Consumibles'
    _order = 'id'

    intake_id = fields.Many2one(
        'consumibles.intake',
        string='Ingreso',
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
        string='Tipo',
        required=True,
        domain="[('product_id', '=', product_id)]"
    )

    qty = fields.Float(
        string='Cantidad',
        required=True,
        default=1.0
    )

    cost = fields.Float(
        string='Costo unitario',
        required=True,
        default=0.0
    )

    line_total = fields.Float(
        string='Total',
        compute='_compute_line_total',
        store=True
    )

    @api.depends('qty', 'cost')
    def _compute_line_total(self):
        for line in self:
            line.line_total = line.qty * line.cost

    # 🔒 BLOQUEAR EDICIÓN SI NO ES BORRADOR
    @api.constrains('qty', 'product_type_line_id', 'cost')
    def _check_edit_when_confirmed(self):
        for line in self:
            if line.intake_id.state == 'confirmed':
                raise ValidationError(
                    'No puedes modificar líneas de un ingreso confirmado.'
                )
