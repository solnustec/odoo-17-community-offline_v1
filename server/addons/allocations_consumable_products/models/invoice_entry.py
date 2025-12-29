from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ConsumableIntake(models.Model):
    _name = 'allocations.consumable.intake'
    _description = 'Ingreso de Consumibles (Cabecera)'
    _order = 'date_purchase desc, id desc'

    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company, required=True)

    vendor_id = fields.Many2one('res.partner', string='Proveedor', domain=[('supplier_rank', '>', 0)])
    manufacturer_id = fields.Many2one('res.partner', string='Fabricante')

    location = fields.Many2one(
        'stock.warehouse',
        string='Almacén destino',
        required=True
    )
    category = fields.Char(string='Categoría')
    order_number = fields.Char(string='Número de orden')
    bill_number = fields.Char(string='No. Factura / Nota')
    model_no = fields.Char(string='Modelo No.')
    article_no = fields.Char(string='Artículo No.')

    date_purchase = fields.Date(string='Fecha de compra', default=fields.Date.context_today)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id.id, required=True)

    line_ids = fields.One2many('allocations.consumable.intake.line', 'intake_id', string='Líneas')

    amount_untaxed = fields.Monetary(string='Subtotal', currency_field='currency_id',
                                     compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(string='Total de la factura', currency_field='currency_id',
                                   compute='_compute_amounts', store=True)

    @api.depends('line_ids.subtotal')
    def _compute_amounts(self):
        for rec in self:
            subtotal = sum(rec.line_ids.mapped('subtotal'))
            rec.amount_untaxed = subtotal
            rec.amount_total = subtotal


class ConsumableIntakeLine(models.Model):
    _name = 'allocations.consumable.intake.line'
    _description = 'Ingreso de Consumibles (Línea)'
    _order = 'id'

    intake_id = fields.Many2one(
        'allocations.consumable.intake', string='Ingreso', required=True, ondelete='cascade'
    )

    product_id = fields.Many2one(
        'allocations.consumable.products', string='Consumible', required=True, ondelete='restrict'
    )

    qty = fields.Float(string='Cantidad ingresada', required=True, default=1.0, digits=(16, 3))
    qty_moved = fields.Float(string='Cantidad movida', default=0.0, readonly=True)
    qty_available = fields.Float(
        string='Cantidad disponible',
        compute='_compute_qty_available',
        store=True,
        readonly=True,
        digits=(16, 3),
        help='Cantidad restante disponible después de movimientos',
    )

    unit_cost = fields.Float(
        string='Costo unitario',
        required=True,
        digits=(16, 3),
        default=0.0
    )

    currency_id = fields.Many2one(
        related='intake_id.currency_id',
        store=True,
        readonly=True,
    )

    subtotal = fields.Monetary(
        string='Subtotal',
        currency_field='currency_id',
        compute='_compute_subtotal',
        store=True,
    )

    bill_number = fields.Char(
        related='intake_id.bill_number', store=True, readonly=True
    )
    date_purchase = fields.Date(
        related='intake_id.date_purchase', store=True, readonly=True
    )

    @api.depends('qty', 'qty_moved')
    def _compute_qty_available(self):
        for line in self:
            line.qty_available = max((line.qty or 0.0) - (line.qty_moved or 0.0), 0.0)

    @api.depends('unit_cost', 'qty')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = (line.unit_cost or 0.0) * (line.qty or 0.0)
