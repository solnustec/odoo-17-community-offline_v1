# -*- coding: utf-8 -*-


from odoo import api, fields, models


class ProductPurchaseHistory(models.Model):
    _name = 'product.purchase.history'
    _description = 'Historial de Compras de Producto'
    _order = 'create_date desc'

    product_tmpl_id = fields.Many2one('product.template', string='Producto', required=True)
    purchase_order_id = fields.Many2one('purchase.order', string='Orden de Compra')
    partner_id = fields.Many2one('res.partner', string='Proveedor')
    quantity = fields.Float(string='Cantidad')
    price_unit = fields.Float(string='Precio Unitario')
    price_unit_per_unit = fields.Float(
        string='Costo Unitario (por unidad)',
        compute='_compute_price_unit_per_unit',
        store=True,
        readonly=True,
        help='Precio unitario dividido por unidades por empaque del UoM de compra'
    )
    id_purchase_old = fields.Char(string='ID Línea Compra Antiguo')

    date_order = fields.Date(string='Fecha de Compra')
    discount = fields.Float(string='Descuento (%)', help='Descuento aplicado en la línea de compra')
    free_product_qty = fields.Float(string='Producto Gratis', default=0.0,
                                    help='Cantidad de producto gratis (promoción)')
    paid_quantity = fields.Float(string='Cantidad Pagada',
                                 help='Cantidad pedida sin incluir producto gratis')
    pvf = fields.Float(string='PVF', help='Precio de Venta Final calculado')
    credit_note = fields.Boolean(string='Nota de Crédito', default=False,
                                 help='Indica si esta línea corresponde a una nota de crédito')

    @api.depends('price_unit', 'product_tmpl_id.uom_po_id.factor',
                 'product_tmpl_id.uom_po_id.factor_inv')
    def _compute_price_unit_per_unit(self):
        for rec in self:
            uom = rec.product_tmpl_id.uom_po_id
            units_per_package = 1.0
            if uom:
                finv = float(uom.factor_inv or 0.0)
                if finv > 0.0:
                    units_per_package = finv
                else:
                    f = float(uom.factor or 0.0)
                    if f > 0.0:
                        units_per_package = 1.0 / f
            price_unit = float(rec.price_unit or 0.0)
            # Aplicar descuento si existe
            discount_factor = 1.0 - (rec.discount or 0.0) / 100.0
            price_with_discount = price_unit * discount_factor
            rec.price_unit_per_unit = price_with_discount / (units_per_package or 1.0)

    @api.model
    def create_from_purchase_line(self, purchase_line):
        """
        Create a purchase history record from a purchase order line
        
        Features:
        - Prevents duplicate records by checking existing entries (idempotent)
        - Uses composite key: product_tmpl_id + purchase_order_id + date_order
        - Returns existing record if duplicate found
        - Creates new record only if unique
        
        :param purchase_line: Purchase order line record
        :return: Created or existing purchase history record
        """
        # Deduplicate using a logical composite key so repeated calls do not create duplicates
        existing_history = self.search([
            ('product_tmpl_id', '=', purchase_line.product_id.product_tmpl_id.id),
            ('purchase_order_id', '=', purchase_line.order_id.id),
            ('date_order', '=', purchase_line.order_id.date_order),
        ], limit=1)
        if existing_history:
            return existing_history
        return self.create({
            'product_tmpl_id': purchase_line.product_id.product_tmpl_id.id,
            'purchase_order_id': purchase_line.order_id.id,
            'partner_id': purchase_line.order_id.partner_id.id,
            'quantity': purchase_line.product_qty,
            'price_unit': purchase_line.price_unit,
            'date_order': purchase_line.order_id.date_order,
            'discount': purchase_line.discount or 0.0,
            'free_product_qty': getattr(purchase_line, 'free_product_qty', 0.0),
            'paid_quantity': purchase_line.paid_quantity,  # Cantidad pedida sin producto gratis
            'pvf': purchase_line.pvf or 0.0,
        })

    @api.model
    def remove_duplicate_by_id_purchase_old(self, batch_size=5000):
        domain = [
            ('id_purchase_old', '!=', False),
            ('product_tmpl_id', '!=', False),
            ('date_order', '!=', False),
            ('quantity', '!=', 0),
        ]

        last_key = None
        total_deleted = 0
        last_id = 0

        while True:
            records = self.search(
                domain + [('id', '>', last_id)],
                limit=batch_size,
                order="""
                        id_purchase_old,
                        product_tmpl_id,
                        date_order,
                        quantity,
                        credit_note,
                        create_date desc,
                        id desc
                    """
            )

            if not records:
                break

            for r in records:
                key = (
                    r.id_purchase_old,
                    r.product_tmpl_id.id,
                    r.date_order,
                    r.quantity,
                    r.credit_note,
                )

                if key == last_key:
                    r.unlink()
                    total_deleted += 1
                else:
                    last_key = key

                last_id = r.id

            # MUY IMPORTANTE EN CRON
            self.env.cr.commit()

        return total_deleted
    # @api.model
    # def remove_duplicate_by_id_purchase_old(self):
    #     """
    #         Elimina registros duplicados que tengan la misma combinación de:
    #         id_purchase_old, product_tmpl_id, date_order y quantity.
    #         Mantiene el registro más reciente (según create_date) y elimina los demás.
    #         """
    #     # Buscar todos los registros con campos clave no vacíos/válidos
    #     all_records = self.search([
    #         ('id_purchase_old', '!=', False),
    #         ('product_tmpl_id', '!=', False),
    #         ('date_order', '!=', False),
    #         ('quantity', '!=', 0)
    #     ])
    #
    #     from collections import defaultdict
    #     grouped = defaultdict(list)
    #     for record in all_records:
    #         key = (
    #             record.id_purchase_old,
    #             record.product_tmpl_id.id,
    #             record.date_order,  # Es un Date, se compara directamente
    #             record.quantity,  # Float, se compara directamente
    #             record.credit_note
    #         )  # Tupla como clave única
    #         grouped[key].append(record)
    #
    #     deleted_count = 0
    #     for key, records in grouped.items():
    #         if len(records) > 1:
    #             records_sorted = sorted(records, key=lambda r: r.create_date, reverse=True)
    #             to_delete = records_sorted[1:]
    #             for record in to_delete:
    #                 record.unlink()  # Descomenta para eliminar realmente
    #                 deleted_count += 1
    #     print(f"Total de duplicados encontrados y listos para eliminar: {deleted_count}")
    #     return deleted_count


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    purchase_history_ids = fields.One2many(
        comodel_name='product.purchase.history',
        inverse_name='product_tmpl_id',  # Campo inverso en product.purchase.history
        string='Historial de Compras'
    )


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def write(self, vals):
        res = super(PurchaseOrderLine, self).write(vals)
        # Odoo may call write on multiple lines at once (recordset).
        # Iterate safely over each line to avoid singleton errors when accessing fields.
        # COMENTADO: Ya no se crea historial al confirmar orden, solo al facturar
        # for line in self:
        #     if line.order_id.state in ['purchase', 'done']:
        #         # Check for existing record to prevent duplicates (fast path with limit)
        #         existing_history = self.env['product.purchase.history'].search([
        #             ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id),
        #             ('purchase_order_id', '=', line.order_id.id),
        #             ('date_order', '=', line.order_id.date_order)
        #         ], limit=1)
        #         if not existing_history:
        #             self.env['product.purchase.history'].create_from_purchase_line(line)
        return res

    @api.model
    def create(self, vals):
        line = super(PurchaseOrderLine, self).create(vals)
        # COMENTADO: Ya no se crea historial al confirmar orden, solo al facturar
        # Create history only when PO is confirmed (purchase) or done
        # if line.order_id.state == 'purchase':
        #     self.env['product.purchase.history'].create_from_purchase_line(line)
        return line


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.model
    def _sync_history_with_order_state(self, order_id, new_state):
        """Sync history records based on order state changes"""
        # COMENTADO: Ya no se crea historial al confirmar orden, solo al facturar
        # if new_state in ['purchase', 'done']:
        #     # Create history for all lines in this order
        #     order = self.browse(order_id)
        #     for line in order.order_line:
        #         if line.product_id:
        #             # Check if history already exists
        #             existing = self.env['product.purchase.history'].search([
        #                 ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id),
        #                 ('purchase_order_id', '=', order_id),
        #                 ('date_order', '=', line.order_id.date_order)
        #             ], limit=1)
        #             if not existing:
        #                 self.env['product.purchase.history'].create_from_purchase_line(line)
        # else:
        #     # Remove history for cancelled/draft orders
        #     history_records = self.env['product.purchase.history'].search([
        #         ('purchase_order_id', '=', order_id)
        #     ])
        #     history_records.unlink()

        # Eliminar historial cuando se cancela o vuelve a borrador
        if new_state in ['cancel', 'draft']:
            history_records = self.env['product.purchase.history'].search([
                ('purchase_order_id', '=', order_id)
            ])
            history_records.unlink()

    def write(self, vals):
        """Override to sync history when order state changes"""
        result = super(PurchaseOrder, self).write(vals)

        # Check if state changed
        if 'state' in vals:
            for order in self:
                self._sync_history_with_order_state(order.id, vals['state'])

        return result
