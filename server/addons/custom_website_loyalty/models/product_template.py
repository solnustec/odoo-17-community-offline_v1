from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from odoo import models, fields, api
from odoo.addons.http_routing.models.ir_http import slug, unslug
import logging
import math

# Configurar el logger
_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    ecommerce_discount = fields.Float(
        string="Descuento Ecommerce",
        compute="_compute_ecommerce_discount",
        default=0,
        store=True,
    )

    ecommerce_required_points = fields.Float(
        string="Puntos necesarios",
        compute="_compute_ecommerce_required_points",
        store=True,
        default=0.0,
    )

    price_with_discount = fields.Float(
        string='Precio con descuento',
        help='Precio con descuento eccomerce',
        store=True,
        compute='_compute_price_with_discount_ecommerce',
    )

    price_with_tax = fields.Float(
        string='Precio con impuestos',
        help='Precio con descuento eccomerce',
        store=True,
        compute='_compute_price_with_tax_ecommerce',
    )

    def calculate_adjusted_price(self, product, price_unit, quantity):
        """
        Calculate adjusted price based on quantity, discount and tax

        This method applies discount and tax calculations with different
        rounding rules based on quantity vs unit comparison threshold.

        Args:
            price_unit (float): Base price per unit
            quantity (float): Quantity to calculate price for

        Returns:
            float: Adjusted unit price (price_without_tax + discount_amount)

        Raises:
            ValueError: If quantity is negative or price_unit is not set
        """

        # Input validation
        if quantity < 0:
            raise ValueError("Quantity cannot be negative")

        if not price_unit:
            return 0.0

        # Convert inputs to float for calculations
        pvp = float(price_unit)
        uc = max(float(product.uom_po_factor_inv or 1.0), 1.0)
        # Get discount and tax percentages
        discount_pct = float(product.ecommerce_discount or 0.0)
        quantity = float(quantity)

        # Get tax amount (assuming single tax)
        tax_pct = 0.0
        if product.taxes_id:
            tax_pct = float(product.taxes_id[0].amount if product.taxes_id else 0.0)

        # Calculate multipliers
        discount_multiplier = 1 - (discount_pct / 100)
        tax_multiplier = 1 + (tax_pct / 100)

        # Calculate unit price with discount and tax
        unit_price_with_tax = pvp * discount_multiplier * tax_multiplier

        # Calculate discount amount for later addition
        discount_amount = pvp * (discount_pct / 100)

        # Apply rounding rules based on quantity threshold
        if quantity < uc:
            # For small quantities: round up to 2 decimals
            unit_price_with_tax = math.ceil(unit_price_with_tax * 100) / 100
        else:
            # For large quantities: round to 4 decimals
            unit_price_with_tax = round(unit_price_with_tax * 10000) / 10000

        # Calculate price without tax
        price_without_tax = unit_price_with_tax / tax_multiplier

        # Return adjusted price (price without tax + discount amount)
        res = price_without_tax + discount_amount
        return res

    @api.depends('is_published', 'ecommerce_required_points', 'ecommerce_discount', 'list_price',
                 'uom_po_id', 'sale_uom_ecommerce')
    @api.depends_context('company')
    def _compute_price_with_tax_ecommerce(self):
        for record in self:
            if record.sale_uom_ecommerce:
                record.price_with_tax = record.price_with_uom_ecommerce
            else:
                if record.taxes_id and record.list_price:
                    taxes = record.taxes_id.filtered(lambda t: t.company_id == self.env.company)
                    tax_result = taxes.compute_all(record.list_price, product=record)
                    record.price_with_tax = tax_result['total_included']
                else:
                    record.price_with_tax = record.list_price or 0.0

    @api.depends('is_published', 'ecommerce_required_points', 'ecommerce_discount', 'list_price',
                 'uom_po_id', 'sale_uom_ecommerce')
    def _compute_price_with_discount_ecommerce(self):
        for product in self:
            if product.is_published and product.ecommerce_discount:
                product.price_with_discount = self._get_discounted_price_with_tax(product, 1)

            else:
                product.price_with_discount = 0.0

    def _compute_ecommerce_discount(self, loyalty_program_id=None, active=None, ecommerce_ok=None):
        for tmpl in self:
            discount = 0
            loyalty_program = self.env['loyalty.program'].sudo().browse(loyalty_program_id)
            if loyalty_program and active and ecommerce_ok:
                for reward in loyalty_program.reward_ids:
                    if reward.reward_type == 'discount':
                        discount = reward.discount
                        break
            tmpl.ecommerce_discount = discount

    def _compute_ecommerce_required_points(self, loyalty_program_id=None, active=None,
                                           ecommerce_ok=None):
        for tmpl in self:
            points = 0.0
            loyalty_program = self.env['loyalty.program'].sudo().browse(loyalty_program_id)
            if loyalty_program and active and ecommerce_ok:
                for reward in loyalty_program.reward_ids:
                    if reward.reward_type == 'discount':
                        points = reward.required_points
                        break
            tmpl.ecommerce_required_points = points

    def _get_base_price_with_tax(self, product, qty=1.0):
        list_price = Decimal(str(product.list_price))
        factor = Decimal(
            str(product.uom_po_id.factor_inv)) if product.sale_uom_ecommerce else Decimal('1.0')
        qty = Decimal(str(qty))
        price = (list_price * factor * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        tax_rate = Decimal(str(product.taxes_id[0].amount)) if product.taxes_id else Decimal('0.00')
        tax_value = (price * tax_rate / Decimal('100')).quantize(Decimal('0.01'),
                                                                 rounding=ROUND_HALF_UP)
        price_with_tax = (price + tax_value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Registrar valores intermedios
        _logger.info(
            f"_get_base_price_with_tax: product={product.name}, list_price={list_price}, "
            f"factor={factor}, qty={qty}, base_price={price}, tax_rate={tax_rate}, "
            f"tax_value={tax_value}, price_with_tax={price_with_tax}"
        )

        return float(price_with_tax)

    @api.model
    def _get_discounted_price_with_tax(self, product_tmpl_id, qty):
        if not product_tmpl_id:
            return 0.0

        qty_d = Decimal(str(qty or 1))
        list_price = Decimal(str(product_tmpl_id.list_price or 0))
        factor = (Decimal(str(product_tmpl_id.uom_po_id.factor_inv))
                  if product_tmpl_id.sale_uom_ecommerce else Decimal('1'))
        base_price = list_price * factor * qty_d

        discount_pct = Decimal(str(product_tmpl_id.ecommerce_discount or 0)) / Decimal('100')
        price_after_discount = base_price * (Decimal('1') - discount_pct)

        taxes = product_tmpl_id.taxes_id.filtered(lambda t: t.company_id == self.env.company)
        if taxes:
            tax_result = taxes.compute_all(float(price_after_discount), product=product_tmpl_id)
            price_with_tax = Decimal(str(tax_result.get('total_included', 0.0)))
        else:
            price_with_tax = price_after_discount

        final_price = price_with_tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return float(final_price)

    def _get_combination_info(self, combination=False, product_id=False, add_qty=1.0,
                              parent_combination=False,
                              only_template=False):
        combination_info = super()._get_combination_info(
            combination=combination,
            product_id=product_id,
            add_qty=add_qty,
            parent_combination=parent_combination,
            only_template=only_template
        )
        product = self
        combination_info['price'] = self._get_base_price_with_tax(product, add_qty)
        if product.ecommerce_discount > 0:
            combination_info['price_add_discount'] = self._get_discounted_price_with_tax(product,
                                                                                         add_qty)
        return combination_info

    def _get_sales_prices(self, pricelist, fiscal_position):
        res = super()._get_sales_prices(pricelist, fiscal_position)
        for product_tmpl in self:
            template_vals = res.get(product_tmpl.id)
            if not template_vals:
                continue
            base = self._get_base_price_with_tax(product_tmpl, 1)
            template_vals['price_reduce'] = base
            if product_tmpl.ecommerce_discount > 0:
                template_vals['discounted_price_rounded'] = self._get_discounted_price_with_tax(
                    product_tmpl, 1)
        return res

    def _calculate_discounted_price_ecommerce(self, product_tmpl_id, product_uom_qty):
        try:
            return self._get_discounted_price_with_tax(product_tmpl_id, product_uom_qty)
        except Exception as e:
            _logger.error(f"Error in _calculate_discounted_price_ecommerce: {str(e)}")
            return float(product_tmpl_id.list_price or 0.0)

    @api.model
    def get_product_template_and_discount(self, product_tmpl_id, product_uom_qty):
        product_tmpl = self.env['product.template'].sudo().search([
            ('name', '=', product_tmpl_id),
        ], limit=1)
        result = self._calculate_discounted_price_ecommerce(product_tmpl, product_uom_qty)

        return result

    @api.model
    def get_product_template_and_discount_id(self, product_tmpl_id, product_uom_qty):
        if not product_tmpl_id:
            return 0.00

        product_tmpl_id = int(product_tmpl_id)
        product_tmpl = self.env['product.template'].sudo().browse(product_tmpl_id)
        result = self._calculate_discounted_price_ecommerce(product_tmpl, product_uom_qty)
        return result

    @api.model
    def _search_get_detail(self, website, order, options):
        result = super()._search_get_detail(website, order, options)
        if options.get('displayDetail'):
            result['mapping']['detail_discount'] = {
                'name': 'discounted_price',
                'type': 'html',
                'display_currency': options['display_currency']
            }
        return result

    def _search_render_results(self, fetch_fields, mapping, icon, limit):
        res = super()._search_render_results(fetch_fields, mapping, icon, limit)
        for product, data in zip(self, res):
            product_uom_qty = 1
            discount_result = self.get_product_template_and_discount(product.name, product_uom_qty)
            data['discounted_price'] = "{:.2f}".format(float(discount_result or 0.0))

        return res

    @api.model
    def action_hide_out_of_stock_products(self):
        # Obtener el sitio web activo de la empresa
        website = self.env['website'].sudo().search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)

        if not website or not website.warehouse_id:
            return

        location = website.warehouse_id.lot_stock_id
        tot = []
        # Obtener todos los productos publicados tipo almacenable
        products = self.search([
            ('website_published', '=', True),
            ('detailed_type', '=', 'product')
        ])

        # Variantes con contexto de ubicación
        variants = products.mapped('product_variant_ids').with_context(
            location=location.id)

        # Acumular stock por plantilla de producto
        stock_by_template = {}
        for variant in variants:
            tmpl_id = variant.product_tmpl_id.id
            stock_by_template[tmpl_id] = stock_by_template.get(tmpl_id,
                                                               0) + variant.qty_available

        # Filtrar productos sin stock
        products_to_unpublish = products.filtered(
            lambda p: stock_by_template.get(p.id, 0) <= 0)
        # Despublicar en lote
        if products_to_unpublish:
            products_to_unpublish.write({'website_published': False})
