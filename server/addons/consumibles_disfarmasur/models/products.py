# -*- coding: utf-8 -*-
from odoo import models, fields, api


# =========================================================
# TIPO DE PRODUCTO
# =========================================================
class ConsumiblesProductType(models.Model):
    _name = 'consumibles.product.type'
    _description = 'Productos'
    _order = 'name'

    name = fields.Char(
        string='Tipo de producto',
        required=True
    )

    description = fields.Text(
        string='Descripción'
    )

    active = fields.Boolean(
        default=True
    )


# =========================================================
# LABORATORIO
# =========================================================
class ConsumiblesProductLaboratory(models.Model):
    _name = 'consumibles.product.laboratory'
    _description = 'Laboratorio'
    _order = 'name'

    name = fields.Char(
        string='Laboratorio',
        required=True
    )

    description = fields.Text(
        string='Descripción'
    )

    active = fields.Boolean(
        default=True
    )


# =========================================================
# PRODUCTO CONSUMIBLE (MODELO MAESTRO)
# =========================================================
class ConsumiblesProductTemplate(models.Model):
    _name = 'consumibles.product.template'
    _description = 'Producto Consumible'
    _order = 'name'

    name = fields.Char(
        string='Nombre del producto',
        required=True
    )

    laboratory_id = fields.Many2one(
        'consumibles.product.laboratory',
        string='Laboratorio',
        required=True,
        ondelete='restrict'
    )

    type_line_ids = fields.One2many(
        'consumibles.product.type.line',
        'product_id',
        string='Tipos y Stock'
    )

    active = fields.Boolean(
        default=True
    )

    cost_history_ids = fields.One2many(
        'consumibles.product.cost.history',
        'product_id',
        string='Historial de Costos'
    )

    # 🔹 NUEVO: marcas dinámicas con historial
    available_product_type_ids = fields.Many2many(
        'consumibles.product.type',
        compute='_compute_available_product_types',
        string='Marcas con historial',
        store=False
    )

    @api.depends('cost_history_ids.product_type_id')
    def _compute_available_product_types(self):
        for product in self:
            product.available_product_type_ids = (
                product.cost_history_ids
                .mapped('product_type_id')
                .filtered(lambda t: t)
            )

    def action_view_cost_history_by_type(self):
        self.ensure_one()

        product_type_id = self.env.context.get('product_type_id')
        if not product_type_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'name': 'Historial de Costos',
            'res_model': 'consumibles.product.cost.history',
            'view_mode': 'tree,form',
            'domain': [
                ('product_id', '=', self.id),
                ('product_type_id', '=', product_type_id),
            ],
            'context': {
                'default_product_id': self.id,
                'default_product_type_id': product_type_id,
            }
        }


# =========================================================
# TIPO + STOCK DEL PRODUCTO (MODELO CLAVE)
# =========================================================
class ConsumiblesProductTypeLine(models.Model):
    _name = 'consumibles.product.type.line'
    _description = 'Tipo y Stock del Producto'
    _order = 'product_type_id'
    _rec_name = 'display_name'  # ✅ CLAVE

    product_id = fields.Many2one(
        'consumibles.product.template',
        string='Producto',
        required=True,
        ondelete='cascade'
    )

    product_type_id = fields.Many2one(
        'consumibles.product.type',
        string='Tipo de producto',
        required=True,
        ondelete='restrict'
    )

    active = fields.Boolean(default=True)

    display_name = fields.Char(
        compute='_compute_display_name',
        store=False
    )

    stock_qty = fields.Float(
        string='Stock',
        compute='_compute_stock_qty',
        inverse='_inverse_stock_qty',
        store=True
    )

    def _inverse_stock_qty(self):
        for line in self:
            # crear movimiento adjust en kardex
            self.env['consumibles.product.kardex'].create({
                'product_id': line.product_id.id,
                'product_type_id': line.product_type_id.id,
                'movement_type': 'adjust',
                'qty_in': line.stock_qty,
            })

    def _compute_stock_qty(self):
        for line in self:
            entries = self.env['consumibles.product.kardex'].search([
                ('product_id', '=', line.product_id.id),
                ('product_type_id', '=', line.product_type_id.id),
            ], order='date, id')

            balance = 0.0
            for move in entries:
                balance += (move.qty_in or 0.0) - (move.qty_out or 0.0)

            line.stock_qty = balance

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.product_type_id.name}"

    _sql_constraints = [
        (
            'unique_product_type_per_product',
            'unique(product_id, product_type_id)',
            'Este tipo de producto ya fue asignado a este producto.'
        )
    ]


# =========================================================
# HISTORIAL DE COSTOS DEL PRODUCTO
# =========================================================
class ConsumiblesProductCostHistory(models.Model):
    _name = 'consumibles.product.cost.history'
    _description = 'Historial de Costos del Producto'
    _order = 'date desc, id desc'

    product_id = fields.Many2one(
        'consumibles.product.template',
        string='Producto',
        required=True,
        ondelete='cascade'
    )

    product_type_id = fields.Many2one(
        'consumibles.product.type',
        string='Tipo de producto',
        required=True,
        ondelete='restrict'
    )

    intake_id = fields.Many2one(
        'consumibles.intake',
        string='Ingreso',
        required=False,
        ondelete='cascade',
    )

    invoice_number = fields.Char(
        string='Número de factura',
        required=True
    )

    qty = fields.Float(
        string='Cantidad',
        required=True
    )

    cost = fields.Float(
        string='Costo unitario',
        required=True
    )

    total = fields.Float(
        string='Total',
        compute='_compute_total',
        store=True
    )

    date = fields.Date(
        string='Fecha',
        required=True
    )

    @api.depends('qty', 'cost')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.qty * rec.cost


# =========================================================
# KARDEX DE PRODUCTOS
# =========================================================
class ConsumiblesProductKardex(models.Model):
    _name = 'consumibles.product.kardex'
    _description = 'Kardex de Productos'
    _order = 'date, id'

    product_id = fields.Many2one(
        'consumibles.product.template',
        string='Producto',
        required=True,
        ondelete='cascade'
    )

    product_type_id = fields.Many2one(
        'consumibles.product.type',
        string='Tipo de producto',
        required=True,
        ondelete='restrict'
    )

    date = fields.Datetime(
        string='Fecha y hora',
        required=True,
        default=fields.Datetime.now
    )

    reference = fields.Char(
        string='Documento'
    )

    movement_type = fields.Selection(
        [
            ('in', 'Entrada'),
            ('out', 'Salida'),
            ('adjust', 'Ajuste'),
        ],
        string='Tipo de movimiento',
        required=True
    )

    qty_in = fields.Float(string='Entrada')
    qty_out = fields.Float(string='Salida')

    balance_qty = fields.Float(
        string='Saldo',
        readonly=True
    )

    cost = fields.Float(string='Costo unitario')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    origin_model = fields.Char(string='Modelo origen')
    origin_id = fields.Integer(string='ID origen')

    @api.depends('qty_in', 'qty_out', 'cost')
    def _compute_total(self):
        for rec in self:
            rec.total = (rec.qty_in or 0.0 - rec.qty_out or 0.0) * (rec.cost or 0.0)
