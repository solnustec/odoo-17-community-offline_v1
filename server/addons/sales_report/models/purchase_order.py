from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # Redefinir partner_id para que no sea obligatorio
    # Esto permite crear órdenes sin proveedor y seleccionarlo manualmente después
    partner_id = fields.Many2one(
        'res.partner', string='Vendor', required=False, change_default=True,
        tracking=True, check_company=True, index=True,
        help="You can find a vendor by its Name, TIN, Email or Internal Reference."
    )

    # Campos Many2many para almacenar TODAS las marcas y laboratorios de la orden
    brand_ids = fields.Many2many(
        'product.brand',
        'purchase_order_brand_rel',
        'order_id',
        'brand_id',
        string='Marcas',
        tracking=True,
        help='Marcas de los productos en esta orden de compra.'
    )

    laboratory_ids = fields.Many2many(
        'product.laboratory',
        'purchase_order_laboratory_rel',
        'order_id',
        'laboratory_id',
        string='Laboratorios',
        tracking=True,
        help='Laboratorios de los productos en esta orden de compra.'
    )

    # Campos de texto para persistencia histórica (se mantienen aunque se eliminen las marcas/laboratorios)
    brand_name = fields.Char(
        string='Nombres Marcas',
        help='Nombres de las marcas (persistente para histórico)',
        tracking=True,
        compute='_compute_brand_names',
        store=True,
        readonly=False
    )

    laboratory_name = fields.Char(
        string='Nombres Laboratorios',
        help='Nombres de los laboratorios (persistente para histórico)',
        tracking=True,
        compute='_compute_laboratory_names',
        store=True,
        readonly=False
    )

    @api.depends('brand_ids')
    def _compute_brand_names(self):
        """Sincroniza los nombres de las marcas cuando cambian brand_ids"""
        for order in self:
            if order.brand_ids:
                order.brand_name = ', '.join(order.brand_ids.mapped('name'))

    @api.depends('laboratory_ids')
    def _compute_laboratory_names(self):
        """Sincroniza los nombres de los laboratorios cuando cambian laboratory_ids"""
        for order in self:
            if order.laboratory_ids:
                order.laboratory_name = ', '.join(order.laboratory_ids.mapped('name'))

    @api.onchange('order_line')
    def _onchange_order_line_brand_laboratory(self):
        """
        Autocompleta marcas y laboratorios basándose en los productos de la orden.
        Agrega TODAS las marcas y laboratorios encontrados.
        """
        if not self.order_line:
            return

        brand_ids = set()
        laboratory_ids = set()

        for line in self.order_line:
            if line.product_id and line.product_id.product_tmpl_id:
                product = line.product_id.product_tmpl_id
                if product.brand_id:
                    brand_ids.add(product.brand_id.id)
                if product.laboratory_id:
                    laboratory_ids.add(product.laboratory_id.id)

        # Agregar todas las marcas encontradas
        if brand_ids:
            self.brand_ids = [(6, 0, list(brand_ids))]

        # Agregar todos los laboratorios encontrados
        if laboratory_ids:
            self.laboratory_ids = [(6, 0, list(laboratory_ids))]

    @api.model_create_multi
    def create(self, vals_list):
        """Al crear, autocompleta marcas/laboratorios"""
        orders = super().create(vals_list)
        for order in orders:
            order._auto_fill_brand_laboratory()
        return orders

    def write(self, vals):
        """Al escribir, actualiza marcas/laboratorios si cambian las líneas"""
        res = super().write(vals)
        if 'order_line' in vals:
            for order in self:
                order._auto_fill_brand_laboratory()
        return res

    def _auto_fill_brand_laboratory(self):
        """
        Método interno para autocompletar marcas y laboratorios.
        Agrega TODAS las marcas y laboratorios de los productos.
        """
        for order in self:
            if not order.order_line:
                continue

            brand_ids = set()
            laboratory_ids = set()

            for line in order.order_line:
                if line.product_id and line.product_id.product_tmpl_id:
                    product = line.product_id.product_tmpl_id
                    if product.brand_id:
                        brand_ids.add(product.brand_id.id)
                    if product.laboratory_id:
                        laboratory_ids.add(product.laboratory_id.id)

            # Actualizar con todas las marcas encontradas
            if brand_ids:
                order.brand_ids = [(6, 0, list(brand_ids))]

            # Actualizar con todos los laboratorios encontrados
            if laboratory_ids:
                order.laboratory_ids = [(6, 0, list(laboratory_ids))]

    def update_brand_laboratory_from_lines(self):
        """
        Método público para actualizar marcas y laboratorios desde el frontend.
        Llamar después de agregar líneas a la orden desde el dashboard.
        """
        self._auto_fill_brand_laboratory()
        return True

    def button_confirm(self):
        """
        Sobrescribe button_confirm para validar que se haya seleccionado un proveedor
        antes de confirmar la orden. Esto evita errores al crear registros en
        product.supplierinfo que requieren partner_id.
        """
        for order in self:
            if not order.partner_id:
                raise UserError(_(
                    "No se puede confirmar la orden de compra '%s' sin un proveedor.\n\n"
                    "Por favor, seleccione un proveedor antes de confirmar."
                ) % order.name)
        return super().button_confirm()
